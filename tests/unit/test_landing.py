"""Tests for the Z1 immutable landing zone, against a mocked S3 (moto).

moto implements a real, in-process subset of the S3 API — this exercises the
actual boto3 calls LandingZone makes, not a hand-rolled fake, without needing
Docker/MinIO. Categorised as unit rather than integration because moto requires
no external service and runs in milliseconds; it earns that classification on
merit, not by fiat.
"""

from __future__ import annotations

import boto3
import pytest
from moto import mock_aws

from drugsim_ingest.landing import ImmutabilityViolationError, LandingZone

pytestmark = pytest.mark.unit

BUCKET = "drugsim-z1-landing-test"
REGION = "us-east-1"


@pytest.fixture
def landing_zone():
    """A LandingZone backed by a fresh mocked S3 bucket."""
    with mock_aws():
        client = boto3.client("s3", region_name=REGION)
        client.create_bucket(Bucket=BUCKET)
        yield LandingZone(BUCKET, region_name=REGION)


class TestWriteImmutable:
    """The write-once guarantee."""

    def test_writes_new_object(self, landing_zone: LandingZone) -> None:
        metadata = landing_zone.write_immutable("green/pdb/snap1/file.txt", b"hello")
        assert metadata.bucket == BUCKET
        assert metadata.key == "green/pdb/snap1/file.txt"
        assert metadata.byte_size == 5
        assert landing_zone.read("green/pdb/snap1/file.txt") == b"hello"

    def test_computes_correct_digest(self, landing_zone: LandingZone) -> None:
        import hashlib

        metadata = landing_zone.write_immutable("k", b"drugsim")
        assert metadata.sha256 == hashlib.sha256(b"drugsim").hexdigest()

    def test_refuses_to_overwrite_existing_key(self, landing_zone: LandingZone) -> None:
        landing_zone.write_immutable("k", b"original")
        with pytest.raises(ImmutabilityViolationError, match="refusing to overwrite"):
            landing_zone.write_immutable("k", b"replacement")
        # The original content must survive the rejected overwrite attempt.
        assert landing_zone.read("k") == b"original"

    def test_refuses_even_with_identical_content(self, landing_zone: LandingZone) -> None:
        """A second write of byte-identical content is still rejected — the
        guard is about the KEY already existing, not about content differing.
        A pipeline that re-runs against a key it already populated should
        notice, even if the content would have been the same."""
        landing_zone.write_immutable("k", b"same")
        with pytest.raises(ImmutabilityViolationError):
            landing_zone.write_immutable("k", b"same")

    def test_accepts_a_file_like_object(self, landing_zone: LandingZone) -> None:
        import io

        metadata = landing_zone.write_immutable("k", io.BytesIO(b"streamed"))
        assert metadata.byte_size == 8
        assert landing_zone.read("k") == b"streamed"

    def test_verifies_expected_checksum(self, landing_zone: LandingZone) -> None:
        import hashlib

        correct = hashlib.sha256(b"data").hexdigest()
        landing_zone.write_immutable("k", b"data", expected_sha256=correct)  # must not raise

    def test_rejects_wrong_expected_checksum(self, landing_zone: LandingZone) -> None:
        with pytest.raises(ValueError, match="does not match expected checksum"):
            landing_zone.write_immutable("k", b"data", expected_sha256="0" * 64)

    def test_wrong_checksum_does_not_write_the_object(self, landing_zone: LandingZone) -> None:
        """A failed checksum verification must not leave a corrupted object
        behind for a later reader to trust."""
        try:
            landing_zone.write_immutable("k", b"data", expected_sha256="0" * 64)
        except ValueError:
            pass
        assert not landing_zone.exists("k")


class TestExists:
    """Existence checking, the basis of the immutability guard."""

    def test_false_for_absent_key(self, landing_zone: LandingZone) -> None:
        assert landing_zone.exists("nope") is False

    def test_true_after_write(self, landing_zone: LandingZone) -> None:
        landing_zone.write_immutable("k", b"x")
        assert landing_zone.exists("k") is True


class TestRead:
    """Reading back written content."""

    def test_reads_exact_bytes_written(self, landing_zone: LandingZone) -> None:
        payload = bytes(range(256)) * 10
        landing_zone.write_immutable("k", payload)
        assert landing_zone.read("k") == payload
