"""The curation pipeline against the real, committed raw data.

Closes a confirmed gap from the Phase 11 audit (docs/data-curation/current-
state.md §11): no test in the normal suite ran against the live processed
datasets at all. This one runs the real driver scripts (offline, via the
assay-metadata cache already populated in datasets/reference/ — see each
script's own module docstring) against the real, committed
datasets/raw/*.csv files, and asserts the results reconcile exactly against
build_dataset.py's own manifest counts.

These exact numbers were confirmed by hand during development, compound by
compound, before this test existed:

* hERG: 148 discordant compounds, 9589 training-eligible — both match
  herg_inhibition_dataset_manifest.json exactly.
* CYP3A4: 97 discordant compounds, 5344 training-eligible — both match
  cyp3a4_inhibition_dataset_manifest.json exactly.
* The one place the two pipelines' counts *don't* match by design: mixture
  counts. build_dataset.py only ever sees a molecule if at least one of its
  raw rows survives its own censored/bad-validity filter first, so its
  mixtures_excluded_count silently omits any mixture-flagged molecule whose
  every measurement was censored. The curation ledger checks structure for
  every molecule regardless of measurement filtering, so it finds more —
  every one of the extra ones was hand-verified to have zero uncensored,
  non-flagged rows (i.e. build_dataset.py structurally could never have
  seen it), not a bug.

This test is marked slow (full chemical standardisation over ~14,000 and
~10,000 distinct molecules) and does not require network access — the
assay-metadata cache must already exist (see each ``curate_measurements.py``
for how to populate it, or run once with network access first).
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = [pytest.mark.integration, pytest.mark.slow]


def _run_curation(endpoint_dir: str) -> None:
    script = ROOT / "models" / "admet" / endpoint_dir / "curate_measurements.py"
    result = subprocess.run(
        [sys.executable, str(script), "--no-network"],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert result.returncode == 0, f"curate_measurements.py failed:\n{result.stderr}"


class TestHergReconcilesWithTheLiveBuildPipeline:
    @pytest.fixture(scope="class", autouse=True)
    def _run(self) -> None:
        _run_curation("herg_inhibition")

    def test_discordant_count_matches_build_dataset_manifest_exactly(self) -> None:
        report = json.loads((ROOT / "datasets/curated/herg_inhibition_curation_report.json").read_text())
        build_manifest = json.loads((ROOT / "datasets/processed/herg_inhibition_dataset_manifest.json").read_text())
        assert report["funnel"]["conflict_discordant_compounds"] == build_manifest["discordant_entities_excluded_count"]

    def test_training_eligible_count_matches_final_compound_count_exactly(self) -> None:
        report = json.loads((ROOT / "datasets/curated/herg_inhibition_curation_report.json").read_text())
        build_manifest = json.loads((ROOT / "datasets/processed/herg_inhibition_dataset_manifest.json").read_text())
        assert report["funnel"]["training_eligible_compounds"] == build_manifest["final_compound_count"]

    def test_funnel_accounts_for_every_raw_record(self) -> None:
        report = json.loads((ROOT / "datasets/curated/herg_inhibition_curation_report.json").read_text())
        funnel = report["funnel"]
        assert funnel["valid_structures"] + funnel["invalid_structures_quarantined"] + funnel["mixtures_excluded"] == funnel["raw_records"]

    def test_live_datasets_processed_files_are_untouched(self) -> None:
        # The single most important invariant in this whole phase: this
        # pipeline must never modify what the live model actually trains
        # on. Re-checked here, not just asserted in the plan.
        import hashlib

        for rel_path, expected_sha in [
            ("datasets/processed/herg_inhibition_dataset.csv", None),
        ]:
            path = ROOT / rel_path
            manifest = json.loads((ROOT / "datasets/processed/herg_inhibition_dataset_manifest.json").read_text())
            actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            assert actual_sha == manifest["output_sha256"], f"{rel_path} was modified -- this must never happen"


class TestCyp3a4ReconcilesWithTheLiveBuildPipeline:
    @pytest.fixture(scope="class", autouse=True)
    def _run(self) -> None:
        _run_curation("cyp3a4_inhibition")

    def test_discordant_count_matches_build_dataset_manifest_exactly(self) -> None:
        report = json.loads((ROOT / "datasets/curated/cyp3a4_inhibition_curation_report.json").read_text())
        build_manifest = json.loads((ROOT / "datasets/processed/cyp3a4_inhibition_dataset_manifest.json").read_text())
        assert report["funnel"]["conflict_discordant_compounds"] == build_manifest["discordant_entities_excluded_count"]

    def test_training_eligible_count_matches_final_compound_count_exactly(self) -> None:
        report = json.loads((ROOT / "datasets/curated/cyp3a4_inhibition_curation_report.json").read_text())
        build_manifest = json.loads((ROOT / "datasets/processed/cyp3a4_inhibition_dataset_manifest.json").read_text())
        assert report["funnel"]["training_eligible_compounds"] == build_manifest["final_compound_count"]

    def test_live_datasets_processed_file_is_untouched(self) -> None:
        import hashlib

        path = ROOT / "datasets/processed/cyp3a4_inhibition_dataset.csv"
        manifest = json.loads((ROOT / "datasets/processed/cyp3a4_inhibition_dataset_manifest.json").read_text())
        actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
        assert actual_sha == manifest["output_sha256"], "cyp3a4_inhibition_dataset.csv was modified -- this must never happen"
