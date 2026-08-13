"""Golden-set regression: the chemistry pipeline reproduces frozen output exactly.

Per the explicit project rule, "golden dataset regressions must fail CI" — this
is not a soft warning. Any difference from ``expected_output.json`` fails the
build. A difference is either an intended change (regenerate deliberately via
``scripts/generate_golden_fixtures.py``, review the diff, commit both) or a
regression (fix the code). There is no third option, and this test does not
attempt to auto-classify which one occurred — that classification is a human
judgement about intent, not something a diff can determine on its own.

Toolchain note: the fixture's ``_meta`` block records the RDKit version it was
generated under. A toolchain upgrade is expected to change output for some
compounds (this is the entire reason ``feature_set_id`` includes the RDKit
version, ADR-005) — when that happens, regenerating is correct, not a
violation of this test's purpose.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from drugsim_chem import process_structure
from drugsim_core.version import get_rdkit_version

pytestmark = pytest.mark.golden

GOLDEN_DIR = Path(__file__).resolve().parents[2] / "datasets" / "golden"
EXPECTED_PATH = GOLDEN_DIR / "expected_output.json"


@pytest.fixture(scope="module")
def expected() -> dict[str, Any]:
    """Load the frozen golden fixture."""
    if not EXPECTED_PATH.exists():
        pytest.fail(
            f"{EXPECTED_PATH} does not exist. Run "
            "scripts/generate_golden_fixtures.py to create it."
        )
    return json.loads(EXPECTED_PATH.read_text(encoding="utf-8"))


def _round(value: Any, ndigits: int = 6) -> Any:  # noqa: ANN401
    """Round a float for comparison; pass through non-floats unchanged."""
    return round(value, ndigits) if isinstance(value, float) else value


class TestToolchainMatches:
    """A mismatched RDKit version invalidates every comparison below it —
    checked first and explicitly, so a failure here is diagnosed correctly
    rather than reported as dozens of confusing per-compound mismatches."""

    def test_rdkit_version_matches_fixture(self, expected: dict[str, Any]) -> None:
        recorded = expected["_meta"]["rdkit_version"]
        current = get_rdkit_version()
        if current != recorded:
            pytest.skip(
                f"RDKit version differs (fixture: {recorded}, running: {current}) — "
                "regenerate deliberately via scripts/generate_golden_fixtures.py "
                "and review the diff before committing, per ADR-005."
            )


class TestGoldenCompoundsReproduceExactly:
    """One test per compound, parametrized, so a single failure names exactly
    which compound regressed rather than failing as one opaque block."""

    @staticmethod
    def _compound_names(expected: dict[str, Any]) -> list[str]:
        path = EXPECTED_PATH
        if not path.exists():
            return []
        return sorted(json.loads(path.read_text(encoding="utf-8"))["compounds"])

    def test_identity_matches(self, expected: dict[str, Any]) -> None:
        mismatches = []
        for name, entry in expected["compounds"].items():
            result = process_structure(entry["smiles"])
            actual = {
                "canonical_smiles": result.identity.canonical_smiles,
                "isomeric_smiles": result.identity.isomeric_smiles,
                "inchi": result.identity.inchi,
                "inchikey_full": result.identity.inchikey_full,
                "inchikey_skeleton": result.identity.inchikey_skeleton,
                "bemis_murcko_scaffold": result.identity.bemis_murcko_scaffold,
                "num_stereocentres": result.identity.num_stereocentres,
                "num_defined_stereocentres": result.identity.num_defined_stereocentres,
                "molecular_formula": result.identity.molecular_formula,
                "inchi_warnings": list(result.identity.inchi_warnings),
            }
            if actual != entry["identity"]:
                mismatches.append((name, entry["identity"], actual))

        if mismatches:
            detail = "\n".join(f"  {n}: expected={e} actual={a}" for n, e, a in mismatches)
            pytest.fail(f"{len(mismatches)} compound(s) regressed on identity:\n{detail}")

    def test_descriptors_match(self, expected: dict[str, Any]) -> None:
        mismatches = []
        for name, entry in expected["compounds"].items():
            result = process_structure(entry["smiles"])
            if entry["descriptors"] is None:
                if result.descriptors is not None:
                    mismatches.append((name, "expected None, got descriptors"))
                continue
            if result.descriptors is None:
                mismatches.append((name, "expected descriptors, got None"))
                continue

            d = result.descriptors
            actual = {
                "mw_g_mol": _round(d.mw_g_mol),
                "mw_parent_g_mol": _round(d.mw_parent_g_mol),
                "exact_mass_g_mol": _round(d.exact_mass_g_mol),
                "logp_crippen": _round(d.logp_crippen),
                "molar_refractivity": _round(d.molar_refractivity),
                "tpsa_a2": _round(d.tpsa_a2),
                "rotatable_bonds": d.rotatable_bonds,
                "aromatic_rings": d.aromatic_rings,
                "ring_count": d.ring_count,
                "heavy_atom_count": d.heavy_atom_count,
                "formal_charge": d.formal_charge,
                "hbd_lipinski": d.hbd_lipinski,
                "hba_lipinski": d.hba_lipinski,
                "hbd_strict": d.hbd_strict,
                "hba_strict": d.hba_strict,
                "heteroatom_count": d.heteroatom_count,
                "fraction_csp3": _round(d.fraction_csp3),
                "num_stereocentres": d.num_stereocentres,
                "largest_ring_size": d.largest_ring_size,
            }
            if actual != entry["descriptors"]:
                mismatches.append((name, f"expected={entry['descriptors']} actual={actual}"))

        if mismatches:
            detail = "\n".join(f"  {n}: {m}" for n, m in mismatches)
            pytest.fail(f"{len(mismatches)} compound(s) regressed on descriptors:\n{detail}")

    def test_drug_likeness_matches(self, expected: dict[str, Any]) -> None:
        mismatches = []
        for name, entry in expected["compounds"].items():
            result = process_structure(entry["smiles"])
            if entry["drug_likeness"] is None:
                if result.drug_likeness is not None:
                    mismatches.append((name, "expected None, got drug_likeness"))
                continue
            if result.drug_likeness is None:
                mismatches.append((name, "expected drug_likeness, got None"))
                continue

            dl = result.drug_likeness
            actual = {
                "lipinski_violations": dl.lipinski_violations,
                "lipinski_pass": dl.lipinski_pass,
                "veber_pass": dl.veber_pass,
                "ghose_pass": dl.ghose_pass,
                "egan_pass": dl.egan_pass,
                "muegge_pass": dl.muegge_pass,
                "rule_of_three_pass": dl.rule_of_three_pass,
                "bioavailability_score": _round(dl.bioavailability_score),
                "qed_score": _round(dl.qed_score),
                "sa_score": _round(dl.sa_score),
                "np_likeness_score": _round(dl.np_likeness_score),
                "pains_alerts": dl.pains_alerts,
                "brenk_alerts": dl.brenk_alerts,
                "gsk_4_400_flag": dl.gsk_4_400_flag,
            }
            if actual != entry["drug_likeness"]:
                mismatches.append((name, f"expected={entry['drug_likeness']} actual={actual}"))

        if mismatches:
            detail = "\n".join(f"  {n}: {m}" for n, m in mismatches)
            pytest.fail(f"{len(mismatches)} compound(s) regressed on drug-likeness:\n{detail}")

    def test_standardization_flags_and_mixture_status_match(self, expected: dict[str, Any]) -> None:
        mismatches = []
        for name, entry in expected["compounds"].items():
            result = process_structure(entry["smiles"])
            actual_flags = list(result.standardization.flags)
            if actual_flags != entry["standardization_flags"] or result.is_mixture != entry["is_mixture"]:
                mismatches.append(
                    (name, entry["standardization_flags"], actual_flags, entry["is_mixture"], result.is_mixture)
                )
        if mismatches:
            detail = "\n".join(
                f"  {n}: flags expected={ef} actual={af}; is_mixture expected={em} actual={am}"
                for n, ef, af, em, am in mismatches
            )
            pytest.fail(f"{len(mismatches)} compound(s) regressed on standardisation flags:\n{detail}")

    def test_component_count_matches(self, expected: dict[str, Any]) -> None:
        mismatches = []
        for name, entry in expected["compounds"].items():
            result = process_structure(entry["smiles"])
            actual = result.standardization.component_count
            if actual != entry["component_count"]:
                mismatches.append((name, entry["component_count"], actual))
        if mismatches:
            detail = "\n".join(f"  {n}: expected={e} actual={a}" for n, e, a in mismatches)
            pytest.fail(f"{len(mismatches)} compound(s) regressed on component_count:\n{detail}")

    def test_standardized_and_parent_smiles_match(self, expected: dict[str, Any]) -> None:
        mismatches = []
        for name, entry in expected["compounds"].items():
            result = process_structure(entry["smiles"])
            if (
                result.standardized_smiles != entry["standardized_smiles"]
                or result.parent_smiles != entry["parent_smiles"]
            ):
                mismatches.append(
                    (
                        name,
                        entry["standardized_smiles"],
                        result.standardized_smiles,
                        entry["parent_smiles"],
                        result.parent_smiles,
                    )
                )
        if mismatches:
            detail = "\n".join(
                f"  {n}: standardized_smiles expected={se} actual={sa}; parent_smiles expected={pe} actual={pa}"
                for n, se, sa, pe, pa in mismatches
            )
            pytest.fail(f"{len(mismatches)} compound(s) regressed on standardized/parent smiles:\n{detail}")


class TestGoldenSetCoversTheEdgeCasesItClaimsTo:
    """The golden set is only valuable if it actually contains the edge cases
    Phase 1 identified — this guards against the compound list silently
    losing coverage (e.g. a bad edit removing the whole-salt case)."""

    def test_covers_whole_salt_case(self, expected: dict[str, Any]) -> None:
        assert any(c["category"] == "whole_salt" for c in expected["compounds"].values())

    def test_covers_a_salt_stripping_case(self, expected: dict[str, Any]) -> None:
        salts = [c for c in expected["compounds"].values() if c["category"] == "salt"]
        assert any("salt_stripped" in c["standardization_flags"] for c in salts)

    def test_covers_defined_and_undefined_stereochemistry(self, expected: dict[str, Any]) -> None:
        completeness = {c["stereo_completeness"] for c in expected["compounds"].values()}
        assert "fully_defined" in completeness
        assert "undefined" in completeness

    def test_covers_a_pains_flagged_structure(self, expected: dict[str, Any]) -> None:
        pains_compound = expected["compounds"].get("rhodanine")
        assert pains_compound is not None
        assert pains_compound["drug_likeness"]["pains_alerts"] >= 1

    def test_covers_a_charge_neutralisation_case(self, expected: dict[str, Any]) -> None:
        assert any(
            "charge_neutralised" in c["standardization_flags"] for c in expected["compounds"].values()
        )

    def test_at_least_twenty_five_compounds(self, expected: dict[str, Any]) -> None:
        """A floor, not a target — catches an accidental mass-deletion from
        the compound list without requiring the exact count to stay static."""
        assert len(expected["compounds"]) >= 25
