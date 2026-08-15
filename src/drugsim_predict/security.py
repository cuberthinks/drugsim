"""Minimal access control and abuse protection for the prediction API.

Phase 8 scope, deliberately minimal:

* :class:`ApiKeyMiddleware` distinguishes public (health/docs) from
  protected (predict, model, retrieval) endpoints via a shared API key.
  This is NOT a multi-tenant identity platform -- this codebase has no
  user/tenant concept anywhere in it (see the original ``api.py`` module
  docstring), and building one is out of scope for a deployment-hardening
  phase ("do not build a complex enterprise identity platform unless
  required"). A shared API key is the smallest change that satisfies
  "distinguish public from protected access" for a controlled external
  demonstration with a small, known set of users.
* :class:`RateLimitMiddleware` is a single-process, in-memory sliding
  window limiter -- correct and sufficient for "the simplest appropriate
  deployment architecture," explicitly not Redis-backed, since this
  deployment runs one worker process (see docs/phase8). Documented as a
  known limitation if ever scaled to multiple worker processes.
* :class:`BodySizeLimitMiddleware` rejects oversized requests, checked
  both via ``Content-Length`` (fast path, covers the realistic case) and
  by capping bytes actually read (defense in depth against a missing or
  understated ``Content-Length``).
* :class:`ConcurrencyLimitMiddleware` bounds how many requests this
  process will work on at once, so a burst of slow requests cannot pile up
  unboundedly.

None of these know anything about chemistry -- they operate purely on
HTTP-level concerns, ahead of any structure ever reaching the pipeline.
"""

from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from typing import Deque, Dict

from starlette.types import ASGIApp, Receive, Scope, Send

from drugsim_predict.schemas import ProblemDetail
from drugsim_predict.settings import get_predict_settings

__all__ = [
    "ApiKeyMiddleware",
    "BodySizeLimitMiddleware",
    "ConcurrencyLimitMiddleware",
    "RateLimitMiddleware",
    "reset_rate_limit_state",
]

#: Paths reachable without an API key -- liveness/readiness must be public
#: so an external orchestrator or uptime monitor can check them, and the
#: OpenAPI docs are non-sensitive.
_PUBLIC_PATHS = frozenset({"/health", "/health/ready", "/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"})


def _problem_body(status: int, type_slug: str, title: str, detail: str) -> bytes:
    import json

    problem = ProblemDetail(type=f"https://drugsim.internal/errors/{type_slug}", title=title, status=status, detail=detail)
    return json.dumps(problem.model_dump(exclude_none=True)).encode("utf-8")


async def _send_problem(send: Send, status: int, type_slug: str, title: str, detail: str, extra_headers: list[tuple[bytes, bytes]] | None = None) -> None:
    body = _problem_body(status, type_slug, title, detail)
    headers = [(b"content-type", b"application/problem+json")]
    if extra_headers:
        headers.extend(extra_headers)
    await send({"type": "http.response.start", "status": status, "headers": headers})
    await send({"type": "http.response.body", "body": body})


class ApiKeyMiddleware:
    """Requires a valid ``X-API-Key`` header on every route except health
    checks and API documentation, whenever at least one key is configured.

    A no-op when no keys are configured -- local/dev/test convenience.
    :func:`drugsim_predict.settings.assert_safe_to_start` is what prevents
    an unauthenticated deployment from being staging/production, so this
    middleware being permissive-by-default in dev never becomes a
    production gap silently.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        settings = get_predict_settings()
        keys = settings.api_key_set
        if not keys:
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers") or [])
        provided = headers.get(b"x-api-key", b"").decode("latin-1")
        if provided not in keys:
            await _send_problem(
                send, 401, "unauthorized", "Missing or invalid API key",
                "This endpoint requires a valid X-API-Key header.",
            )
            return

        await self.app(scope, receive, send)


#: Module-level (not instance-level) sliding-window state. Deliberately not
#: stored on the middleware instance: Starlette builds and caches the
#: middleware stack lazily on first request, so an instance attribute would
#: live for the lifetime of the app object -- correct in production (one
#: long-lived process), but it would leak rate-limit state across tests
#: that share the same imported ``app``. Module-level state can be reset
#: explicitly via :func:`reset_rate_limit_state`, which tests do.
_rate_limit_buckets: Dict[str, Deque[float]] = defaultdict(deque)


def reset_rate_limit_state() -> None:
    """Clear all rate-limit tracking. Intended for tests only."""
    _rate_limit_buckets.clear()


class RateLimitMiddleware:
    """Fixed-window-per-key (or per-client-IP) request rate limiting.

    In-memory only -- correct for a single worker process, not a
    distributed limiter. See module docstring.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    def _client_ip(self, scope: Scope, headers: Dict[bytes, bytes]) -> str:
        """The requesting client's address, seen through any reverse proxy.

        ``scope["client"]`` is the *immediate* peer, which behind Render's
        router (or the Caddy topology in deployment/caddy/) is the proxy
        itself -- identical for every visitor, and therefore useless as a
        per-client identity. The originating address is the first entry of
        ``X-Forwarded-For``. That header is client-spoofable in general,
        which is why it is not used for authentication; here it only
        partitions rate-limit buckets, where the worst case of a forged
        value is an abuser widening their own limit -- exactly what they
        could already do from multiple addresses.
        """
        forwarded = headers.get(b"x-forwarded-for")
        if forwarded:
            first = forwarded.decode("latin-1").split(",")[0].strip()
            if first:
                return first
        client = scope.get("client")
        return client[0] if client else "unknown"

    def _client_key(self, scope: Scope) -> str:
        headers = dict(scope.get("headers") or [])
        ip = self._client_ip(scope, headers)
        api_key = headers.get(b"x-api-key")
        if api_key:
            # Keyed by API key *and* address, never the key alone. This
            # product ships a single shared key baked into the browser
            # bundle (frontend/src/api/client.ts says so explicitly: it is
            # a "controlled demonstration" barrier, not per-user auth), so
            # keying on the key alone puts every visitor on earth into one
            # 30-requests-per-minute bucket -- two colleagues opening the
            # app at the same time then rate-limit each other, which reads
            # as the service randomly failing rather than as a quota.
            return f"key:{api_key.decode('latin-1')}|ip:{ip}"
        return f"ip:{ip}"

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        settings = get_predict_settings()
        limit = settings.rate_limit_requests_per_minute
        now = time.monotonic()
        window_start = now - 60.0
        key = self._client_key(scope)
        bucket = _rate_limit_buckets[key]

        while bucket and bucket[0] < window_start:
            bucket.popleft()

        if len(bucket) >= limit:
            await _send_problem(
                send, 429, "rate-limited", "Too many requests",
                f"This client has exceeded {limit} requests per minute. Please slow down and retry shortly.",
                extra_headers=[(b"retry-after", b"60")],
            )
            return

        bucket.append(now)
        await self.app(scope, receive, send)


class BodySizeLimitMiddleware:
    """Rejects request bodies over the configured limit.

    Two layers: a fast ``Content-Length``-based rejection (covers the
    realistic case -- virtually every well-behaved client sets this), and a
    hard cap on bytes actually read from the ASGI receive channel (defense
    in depth against a missing or understated ``Content-Length``, e.g. a
    chunked-transfer request). The second layer cannot produce as clean an
    error response once streaming has started, so it raises, which the
    application's own global exception handler turns into a safe generic
    500 rather than letting an oversized body be buffered into memory.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        settings = get_predict_settings()
        max_bytes = settings.max_request_body_bytes

        headers = dict(scope.get("headers") or [])
        content_length = headers.get(b"content-length")
        if content_length is not None:
            try:
                if int(content_length) > max_bytes:
                    await _send_problem(
                        send, 413, "payload-too-large", "Request body too large",
                        f"Request body exceeds the {max_bytes}-byte limit.",
                    )
                    return
            except ValueError:
                pass  # Malformed header -- let the ASGI server / Starlette reject it downstream.

        total = 0

        async def limited_receive() -> dict:
            nonlocal total
            message = await receive()
            if message.get("type") == "http.request":
                total += len(message.get("body", b""))
                if total > max_bytes:
                    msg = f"request body exceeded {max_bytes} bytes during streaming"
                    raise ValueError(msg)
            return message

        await self.app(scope, limited_receive, send)


class ConcurrencyLimitMiddleware:
    """Bounds how many requests this process works on concurrently.

    A simple semaphore, not a queue -- a request that cannot acquire a slot
    immediately is rejected with 503 rather than queued indefinitely, so a
    burst of slow requests degrades visibly (clients see an honest error and
    can retry) instead of silently piling up latency for everyone.
    """

    def __init__(self, app: ASGIApp) -> None:
        self.app = app
        self._semaphore: asyncio.Semaphore | None = None

    def _get_semaphore(self) -> asyncio.Semaphore:
        if self._semaphore is None:
            settings = get_predict_settings()
            self._semaphore = asyncio.Semaphore(settings.max_concurrent_requests)
        return self._semaphore

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http" or scope["path"] in _PUBLIC_PATHS:
            await self.app(scope, receive, send)
            return

        semaphore = self._get_semaphore()
        if not await self._try_acquire(semaphore):
            await _send_problem(
                send, 503, "server-busy", "Server is at capacity",
                "Too many concurrent requests are already being processed. Please retry shortly.",
                extra_headers=[(b"retry-after", b"2")],
            )
            return

        try:
            await self.app(scope, receive, send)
        finally:
            semaphore.release()

    @staticmethod
    async def _try_acquire(semaphore: asyncio.Semaphore) -> bool:
        try:
            await asyncio.wait_for(semaphore.acquire(), timeout=0.001)
            return True
        except asyncio.TimeoutError:
            return False
