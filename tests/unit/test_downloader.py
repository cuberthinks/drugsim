"""Tests for HTTP download, retry, and streaming checksum verification.

Uses httpx.MockTransport for fully offline, deterministic testing of the retry
and checksum logic — the behaviour that actually needs exhaustive coverage. A
single real-network test against a live source lives in
tests/integration/test_downloader_live.py, proving the mocked path matches
reality rather than only itself.
"""

from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import httpx
import pytest

from drugsim_ingest.downloader import (
    ChecksumMismatchError,
    DownloadError,
    DownloadResult,
)
from drugsim_ingest.downloader import download_to_file as _download_to_file_prod

pytestmark = pytest.mark.unit

CONTENT = b"the quick brown fox jumps over the lazy dog"
CONTENT_SHA = hashlib.sha256(CONTENT).hexdigest()


def _client(transport: httpx.MockTransport) -> httpx.Client:
    return httpx.Client(transport=transport)


def download_to_file(*args: Any, **kwargs: Any) -> DownloadResult:  # noqa: ANN401
    """Test-local wrapper forcing near-zero retry backoff.

    Every retry test in this file exercises tenacity's retry COUNT, never its
    timing. Without this, the production defaults (1-30s exponential backoff)
    make retry tests sleep for real — the suite went from milliseconds to over
    20 seconds once the retry-exhaustion and checksum-mismatch-retry tests were
    added. Callers may still override retry_wait_* explicitly if a specific
    test needs to.
    """
    kwargs.setdefault("retry_wait_initial_seconds", 0.001)
    kwargs.setdefault("retry_wait_max_seconds", 0.01)
    return _download_to_file_prod(*args, **kwargs)


class TestSuccessfulDownload:
    """The straightforward path."""

    def test_downloads_and_verifies_checksum(self, tmp_path: Path) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=CONTENT))
        dest = tmp_path / "file.bin"

        result = download_to_file(
            "http://test/file", dest, expected_sha256=CONTENT_SHA, client=_client(transport)
        )

        assert result.sha256 == CONTENT_SHA
        assert result.byte_size == len(CONTENT)
        assert result.attempts == 1
        assert dest.read_bytes() == CONTENT

    def test_no_expected_checksum_still_computes_one(self, tmp_path: Path) -> None:
        """Even without verification, the digest is always computed and returned
        — every downstream consumer needs it for provenance regardless."""
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=CONTENT))
        result = download_to_file("http://test/file", tmp_path / "f.bin", client=_client(transport))
        assert result.sha256 == CONTENT_SHA

    def test_creates_parent_directories(self, tmp_path: Path) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=CONTENT))
        dest = tmp_path / "a" / "b" / "c" / "file.bin"
        download_to_file("http://test/file", dest, client=_client(transport))
        assert dest.exists()


class TestRetryOnTransientFailure:
    """5xx and 429 responses are retried; the download eventually succeeds."""

    def test_recovers_after_two_server_errors(self, tmp_path: Path) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 3:
                return httpx.Response(503)
            return httpx.Response(200, content=CONTENT)

        result = download_to_file(
            "http://test/flaky",
            tmp_path / "f.bin",
            expected_sha256=CONTENT_SHA,
            client=_client(httpx.MockTransport(handler)),
        )
        assert attempts["count"] == 3
        assert result.sha256 == CONTENT_SHA

    def test_recovers_after_rate_limiting(self, tmp_path: Path) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            if attempts["count"] < 2:
                return httpx.Response(429)
            return httpx.Response(200, content=CONTENT)

        download_to_file(
            "http://test/limited", tmp_path / "f.bin", client=_client(httpx.MockTransport(handler))
        )
        assert attempts["count"] == 2

    def test_gives_up_after_exhausting_retries(self, tmp_path: Path) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(503))
        with pytest.raises(DownloadError, match="failed"):
            download_to_file("http://test/always-down", tmp_path / "f.bin", client=_client(transport))


class TestNonRetryablePermanentFailure:
    """A 404 is reported immediately, not retried five times first."""

    def test_404_raises_without_retrying(self, tmp_path: Path) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(404)

        with pytest.raises(DownloadError):
            download_to_file("http://test/missing", tmp_path / "f.bin", client=_client(httpx.MockTransport(handler)))

        assert attempts["count"] == 1, "a 404 must not be retried like a transient failure"


class TestChecksumMismatch:
    """A persistent mismatch is reported distinctly from a network failure."""

    def test_persistent_mismatch_raises_checksum_error(self, tmp_path: Path) -> None:
        transport = httpx.MockTransport(lambda request: httpx.Response(200, content=CONTENT))
        wrong_checksum = "0" * 64

        with pytest.raises(ChecksumMismatchError, match="never matched"):
            download_to_file(
                "http://test/file",
                tmp_path / "f.bin",
                expected_sha256=wrong_checksum,
                max_checksum_retries=2,
                client=_client(transport),
            )

    def test_mismatch_retries_the_configured_number_of_times(self, tmp_path: Path) -> None:
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            return httpx.Response(200, content=CONTENT)

        with pytest.raises(ChecksumMismatchError):
            download_to_file(
                "http://test/file",
                tmp_path / "f.bin",
                expected_sha256="0" * 64,
                max_checksum_retries=4,
                client=_client(httpx.MockTransport(handler)),
            )
        assert attempts["count"] == 4

    def test_correcting_itself_on_a_later_attempt_succeeds(self, tmp_path: Path) -> None:
        """Simulates transient corruption: wrong content once, correct after."""
        attempts = {"count": 0}

        def handler(request: httpx.Request) -> httpx.Response:
            attempts["count"] += 1
            content = b"corrupted garbage" if attempts["count"] == 1 else CONTENT
            return httpx.Response(200, content=content)

        result = download_to_file(
            "http://test/file",
            tmp_path / "f.bin",
            expected_sha256=CONTENT_SHA,
            max_checksum_retries=3,
            client=_client(httpx.MockTransport(handler)),
        )
        assert result.sha256 == CONTENT_SHA
        assert attempts["count"] == 2
