"""Tests for per-record unit resolution.

The load-bearing property: a unit this module cannot establish reliably is
marked ``unresolved``, never guessed. TestMassConcentrationConversion also
locks in the exact arithmetic (a real bug — a 1000x factor error — was
caught here during development by testing rather than trusting the
derivation on paper).
"""

from __future__ import annotations

import pytest

from drugsim_curation.units import resolve_unit

pytestmark = pytest.mark.unit


class TestMolarUnitsAlwaysResolve:
    def test_nanomolar_is_identity_passthrough(self) -> None:
        result = resolve_unit("12.5", "nM")
        assert result.normalised_value == pytest.approx(12.5)
        assert result.normalised_unit == "nM"
        assert result.unit_status == "resolved"
        assert result.conversion_status == "not_required"

    def test_micromolar_converts_to_nanomolar(self) -> None:
        result = resolve_unit("2.0", "uM")
        assert result.normalised_value == pytest.approx(2000.0)
        assert result.unit_status == "resolved"
        assert result.conversion_status == "converted"

    def test_millimolar_converts_to_nanomolar(self) -> None:
        result = resolve_unit("1.0", "mM")
        assert result.normalised_value == pytest.approx(1_000_000.0)

    def test_molar_converts_to_nanomolar(self) -> None:
        result = resolve_unit("1.0", "M")
        assert result.normalised_value == pytest.approx(1_000_000_000.0)

    def test_picomolar_converts_to_nanomolar(self) -> None:
        result = resolve_unit("500", "pM")
        assert result.normalised_value == pytest.approx(0.5)


class TestMassConcentrationRequiresMolecularWeight:
    def test_unresolved_without_molecular_weight(self) -> None:
        result = resolve_unit("5", "ug/mL")
        assert result.unit_status == "unresolved"
        assert result.conversion_status == "unresolved_no_molecular_weight"
        assert result.normalised_value is None

    def test_resolved_with_molecular_weight(self) -> None:
        # 5 ug/mL at MW 500 g/mol: 5e-3 g/L / 500 g/mol = 1e-5 M = 1e4 nM.
        result = resolve_unit("5", "ug/mL", molecular_weight_g_mol=500.0)
        assert result.unit_status == "resolved"
        assert result.normalised_value == pytest.approx(10_000.0)

    def test_mg_per_ml_conversion_is_correct(self) -> None:
        # 1 mg/mL at MW 1000 g/mol: 1 g/L / 1000 g/mol = 1e-3 M = 1e6 nM.
        result = resolve_unit("1", "mg/mL", molecular_weight_g_mol=1000.0)
        assert result.normalised_value == pytest.approx(1_000_000.0)

    def test_ng_per_ml_conversion_is_correct(self) -> None:
        # 1 ng/mL at MW 100 g/mol: 1e-6 g/L / 100 g/mol = 1e-8 M = 10 nM.
        result = resolve_unit("1", "ng/mL", molecular_weight_g_mol=100.0)
        assert result.normalised_value == pytest.approx(10.0)

    def test_zero_or_negative_molecular_weight_is_unresolved(self) -> None:
        result = resolve_unit("5", "ug/mL", molecular_weight_g_mol=0.0)
        assert result.unit_status == "unresolved"


class TestUnknownAndUnparseableInputsNeverGuess:
    def test_unrecognised_unit_is_unresolved(self) -> None:
        result = resolve_unit("10", "furlongs_per_fortnight")
        assert result.unit_status == "unresolved"
        assert result.conversion_status == "unresolved_unknown_unit"

    def test_unparseable_value_is_unresolved(self) -> None:
        result = resolve_unit("not_a_number", "nM")
        assert result.unit_status == "unresolved"

    def test_empty_value_is_unresolved(self) -> None:
        result = resolve_unit("", "nM")
        assert result.unit_status == "unresolved"
