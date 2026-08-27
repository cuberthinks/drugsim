"""Golden-set regression: the curation pipeline reproduces frozen output exactly.

Separate fixture and test from ``test_golden_regression.py`` (the
chemistry-only golden set) — see
``scripts/generate_curation_golden_fixtures.py`` for why they are
deliberately kept independent. This test re-runs the real pipeline (via
that script's ``run_golden_curation()`` — the exact same call the live
driver scripts make through ``drugsim_curation.pipeline.curate_raw_rows``)
fresh, on every run, and compares the live result against the frozen
``expected_curation_output.json``. A mismatch is either an intended,
reviewed change (regenerate via that script) or a regression (fix the
code) — this test does not classify which.

This file also doubles as documentation-by-example of every curation edge
case this phase was built to handle.
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path
from typing import Any

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from generate_curation_golden_fixtures import run_golden_curation  # noqa: E402

pytestmark = pytest.mark.golden

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "datasets" / "golden"
EXPECTED_PATH = GOLDEN_DIR / "expected_curation_output.json"


@pytest.fixture(scope="module")
def expected() -> dict[str, Any]:
    """Load the frozen curation golden fixture."""
    if not EXPECTED_PATH.exists():
        pytest.fail(f"{EXPECTED_PATH} does not exist. Run scripts/generate_curation_golden_fixtures.py to create it.")
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def actual() -> dict[str, Any]:
    """Re-run the real pipeline fresh -- this is the live half of the comparison."""
    result = run_golden_curation()
    return {
        "ledger_rows": {row.measurement_id: dataclasses.asdict(row) for row in result.ledger_rows},
        "curated_compounds": {
            c.compound_id: {
                "compound_id": c.compound_id,
                "n_source_measurements_total": c.n_source_measurements_total,
                "n_source_measurements_used": c.n_source_measurements_used,
                "aggregated_ic50_nm": c.aggregated_ic50_nm,
                "aggregation_method": c.aggregation_method,
                "value_spread_log10": c.value_spread_log10,
                "is_discordant": c.is_discordant,
                "conflict_status": c.conflict_status,
                "label": c.label,
                "training_eligible": c.training_eligible,
                "exclusion_reason": c.exclusion_reason,
                "data_quality_score": round(c.quality.total, 6),
                "measurement_ids": c.measurement_ids,
            }
            for c in result.curated_compounds
        },
    }


def _round(value: Any, ndigits: int = 6) -> Any:  # noqa: ANN401
    return round(value, ndigits) if isinstance(value, float) else value


class TestFreshRunMatchesFrozenFixtureExactly:
    """The actual regression check: live output vs. frozen output, field by field."""

    def test_every_ledger_row_matches(self, expected: dict[str, Any], actual: dict[str, Any]) -> None:
        mismatches = []
        assert set(actual["ledger_rows"]) == set(expected["ledger_rows"]), "measurement_id set itself changed"
        for measurement_id, expected_row in expected["ledger_rows"].items():
            actual_row = {k: _round(v) for k, v in actual["ledger_rows"][measurement_id].items()}
            expected_row_rounded = {k: _round(v) for k, v in expected_row.items()}
            if actual_row != expected_row_rounded:
                diff = {
                    k: (expected_row_rounded[k], actual_row[k])
                    for k in expected_row_rounded
                    if expected_row_rounded[k] != actual_row.get(k)
                }
                mismatches.append((measurement_id, diff))
        if mismatches:
            detail = "\n".join(f"  {mid}: {d}" for mid, d in mismatches)
            pytest.fail(f"{len(mismatches)} ledger row(s) regressed:\n{detail}")

    def test_every_curated_compound_matches(self, expected: dict[str, Any], actual: dict[str, Any]) -> None:
        mismatches = []
        assert set(actual["curated_compounds"]) == set(expected["curated_compounds"]), "compound_id set itself changed"
        for compound_id, expected_row in expected["curated_compounds"].items():
            actual_row = actual["curated_compounds"][compound_id]
            if actual_row != expected_row:
                diff = {k: (expected_row[k], actual_row[k]) for k in expected_row if expected_row[k] != actual_row.get(k)}
                mismatches.append((compound_id, diff))
        if mismatches:
            detail = "\n".join(f"  {cid}: {d}" for cid, d in mismatches)
            pytest.fail(f"{len(mismatches)} curated compound(s) regressed:\n{detail}")


def _compound_by_measurement(actual: dict[str, Any], measurement_id: str) -> dict[str, Any]:
    row = actual["ledger_rows"][measurement_id]
    return actual["curated_compounds"][row["compound_id"]]


class TestExactDuplicateIsRetainedAndTagged:
    """Two identical aspirin measurements: both kept, tagged, both used."""

    def test_both_rows_survive(self, actual: dict[str, Any]) -> None:
        row_a = actual["ledger_rows"]["golden_measurements:G001"]
        row_b = actual["ledger_rows"]["golden_measurements:G002"]
        assert row_a["curation_status"] == "included"
        assert row_b["curation_status"] == "included"

    def test_one_is_the_representative_and_one_is_tagged_duplicate(self, actual: dict[str, Any]) -> None:
        roles = {
            actual["ledger_rows"]["golden_measurements:G001"]["duplicate_role"],
            actual["ledger_rows"]["golden_measurements:G002"]["duplicate_role"],
        }
        assert roles == {"representative", "duplicate"}

    def test_the_compound_uses_both_measurements_not_one(self, actual: dict[str, Any]) -> None:
        compound = _compound_by_measurement(actual, "golden_measurements:G001")
        assert compound["n_source_measurements_used"] == 2


class TestStructuralDuplicateAcrossChemblIds:
    """Two different molecule_chembl_ids, identical structure: merged to one compound."""

    def test_both_measurements_merge_into_one_compound(self, actual: dict[str, Any]) -> None:
        compound_a = _compound_by_measurement(actual, "golden_measurements:G003")
        compound_b = _compound_by_measurement(actual, "golden_measurements:G004")
        assert compound_a["compound_id"] == compound_b["compound_id"]
        assert compound_a["n_source_measurements_used"] == 2

    def test_aggregated_value_is_the_geometric_mean(self, actual: dict[str, Any]) -> None:
        compound = _compound_by_measurement(actual, "golden_measurements:G003")
        assert compound["aggregated_ic50_nm"] == pytest.approx(54.7723, abs=1e-3)
        assert compound["is_discordant"] is False


class TestSaltEquivalentDuplicate:
    """Triethylamine HCl and its free base standardise to the same parent."""

    def test_salt_and_free_base_merge_into_one_compound(self, actual: dict[str, Any]) -> None:
        salt_compound = _compound_by_measurement(actual, "golden_measurements:G005")
        free_compound = _compound_by_measurement(actual, "golden_measurements:G006")
        assert salt_compound["compound_id"] == free_compound["compound_id"]
        assert salt_compound["n_source_measurements_used"] == 2


class TestDiscordantPairIsRetainedNotDropped:
    """The defining property of this whole phase: discordance is visible, not silent."""

    def test_the_pair_is_flagged_discordant(self, actual: dict[str, Any]) -> None:
        compound = _compound_by_measurement(actual, "golden_measurements:G007")
        assert compound["is_discordant"] is True
        assert compound["conflict_status"] == "discordant"

    def test_discordant_compound_is_training_ineligible_but_still_present(self, actual: dict[str, Any]) -> None:
        compound = _compound_by_measurement(actual, "golden_measurements:G007")
        assert compound["training_eligible"] is False
        assert compound["exclusion_reason"] == "discordant_gt_10x"
        assert compound["aggregated_ic50_nm"] is not None
        assert compound["data_quality_score"] is not None

    def test_both_contributing_measurements_are_tagged_discordant(self, actual: dict[str, Any]) -> None:
        row_a = actual["ledger_rows"]["golden_measurements:G007"]
        row_b = actual["ledger_rows"]["golden_measurements:G008"]
        assert row_a["conflict_status"] == "discordant"
        assert row_b["conflict_status"] == "discordant"


class TestUnresolvableUnitIsExcludedNeverGuessed:
    def test_the_measurement_is_marked_unresolved(self, actual: dict[str, Any]) -> None:
        row = actual["ledger_rows"]["golden_measurements:G009"]
        assert row["unit_status"] == "unresolved"
        assert row["exclusion_reason"] == "unresolved_unit"
        assert row["normalised_value"] is None

    def test_the_compound_has_no_usable_measurements(self, actual: dict[str, Any]) -> None:
        compound = _compound_by_measurement(actual, "golden_measurements:G009")
        assert compound["n_source_measurements_used"] == 0
        assert compound["training_eligible"] is False
        assert compound["exclusion_reason"] == "no_usable_measurements"
        assert compound["label"] is None


class TestKnownToxicAndSafeControls:
    def test_terfenadine_is_labeled_blocker(self, actual: dict[str, Any]) -> None:
        compound = _compound_by_measurement(actual, "golden_measurements:G010")
        assert compound["label"] == 1
        assert compound["training_eligible"] is True

    def test_paracetamol_is_labeled_non_blocker(self, actual: dict[str, Any]) -> None:
        compound = _compound_by_measurement(actual, "golden_measurements:G011")
        assert compound["label"] == 0
        assert compound["training_eligible"] is True


class TestInvalidStructureIsQuarantinedNeverDropped:
    def test_the_row_exists_with_the_original_data_intact(self, actual: dict[str, Any]) -> None:
        row = actual["ledger_rows"]["golden_measurements:G012"]
        assert row["structure_status"] == "invalid_quarantined"
        assert row["exclusion_reason"] == "invalid_structure"
        assert row["structure_error"] is not None
        assert row["original_value"] == "100"

    def test_no_compound_row_is_fabricated_for_an_unresolvable_structure(self, actual: dict[str, Any]) -> None:
        row = actual["ledger_rows"]["golden_measurements:G012"]
        assert row["compound_id"].startswith("UNRESOLVED:")
        assert row["compound_id"] not in actual["curated_compounds"]


class TestGenuineMixtureIsExcludedNeverDropped:
    def test_the_row_exists_and_is_flagged_mixture(self, actual: dict[str, Any]) -> None:
        row = actual["ledger_rows"]["golden_measurements:G013"]
        assert row["structure_status"] == "mixture_excluded"
        assert row["exclusion_reason"] == "mixture"


class TestGoldenSetCoversTheEdgeCasesItClaimsTo:
    """Guards against the fixture silently losing coverage over time."""

    def test_at_least_thirteen_measurement_rows(self, actual: dict[str, Any]) -> None:
        assert len(actual["ledger_rows"]) >= 13

    def test_covers_at_least_one_discordant_compound(self, actual: dict[str, Any]) -> None:
        assert any(c["is_discordant"] for c in actual["curated_compounds"].values())

    def test_covers_at_least_one_insufficient_data_compound(self, actual: dict[str, Any]) -> None:
        assert any(c["exclusion_reason"] == "no_usable_measurements" for c in actual["curated_compounds"].values())

    def test_covers_at_least_one_exact_duplicate_group(self, actual: dict[str, Any]) -> None:
        assert any(row["duplicate_role"] == "duplicate" for row in actual["ledger_rows"].values())

    def test_covers_at_least_one_invalid_structure(self, actual: dict[str, Any]) -> None:
        assert any(row["structure_status"] == "invalid_quarantined" for row in actual["ledger_rows"].values())

    def test_covers_at_least_one_genuine_mixture(self, actual: dict[str, Any]) -> None:
        assert any(row["structure_status"] == "mixture_excluded" for row in actual["ledger_rows"].values())
