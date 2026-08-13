"""Streaming checksum computation.

A ChEMBL-scale download is gigabytes. Computing a checksum by reading the whole
file into memory first would work for a test fixture and fail in production; this
module always operates on a stream so memory use is bounded by the chunk size,
not the file size.
"""

from __future__ import annotations

import hashlib
from collections.abc import Iterable, Iterator
from pathlib import Path
from typing import BinaryIO

__all__ = ["DEFAULT_CHUNK_BYTES", "sha256_file", "sha256_of_chunks", "verify_sha256"]

#: 8 MiB — large enough to keep syscall overhead low, small enough to bound
#: memory use on any file size.
DEFAULT_CHUNK_BYTES = 8 * 1024 * 1024


def sha256_of_chunks(chunks: Iterable[bytes]) -> str:
    """Compute the SHA-256 digest of a sequence of byte chunks.

    Args:
        chunks: An iterable of byte chunks, in order.

    Returns:
        The lowercase hex digest.
    """
    digest = hashlib.sha256()
    for chunk in chunks:
        digest.update(chunk)
    return digest.hexdigest()


def _iter_stream(stream: BinaryIO, chunk_bytes: int) -> Iterator[bytes]:
    """Yield fixed-size chunks from a binary stream until exhausted."""
    while chunk := stream.read(chunk_bytes):
        yield chunk


def sha256_file(path: Path, *, chunk_bytes: int = DEFAULT_CHUNK_BYTES) -> str:
    """Compute the SHA-256 digest of a file on disk, streaming.

    Args:
        path: File to digest.
        chunk_bytes: Read size per iteration.

    Returns:
        The lowercase hex digest.

    Raises:
        FileNotFoundError: If ``path`` does not exist.
    """
    with path.open("rb") as handle:
        return sha256_of_chunks(_iter_stream(handle, chunk_bytes))


def verify_sha256(actual: str, expected: str) -> None:
    """Raise if two digests do not match, comparing case-insensitively.

    Args:
        actual: The computed digest.
        expected: The digest to compare against (e.g. from a source's published
            checksum file, or ``ingestion_snapshot.content_sha256``).

    Raises:
        ValueError: If the digests differ.
    """
    if actual.lower() != expected.lower():
        msg = f"checksum mismatch: expected {expected}, got {actual}"
        raise ValueError(msg)
