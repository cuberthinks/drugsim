"""Tests for structure redaction primitives.

Complements ``tests/security/test_no_structure_in_logs.py``, which tests the
end-to-end control. These tests cover the primitives directly, including the
false-positive behaviour of the heuristic backstop.
"""

from __future__ import annotations

import pytest

from drugsim_core.redaction import (
    SENSITIVE_KEYS,
    SensitiveStructure,
    looks_like_structure,
    redact_event,
    structure_digest,
)

pytestmark = pytest.mark.unit

REAL_SMILES = [
    "CC(=O)Oc1ccccc1C(=O)O",                                    # aspirin
    "CN1C=NC2=C1C(=O)N(C)C(=O)N2C",                             # caffeine
    "c1ccccc1",                                                 # benzene
    "CC(C)Cc1ccc(cc1)C(C)C(=O)O",                               # ibuprofen
    "C[C@@H](N)C(=O)O",                                         # L-alanine, stereo
    "[Na+].[Cl-]",                                              # salt
    "Cc1ccc(NC(=O)c2ccc(CN3CCN(C)CC3)cc2)cc1Nc1nccc(-c2cccnc2)n1",  # imatinib
]

NOT_STRUCTURES = [
    "",
    "hello",
    "INFO",
    "2026-08-05T12:00:00Z",
    "1.2.3",
    "chembl_37",
    "caco2_papp",
    "01J8XK2M4N7P9QRSTVWXYZ0123",          # ULID
    "cmp_01J8XK2M4N7P9QRSTVWXYZ0123",      # public ID
    "/var/data/chembl/activities.parquet",
    "postgresql://localhost:5432/drugsim",
    "a3f9c21b8e40d1f2a3b4c5d6e7f8091a",     # hex digest
    "The quick brown fox",
]


class TestSensitiveStructure:
    """The wrapper type."""

    def test_str_is_redacted(self) -> None:
        s = SensitiveStructure(REAL_SMILES[0])
        assert REAL_SMILES[0] not in str(s)
        assert "REDACTED" in str(s)

    def test_repr_is_redacted(self) -> None:
        assert REAL_SMILES[0] not in repr(SensitiveStructure(REAL_SMILES[0]))

    @pytest.mark.parametrize("spec", ["", ">50", "<10", ".5", "^30"])
    def test_format_spec_cannot_slice_value_out(self, spec: str) -> None:
        """A format spec must not be able to reveal any part of the value."""
        s = SensitiveStructure(REAL_SMILES[0])
        rendered = format(s, spec)
        assert REAL_SMILES[0] not in rendered
        assert "REDACTED" in rendered

    def test_is_not_a_str_subclass(self) -> None:
        """A str subclass would be silently accepted where a raw string is expected."""
        assert not isinstance(SensitiveStructure("CCO"), str)

    def test_reveal_returns_value(self) -> None:
        assert SensitiveStructure("CCO").reveal() == "CCO"

    def test_digest_is_deterministic(self) -> None:
        assert SensitiveStructure("CCO").digest == SensitiveStructure("CCO").digest

    def test_digest_differs_between_structures(self) -> None:
        assert SensitiveStructure("CCO").digest != SensitiveStructure("CCC").digest

    def test_digest_is_not_reversible_length(self) -> None:
        assert len(structure_digest("CCO")) == 12

    def test_is_frozen(self) -> None:
        s = SensitiveStructure("CCO")
        with pytest.raises(AttributeError):
            s.kind = "molblock"  # type: ignore[misc]

    def test_kind_is_recorded(self) -> None:
        assert "molblock" in str(SensitiveStructure("CCO", kind="molblock"))


class TestHeuristic:
    """The pattern backstop, including its false-positive behaviour."""

    @pytest.mark.parametrize("smiles", REAL_SMILES)
    def test_detects_real_smiles(self, smiles: str) -> None:
        assert looks_like_structure(smiles), smiles

    @pytest.mark.parametrize("text", NOT_STRUCTURES)
    def test_does_not_flag_ordinary_strings(self, text: str) -> None:
        """False positives would redact useful diagnostics, degrading debuggability."""
        assert not looks_like_structure(text), text

    def test_detects_inchi(self) -> None:
        assert looks_like_structure(
            "InChI=1S/C9H8O4/c1-6(10)13-8-5-3-2-4-7(8)9(11)12/h2-5H,1H3,(H,11,12)"
        )

    def test_detects_inchikey(self) -> None:
        assert looks_like_structure("BSYNRYMUTXBXSQ-UHFFFAOYSA-N")

    def test_rejects_overlong_input(self) -> None:
        """A guard against pathological input to the regex engine."""
        assert not looks_like_structure("C" * 6000)


class TestRedactEvent:
    """The structlog processor."""

    def test_redacts_sensitive_keys(self) -> None:
        for key in sorted(SENSITIVE_KEYS):
            out = redact_event(None, "info", {key: REAL_SMILES[0]})
            assert REAL_SMILES[0] not in str(out[key]), key

    def test_redacts_sensitive_key_even_for_innocuous_value(self) -> None:
        """Key-based redaction is exact and does not depend on the heuristic."""
        out = redact_event(None, "info", {"smiles": "x"})
        assert out["smiles"] != "x"

    def test_redacts_wrapper_anywhere(self) -> None:
        out = redact_event(None, "info", {"anything": SensitiveStructure(REAL_SMILES[0])})
        assert REAL_SMILES[0] not in out["anything"]

    def test_recurses_into_nested_mapping(self) -> None:
        event = {"payload": {"inner": {"smiles": REAL_SMILES[0]}}}
        assert REAL_SMILES[0] not in str(redact_event(None, "info", event))

    def test_recurses_into_list(self) -> None:
        event = {"batch": [REAL_SMILES[0], REAL_SMILES[1]]}
        assert REAL_SMILES[0] not in str(redact_event(None, "info", event))

    def test_preserves_tuple_type(self) -> None:
        out = redact_event(None, "info", {"items": ("a", "b")})
        assert isinstance(out["items"], tuple)

    def test_preserves_non_string_values(self) -> None:
        event = {"count": 42, "ratio": 0.5, "ok": True, "nothing": None}
        assert redact_event(None, "info", event) == event

    def test_scrubs_inchi_inside_free_text(self) -> None:
        inchi = "InChI=1S/C2H6O/c1-2-3/h3H,2H2,1H3"
        out = redact_event(None, "info", {"event": f"failed on {inchi} at step 2"})
        assert inchi not in out["event"]
        assert "failed on" in out["event"]
        assert "at step 2" in out["event"]

    def test_does_not_mangle_ordinary_messages(self) -> None:
        message = "ingested 1234 rows from chembl_37 in 5.2s"
        out = redact_event(None, "info", {"event": message})
        assert out["event"] == message
