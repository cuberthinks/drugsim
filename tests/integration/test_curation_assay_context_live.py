"""One real round-trip against ChEMBL's live assay.json endpoint.

Every other assay-context test uses a pre-populated cache
(tests/unit/test_curation_assay_context.py) — fast, deterministic, but
proves only that the code does what a fixture says the API returns. This
file proves the real API still matches that shape.

Target: CHEMBL240 (hERG), a small, well-known target whose assay records
have been stable. If ChEMBL ever changes this endpoint's schema, that is
itself worth knowing about.
"""

from __future__ import annotations

from pathlib import Path

import httpx
import pytest

from drugsim_curation.assay_context import fetch_assay_metadata

pytestmark = [pytest.mark.integration, pytest.mark.network]


def test_a_real_herg_assay_resolves_with_a_live_fetch(tmp_path: Path) -> None:
    cache_path = tmp_path / "cache.json"
    with httpx.Client() as client:
        # CHEMBL656375 is a real, stable hERG functional assay (verified
        # during development against the live API).
        result = fetch_assay_metadata("CHEMBL240", {"CHEMBL656375"}, cache_path=cache_path, http_client=client)
    assert "CHEMBL656375" in result
    metadata = result["CHEMBL656375"]
    assert metadata.assay_cell_type == "COS-7"
    assert metadata.paradigm in {
        "functional_electrophysiology",
        "functional_flux_fluorescence",
        "binding_displacement",
        "ambiguous_generic_inhibition",
        "other_unclassified",
    }
    # The fetch must have written a cache a later offline run can reuse.
    assert cache_path.exists()
