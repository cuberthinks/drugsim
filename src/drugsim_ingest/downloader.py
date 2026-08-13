"""HTTP download with retry, streaming checksum, and structured logging.

Retries distinguish transient failures (network errors, 5xx, 429) from
permanent ones (404, other 4xx) — retrying a 404 wastes time and obscures the
real error. A checksum mismatch is treated as potentially transient (corruption
in transit) and retried up to the same limit, but is reported distinctly from a
network failure if it never resolves, because the fix for each is different: a
persistent checksum mismatch usually means the *expected* value is stale, not
that the download is failing.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import httpx
from tenacity import Retrying, retry_if_exception_type, stop_after_attempt, wait_exponential_jitter

from drugsim_core.errors import DrugSimError
from drugsim_core.logging import get_logger
from drugsim_ingest.checksums import DEFAULT_CHUNK_BYTES, sha256_of_chunks

__all__ = [
    "ChecksumMismatchError",
    "DownloadError",
    "DownloadResult",
    "download_to_file",
]

_logger = get_logger(__name__)


class DownloadError(DrugSimError):
    """A download failed after exhausting retries."""

    code = "download_failed"


class ChecksumMismatchError(DownloadError):
    """A download completed but its checksum never matched the expected value.

    Distinguished from a generic :class:`DownloadError` because the remedy
    differs: a persistent mismatch after successful, complete downloads usually
    means the *expected* checksum on file (e.g. in ``registry.yaml``) is stale
    or the source silently changed content without a version bump, not that the
    transfer itself is broken.
    """

    code = "checksum_mismatch"


@dataclass(frozen=True)
class DownloadResult:
    """The outcome of a completed, verified download.

    Attributes:
        url: Source URL.
        local_path: Where the bytes were written.
        sha256: Digest computed while streaming (not a second pass over the file).
        byte_size: Total bytes written.
        attempts: How many attempts the download took, including the successful one.
    """

    url: str
    local_path: Path
    sha256: str
    byte_size: int
    attempts: int


class _RetryableTransferError(Exception):
    """Internal signal: this attempt failed in a way worth retrying."""


def _is_retryable_status(status_code: int) -> bool:
    """Whether an HTTP status code represents a transient failure worth retrying.

    Args:
        status_code: The response status code.

    Returns:
        True for 5xx (server error) and 429 (rate limited); false otherwise —
        a 404 or other 4xx will not become true on retry.
    """
    return status_code >= 500 or status_code == 429


def _stream_to_file(
    client: httpx.Client,
    url: str,
    destination: Path,
    *,
    chunk_bytes: int,
    timeout_seconds: int,
) -> tuple[int, str]:
    """Perform one streaming download attempt.

    Args:
        client: An httpx client (real or test transport).
        url: Source URL.
        destination: Path to write to. Overwritten if a prior attempt left a
            partial file — attempts are not resumed, since resuming and then
            checksumming would require additional state this scale does not
            justify.
        chunk_bytes: Read/write chunk size.
        timeout_seconds: Per-request timeout.

    Returns:
        A tuple of (byte count written, sha256 hex digest).

    Raises:
        _RetryableTransferError: For a transient HTTP or transport failure.
        httpx.HTTPStatusError: For a non-retryable HTTP status.
    """
    digest_chunks: list[bytes] = []
    byte_count = 0

    def _chunks() -> Iterator[bytes]:
        nonlocal byte_count
        with client.stream("GET", url, timeout=timeout_seconds) as response:
            if _is_retryable_status(response.status_code):
                msg = f"retryable status {response.status_code} from {url}"
                raise _RetryableTransferError(msg)
            response.raise_for_status()
            for chunk in response.iter_bytes(chunk_bytes):
                byte_count += len(chunk)
                digest_chunks.append(chunk)
                yield chunk

    try:
        with destination.open("wb") as handle:
            for chunk in _chunks():
                handle.write(chunk)
    except httpx.TransportError as exc:
        msg = f"transport error downloading {url}: {exc}"
        raise _RetryableTransferError(msg) from exc

    return byte_count, sha256_of_chunks(digest_chunks)


def _attempt_with_retry(
    client: httpx.Client,
    url: str,
    destination: Path,
    *,
    chunk_bytes: int,
    timeout_seconds: int,
    max_network_attempts: int,
    wait_initial_seconds: float,
    wait_max_seconds: float,
) -> tuple[int, str]:
    """Wrap :func:`_stream_to_file` with exponential-backoff retry.

    Separated from :func:`download_to_file` so the retry count applies to
    network/transport failures only — checksum verification happens after this
    returns, in the caller, where a mismatch is retried by a different loop
    that also re-runs the download (a checksum failure means the bytes
    themselves may need to be re-fetched, not just re-hashed).

    The retry policy is constructed per call, not as a static decorator,
    specifically so tests can inject near-zero wait times. A hardcoded
    decorator with a 1-30s backoff made the test suite genuinely slow — real
    `time.sleep` calls during retry tests, not a simulated delay — which is a
    bad trade for a unit test suite that should stay fast enough to run on
    every save.
    """
    retrying = Retrying(
        retry=retry_if_exception_type(_RetryableTransferError),
        stop=stop_after_attempt(max_network_attempts),
        wait=wait_exponential_jitter(initial=wait_initial_seconds, max=wait_max_seconds),
        reraise=True,
    )
    return retrying(
        _stream_to_file, client, url, destination, chunk_bytes=chunk_bytes, timeout_seconds=timeout_seconds
    )


def download_to_file(
    url: str,
    destination: Path,
    *,
    expected_sha256: Optional[str] = None,
    max_checksum_retries: int = 3,
    chunk_bytes: int = DEFAULT_CHUNK_BYTES,
    timeout_seconds: int = 1800,
    client: Optional[httpx.Client] = None,
    max_network_attempts: int = 5,
    retry_wait_initial_seconds: float = 1.0,
    retry_wait_max_seconds: float = 30.0,
) -> DownloadResult:
    """Download a URL to a local file, retrying transient failures.

    Args:
        url: Source URL.
        destination: Local path to write to. Parent directories are created.
        expected_sha256: If given, the download is retried (up to
            ``max_checksum_retries`` times) until the computed digest matches,
            or :class:`ChecksumMismatchError` is raised.
        max_checksum_retries: Outer retry count for checksum mismatches, on top
            of the inner network-retry policy each attempt already gets.
        chunk_bytes: Streaming read/write chunk size.
        timeout_seconds: Per-request timeout.
        client: An httpx client to use. Tests supply one built on
            ``httpx.MockTransport`` for fully offline, deterministic runs; the
            caller is responsible for closing a client it constructed itself,
            since this function may be called many times against one client.
        max_network_attempts: Retry budget for transient network/5xx/429
            failures. Tests pass a near-zero ``retry_wait_*`` pair alongside
            this to keep the suite fast without changing production defaults.
        retry_wait_initial_seconds: First backoff delay.
        retry_wait_max_seconds: Backoff ceiling.

    Returns:
        The verified download result.

    Raises:
        ChecksumMismatchError: If ``expected_sha256`` never matched.
        DownloadError: If the download failed for a non-checksum reason after
            exhausting retries.

    Example:
        >>> result = download_to_file(
        ...     "https://ftp.uniprot.org/.../small.fasta",
        ...     Path("/tmp/small.fasta"),
        ...     expected_sha256="abc123...",
        ... )
    """
    destination.parent.mkdir(parents=True, exist_ok=True)
    owns_client = client is None
    active_client = client if client is not None else httpx.Client(follow_redirects=True)

    try:
        last_digest = ""
        for checksum_attempt in range(1, max_checksum_retries + 1):
            try:
                byte_count, digest = _attempt_with_retry(
                    active_client,
                    url,
                    destination,
                    chunk_bytes=chunk_bytes,
                    timeout_seconds=timeout_seconds,
                    max_network_attempts=max_network_attempts,
                    wait_initial_seconds=retry_wait_initial_seconds,
                    wait_max_seconds=retry_wait_max_seconds,
                )
            except (_RetryableTransferError, httpx.HTTPStatusError) as exc:
                _logger.error("download failed", url=url, error=str(exc))
                msg = f"download of {url} failed: {exc}"
                raise DownloadError(msg, url=url) from exc

            last_digest = digest
            if expected_sha256 is None or digest.lower() == expected_sha256.lower():
                _logger.info(
                    "download verified",
                    url=url,
                    byte_size=byte_count,
                    attempts=checksum_attempt,
                )
                return DownloadResult(
                    url=url,
                    local_path=destination,
                    sha256=digest,
                    byte_size=byte_count,
                    attempts=checksum_attempt,
                )

            _logger.warning(
                "checksum mismatch, retrying",
                url=url,
                expected=expected_sha256,
                actual=digest,
                attempt=checksum_attempt,
            )

        msg = (
            f"checksum for {url} never matched after {max_checksum_retries} attempts: "
            f"expected {expected_sha256}, last got {last_digest}"
        )
        raise ChecksumMismatchError(msg, url=url, expected=expected_sha256, actual=last_digest)
    finally:
        if owns_client:
            active_client.close()
