"""Tests for streaming checksum computation."""

from __future__ import annotations

import hashlib
from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from drugsim_ingest.checksums import sha256_file, sha256_of_chunks, verify_sha256

pytestmark = pytest.mark.unit


class TestShaOfChunks:
    """Streaming digest correctness."""

    def test_matches_hashlib_for_a_single_chunk(self) -> None:
        data = b"hello world"
        assert sha256_of_chunks([data]) == hashlib.sha256(data).hexdigest()

    def test_matches_hashlib_regardless_of_chunking(self) -> None:
        """The digest of chunked bytes must equal the digest of the whole —
        this is the property that makes streaming safe to use at all."""
        data = b"the quick brown fox jumps over the lazy dog" * 1000
        chunked = [data[i : i + 17] for i in range(0, len(data), 17)]
        assert sha256_of_chunks(chunked) == hashlib.sha256(data).hexdigest()

    def test_empty_input(self) -> None:
        assert sha256_of_chunks([]) == hashlib.sha256(b"").hexdigest()

    @given(st.binary(max_size=10_000))
    def test_property_matches_hashlib_for_arbitrary_bytes(self, data: bytes) -> None:
        assert sha256_of_chunks([data]) == hashlib.sha256(data).hexdigest()


class TestShaFile:
    """File-based digest, exercising the actual streaming read path."""

    def test_small_file(self, tmp_path: Path) -> None:
        path = tmp_path / "f.txt"
        path.write_bytes(b"drugsim")
        assert sha256_file(path) == hashlib.sha256(b"drugsim").hexdigest()

    def test_file_larger_than_chunk_size(self, tmp_path: Path) -> None:
        """Forces multiple read iterations — proves chunk boundaries don't
        corrupt the digest."""
        data = b"x" * 100
        path = tmp_path / "f.bin"
        path.write_bytes(data)
        assert sha256_file(path, chunk_bytes=7) == hashlib.sha256(data).hexdigest()

    def test_empty_file(self, tmp_path: Path) -> None:
        path = tmp_path / "empty.bin"
        path.write_bytes(b"")
        assert sha256_file(path) == hashlib.sha256(b"").hexdigest()

    def test_missing_file_raises(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            sha256_file(tmp_path / "does_not_exist.bin")


class TestVerify:
    """Checksum comparison."""

    def test_matching_digests_do_not_raise(self) -> None:
        verify_sha256("abc123", "ABC123")  # case-insensitive, must not raise

    def test_mismatched_digests_raise(self) -> None:
        with pytest.raises(ValueError, match="checksum mismatch"):
            verify_sha256("abc123", "def456")
