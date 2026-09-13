"""Regression tests for tiered compound-identity resolution.

Covers the resolution order added for the Scientific Coverage upgrade:
exact full-InChIKey, then *unambiguous* skeleton, then unidentified.

Two rules these tests exist to defend:

  1. **Identity is never guessed.** An ambiguous skeleton (two stereoisomers
     sharing a connectivity block) must resolve as ``unidentified``, not as
     an arbitrary pick between them.
  2. **Identity never gates prediction.** An unidentified compound is a normal
     outcome, not an error.

Compound expectations here are asserted against the *committed snapshot's own
contents*, not hand-written identities -- these tests fail loudly if the
reference data changes, which is the point.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from drugsim_chem import process_structure
from drugsim_identity import (
    CompoundIdentityRecord,
    build_skeleton_index,
    load_identity_snapshot,
    resolve_identity,
)

SNAPSHOT_PATH = (
    Path(__file__).resolve().parents[2]
    / "src"
    / "drugsim_identity"
    / "data"
    / "compound_identity_snapshot.json"
)

# Structures only -- never names or identifiers. What each resolves *to* is
# read from the snapshot at test time, so nothing is hard-coded per compound.
CAFFEINE_SMILES = "Cn1cnc2c1c(=O)n(C)c(=O)n2C"
ASPIRIN_SMILES = "CC(=O)Oc1ccccc1C(=O)O"
ASPIRIN_SODIUM_SALT_SMILES = "CC(=O)Oc1ccccc1C(=O)[O-].[Na+]"
DOXORUBICIN_SMILES = (
    "COc1cccc2c1C(=O)c1c(O)c3c(c(O)c1C2=O)C[C@@](O)(C(=O)CO)C[C@@H]3O"
    "[C@H]1C[C@H](N)[C@H](O)[C@H](C)O1"
)
# A deliberately novel, valid structure: not a real drug, must still predict.
NOVEL_VALID_SMILES = "CCCCCCCCCCCCNc1ccc(C(=O)NCCCN2CCOCC2)cc1"


@pytest.fixture(scope="module")
def snapshot() -> dict[str, CompoundIdentityRecord]:
    return load_identity_snapshot(SNAPSHOT_PATH)


@pytest.fixture(scope="module")
def skeleton_index(snapshot):
    return build_skeleton_index(snapshot)


def _key(smiles: str) -> str:
    return process_structure(smiles).identity.inchikey_full


class TestExactResolution:
    def test_caffeine_resolves_by_exact_inchikey(self, snapshot, skeleton_index) -> None:
        result = resolve_identity(_key(CAFFEINE_SMILES), snapshot, skeleton_index)
        assert result.identity_status == "identified"
        assert result.match_type == "exact"
        assert result.match_caveat is None
        assert result.compound_name  # a real name from PubChem, whatever it is
        assert result.source == "PubChem"

    def test_aspirin_resolves_by_exact_inchikey(self, snapshot, skeleton_index) -> None:
        result = resolve_identity(_key(ASPIRIN_SMILES), snapshot, skeleton_index)
        assert result.identity_status == "identified"
        assert result.match_type == "exact"

    def test_identified_compound_always_carries_provenance(self, snapshot, skeleton_index) -> None:
        """No identity field is ever shown without saying where it came from."""
        result = resolve_identity(_key(CAFFEINE_SMILES), snapshot, skeleton_index)
        assert result.source == "PubChem"
        assert result.retrieved_at
        assert result.identifiers and "pubchem_cid" in result.identifiers

    def test_description_is_never_invented(self, snapshot, skeleton_index) -> None:
        """Either a real sourced description, or the fixed placeholder."""
        result = resolve_identity(_key(CAFFEINE_SMILES), snapshot, skeleton_index)
        if result.description == "Verified description unavailable.":
            assert result.description_source is None
        else:
            assert result.description_source  # a real attributed source


class TestSaltEquivalence:
    def test_salt_form_resolves_to_its_parent(self, snapshot, skeleton_index) -> None:
        """Standardisation strips the counter-ion before identity is resolved,
        so a salt and its parent are the same compound -- no skeleton tier
        needed, and no separate snapshot entry required."""
        parent = resolve_identity(_key(ASPIRIN_SMILES), snapshot, skeleton_index)
        salt = resolve_identity(_key(ASPIRIN_SODIUM_SALT_SMILES), snapshot, skeleton_index)
        assert _key(ASPIRIN_SODIUM_SALT_SMILES) == _key(ASPIRIN_SMILES)
        assert salt.compound_name == parent.compound_name
        assert salt.match_type == "exact"


class TestSkeletonTier:
    def test_unambiguous_skeleton_variant_resolves_with_a_caveat(
        self, snapshot, skeleton_index
    ) -> None:
        """A stereo/isotope variant of a uniquely-keyed snapshot compound
        resolves, but is explicitly labelled as a weaker match."""
        unique = next(
            recs[0] for recs in skeleton_index.values() if len(recs) == 1
        )
        variant_key = unique.inchikey_full[:14] + "-ZZZZZZZZZZ-N"
        assert variant_key not in snapshot  # genuinely not an exact hit

        result = resolve_identity(variant_key, snapshot, skeleton_index)
        assert result.identity_status == "identified"
        assert result.match_type == "skeleton"
        assert result.match_caveat and "connectivity" in result.match_caveat.lower()

    def test_ambiguous_skeleton_refuses_to_guess(self, snapshot, skeleton_index) -> None:
        """The safety property: where one skeleton means several compounds,
        resolution must decline rather than pick a stereoisomer at random."""
        ambiguous = [s for s, recs in skeleton_index.items() if len(recs) > 1]
        if not ambiguous:
            pytest.skip("no colliding skeletons in the committed snapshot")
        variant_key = ambiguous[0] + "-ZZZZZZZZZZ-N"
        result = resolve_identity(variant_key, snapshot, skeleton_index)
        assert result.identity_status == "unidentified"
        assert result.compound_name is None
        assert result.match_type is None

    def test_legacy_two_argument_call_stays_exact_only(self, snapshot, skeleton_index) -> None:
        """Callers that do not pass an index keep the old behaviour exactly."""
        unique = next(recs[0] for recs in skeleton_index.values() if len(recs) == 1)
        variant_key = unique.inchikey_full[:14] + "-ZZZZZZZZZZ-N"
        assert resolve_identity(variant_key, snapshot).identity_status == "unidentified"


class TestUnidentifiedIsNormal:
    def test_valid_novel_compound_is_unidentified_but_not_an_error(
        self, snapshot, skeleton_index
    ) -> None:
        """VALID + UNIDENTIFIED + PREDICTABLE is a supported state."""
        processed = process_structure(NOVEL_VALID_SMILES)  # must not raise
        result = resolve_identity(processed.identity.inchikey_full, snapshot, skeleton_index)
        assert result.identity_status == "unidentified"
        assert result.compound_name is None
        assert result.match_caveat is None

    def test_doxorubicin_documents_a_real_coverage_gap(self, snapshot, skeleton_index) -> None:
        """Doxorubicin is a well-known drug that DrugSim currently cannot name.

        This is not a bug in resolution -- it is the reference set's scope.
        The snapshot is seeded from compounds *named in DrugSim's own hERG and
        CYP3A4 assay files*; a drug that appears in neither assay is absent no
        matter how good the matching is. See
        ``docs/scientific-coverage/compound-identity-coverage.md``.

        If this test starts failing, the reference set has been broadened --
        update the coverage report rather than deleting the test.
        """
        result = resolve_identity(_key(DOXORUBICIN_SMILES), snapshot, skeleton_index)
        assert result.identity_status == "unidentified", (
            "Doxorubicin now resolves -- reference coverage changed. Re-run "
            "scripts/scientific_coverage/02_identity_coverage.py and update the "
            "coverage report."
        )


class TestSnapshotDegradesGracefully:
    def test_missing_snapshot_file_yields_unidentified_not_a_crash(self, tmp_path: Path) -> None:
        """An identity-data outage must never take prediction down with it."""
        empty = load_identity_snapshot(tmp_path / "absent.json")
        assert empty == {}
        result = resolve_identity(_key(CAFFEINE_SMILES), empty, build_skeleton_index(empty))
        assert result.identity_status == "unidentified"

    def test_snapshot_entries_all_carry_a_license(self) -> None:
        """Provenance requirement: every reference record states its licence."""
        raw = json.loads(SNAPSHOT_PATH.read_text(encoding="utf-8"))
        assert raw["compounds"], "snapshot unexpectedly empty"
        assert all(c.get("license_spdx") for c in raw["compounds"])
