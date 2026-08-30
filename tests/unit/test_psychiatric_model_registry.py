"""Regression tests for the CYP2D6/BBB model_registry entries.

Catches registry-JSON/checksum drift (a stale sha256 after a model is
retrained but the registry entry isn't regenerated, a moved artifact
path, a promotion-status typo) rather than re-testing
`drugsim_predict.model_registry` itself, which already has its own
test suite for hERG/CYP3A4.
"""

from __future__ import annotations

from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]

pytestmark = pytest.mark.unit

_ARTIFACTS_PRESENT = all(
    (ROOT / "models" / "psychiatric" / endpoint / "artifact" / "model.joblib").exists()
    for endpoint in ("cyp2d6_activity", "bbb_permeability")
)


@pytest.mark.skipif(
    not _ARTIFACTS_PRESENT,
    reason="Model artifacts are gitignored binaries -- only present after running each endpoint's own train.py + 10_export_inference_support.py locally.",
)
class TestCyp2d6AndBbbRegistryEntries:
    @pytest.mark.parametrize("model_id", ["cyp2d6_activity", "bbb_permeability"])
    def test_registered_bundle_loads_and_checksum_verifies(self, model_id: str) -> None:
        from drugsim_predict.model_registry import load_model_bundle

        bundle = load_model_bundle(model_id=model_id)
        assert bundle.model_id == model_id
        assert bundle.sklearn_model is not None
        assert bundle.train_fingerprints_f32.shape[1] == 2048

    @pytest.mark.parametrize("model_id", ["cyp2d6_activity", "bbb_permeability"])
    def test_registered_as_experimental_not_promoted(self, model_id: str) -> None:
        from drugsim_predict.model_registry import load_model_bundle

        bundle = load_model_bundle(model_id=model_id)
        assert bundle.final_report_status == "EXPERIMENTAL"

    @pytest.mark.parametrize("model_id", ["cyp2d6_activity", "bbb_permeability"])
    def test_run_inference_correctly_refuses_to_serve_experimental_models(self, model_id: str) -> None:
        from drugsim_core.errors import EndpointNotAvailableError
        from drugsim_predict.pipeline import run_inference

        with pytest.raises(EndpointNotAvailableError):
            run_inference("CCO", "smiles", model_id=model_id)
