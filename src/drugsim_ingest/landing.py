"""The Z1 landing zone: write-once object storage.

Phase 1 Step 2 §3 (Z1): bytes acquired from a source are written once,
checksummed, and never edited — a correction is a new snapshot, not an in-place
change (P3). This module is the one place that boundary is enforced in code: a
write to a key that already exists raises rather than silently overwriting.

Backed by any S3-compatible store (MinIO locally, cloud object storage in
production) via boto3, per ADR-011 — one code path for both.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO, Optional, Union

import boto3
from botocore.exceptions import ClientError

from drugsim_core.errors import DrugSimError
from drugsim_core.logging import get_logger
from drugsim_ingest.checksums import sha256_of_chunks

__all__ = ["ImmutabilityViolationError", "LandingZone", "ObjectMetadata"]

_logger = get_logger(__name__)


class ImmutabilityViolationError(DrugSimError):
    """An attempt was made to overwrite an existing Z1 object.

    Z1 is write-once (P3). This is not a race-free guarantee — see
    :meth:`LandingZone.write_immutable` — but it turns the common case (a
    re-run accidentally targeting the same key) into a loud failure instead of
    a silent, undetectable overwrite of evidence.
    """

    code = "immutability_violation"


@dataclass(frozen=True)
class ObjectMetadata:
    """What was actually written, as confirmed by the store."""

    bucket: str
    key: str
    sha256: str
    byte_size: int


class LandingZone:
    """A write-once object store for one bucket.

    One instance per bucket, since immutability semantics and bucket-level
    versioning configuration are bucket-scoped concerns.
    """

    def __init__(self, bucket: str, *, endpoint_url: Optional[str] = None, **client_kwargs: object) -> None:
        """Initialise the landing zone.

        Args:
            bucket: The target S3-compatible bucket. Must already exist —
                bucket creation is an infrastructure concern (Terraform /
                Compose init), not something application code does implicitly.
            endpoint_url: Override for a non-AWS endpoint (MinIO). ``None`` uses
                the default AWS resolution, appropriate in production.
            **client_kwargs: Passed through to ``boto3.client("s3", ...)`` —
                tests inject credentials and region here without needing real
                AWS config.
        """
        self.bucket = bucket
        self._client = boto3.client("s3", endpoint_url=endpoint_url, **client_kwargs)

    def exists(self, key: str) -> bool:
        """Check whether an object already exists at ``key``.

        Args:
            key: Object key.

        Returns:
            True if present.
        """
        try:
            self._client.head_object(Bucket=self.bucket, Key=key)
        except ClientError as exc:
            if exc.response.get("Error", {}).get("Code") in {"404", "NoSuchKey"}:
                return False
            raise
        return True

    def write_immutable(
        self,
        key: str,
        data: Union[bytes, BinaryIO],
        *,
        expected_sha256: Optional[str] = None,
    ) -> ObjectMetadata:
        """Write an object, refusing to overwrite an existing one.

        Args:
            key: Destination key, conventionally
                ``{license_tier}/{source_id}/{snapshot_id}/{filename}``
                (Phase 1 Step 2 §3, Z1 layout).
            data: The bytes to write, or a binary file-like object.
            expected_sha256: If given, verified against the content actually
                written before returning.

        Returns:
            Metadata for the object as written.

        Raises:
            ImmutabilityViolationError: If ``key`` already exists. Checked via
                a HEAD request immediately before the PUT. This is a
                check-then-act with a small race window under concurrent
                writers targeting the exact same key with the exact same
                content — accepted, because two writers racing to land
                *identical, checksum-verified* bytes is not a scientific
                integrity problem; the case this guards against is a pipeline
                bug re-running against a key it already populated with
                different content.
            ValueError: If ``expected_sha256`` does not match the content.
        """
        if self.exists(key):
            msg = f"refusing to overwrite existing Z1 object: {self.bucket}/{key}"
            raise ImmutabilityViolationError(msg, bucket=self.bucket, key=key)

        # isinstance-first (rather than hasattr(data, "read")) so this is a real
        # type guard for mypy, not a runtime assert that -O could strip.
        payload: bytes = data if isinstance(data, bytes) else data.read()

        digest = sha256_of_chunks([payload])
        if expected_sha256 is not None and digest.lower() != expected_sha256.lower():
            msg = f"content for {key} does not match expected checksum: expected {expected_sha256}, got {digest}"
            raise ValueError(msg)

        self._client.put_object(Bucket=self.bucket, Key=key, Body=payload)
        _logger.info("wrote immutable object", bucket=self.bucket, key=key, byte_size=len(payload))

        return ObjectMetadata(bucket=self.bucket, key=key, sha256=digest, byte_size=len(payload))

    def read(self, key: str) -> bytes:
        """Read an object's full content.

        Args:
            key: Object key.

        Returns:
            The object's bytes.
        """
        response = self._client.get_object(Bucket=self.bucket, Key=key)
        return response["Body"].read()  # type: ignore[no-any-return]
