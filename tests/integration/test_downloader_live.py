"""One real download against a live source.

Every other downloader test uses httpx.MockTransport (tests/unit/test_downloader.py)
— fast, deterministic, and exhaustive over retry/checksum edge cases, but proves
only that the code does what the mock says a server does. This file proves the
mocked behaviour matches an actual server: real TLS, real chunked transfer, real
DNS.

Target: RCSB PDB entry 1CRN (crambin) — a well-known, structurally tiny (46
residues) protein whose deposited coordinate file has been stable for decades
and is ~48 KB. Verified reachable and its checksum recorded during Sprint 2.4
authoring (2026-08-06); if RCSB ever changes the file layout for a 45-year-old
deposited structure, that is itself worth knowing about.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from drugsim_ingest.downloader import download_to_file

pytestmark = [pytest.mark.integration, pytest.mark.network]

_1CRN_URL = "https://files.rcsb.org/download/1CRN.pdb"
_1CRN_SHA256 = "42199a30a0701864a2a5cc76cd7f35cc544cd0e65fbcf63e03c166543249b811"


class TestRealDownload:
    """Confirms the downloader works against an actual HTTPS server."""

    def test_downloads_and_verifies_a_real_file(self, tmp_path: Path) -> None:
        dest = tmp_path / "1CRN.pdb"
        result = download_to_file(_1CRN_URL, dest, expected_sha256=_1CRN_SHA256)

        assert result.sha256 == _1CRN_SHA256
        assert result.attempts == 1
        assert dest.exists()
        assert dest.read_bytes().startswith(b"HEADER")

    def test_a_real_404_is_reported_as_download_error(self, tmp_path: Path) -> None:
        from drugsim_ingest.downloader import DownloadError

        with pytest.raises(DownloadError):
            download_to_file(
                "https://files.rcsb.org/download/DOES-NOT-EXIST-9999.pdb",
                tmp_path / "missing.pdb",
            )
