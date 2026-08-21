"""Tests for the model bundle loader and its integrity verification."""

from __future__ import annotations

import json

import pytest

from drugsim_core.errors import IntegrityError
from drugsim_predict.model_registry import load_model_bundle

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]


class TestLoadModelBundle:
    def test_loads_successfully(self) -> None:
        bundle = load_model_bundle()
        assert bundle.model_id == "herg_inhibition"
        assert bundle.model_version == "0.1.0"

    def test_exposes_frozen_reference_data(self) -> None:
        bundle = load_model_bundle()
        assert bundle.calibration_nonconformity.shape[0] > 0
        assert bundle.train_fingerprints_f32.shape == (bundle.training_set_size, 2048)
        assert bundle.train_descriptors_scaled.shape[0] == bundle.training_set_size
        assert len(bundle.train_scaffolds) > 0

    def test_training_set_size_is_the_training_split_not_full_dataset(self) -> None:
        """training_set_size must reflect what the model actually fit on
        (split groups 0-6), not the full validated dataset (9,589) -- a
        real bug caught during Phase 5 development."""
        bundle = load_model_bundle()
        assert bundle.training_set_size == bundle.train_fingerprints_f32.shape[0]
        assert bundle.training_set_size < 9589

    def test_final_report_status_is_the_phase4_status_not_stale_phase3(self) -> None:
        """Caught during Phase 5 development: the registry file still said
        EXPERIMENTAL after Phase 4 concluded VALIDATED FOR INTERNAL
        RESEARCH. Pinned here so a future edit cannot silently regress it."""
        bundle = load_model_bundle()
        assert bundle.final_report_status == "VALIDATED FOR INTERNAL RESEARCH"

    def test_descriptor_ad_scaler_is_fitted(self) -> None:
        bundle = load_model_bundle()
        # A fitted StandardScaler has these attributes; an unfitted one raises.
        assert bundle.descriptor_ad_scaler.mean_.shape[0] == len(bundle.descriptor_fields)

    def test_model_forced_to_single_threaded_execution(self) -> None:
        """Phase 7 performance fix: the pickled estimator's n_jobs=-1 is
        overridden to 1 at load time. Single-sample serving pays joblib's
        parallel-backend coordination overhead on every request for no
        benefit (measured: ~65% of inference time); this only changes
        execution strategy; predict_proba's output is unaffected."""
        bundle = load_model_bundle()
        assert bundle.sklearn_model.n_jobs == 1


def _fake_registry_dir(tmp_path):
    """A tmp_path/models/registry/ dir, matching load_model_bundle's own
    ``path.resolve().parents[2]`` repo-root convention (registry.json ->
    registry/ -> models/ -> repo root)."""
    d = tmp_path / "models" / "registry"
    d.mkdir(parents=True)
    return d


class TestIntegrityVerification:
    def test_missing_model_file_raises_integrity_error(self, tmp_path) -> None:
        """Registry points at a model file that does not exist on disk."""
        from drugsim_predict.model_registry import get_predict_settings

        real_registry = json.loads(get_predict_settings().registry_path.read_text())
        real_registry["artifact"]["path"] = "models/admet/herg_inhibition/artifact/does_not_exist.joblib"

        fake_registry_path = _fake_registry_dir(tmp_path) / "registry.json"
        fake_registry_path.write_text(json.dumps(real_registry))

        with pytest.raises(IntegrityError):
            load_model_bundle(registry_path=fake_registry_path)

    def test_tampered_model_checksum_raises_integrity_error(self, tmp_path) -> None:
        """A model file that exists but does not match its recorded
        checksum must hard-fail, not warn (TDS Sec 6.6 stage 2)."""
        import shutil

        from drugsim_predict.model_registry import get_predict_settings

        real_path = get_predict_settings().registry_path
        real_registry = json.loads(real_path.read_text())
        real_root = real_path.resolve().parents[2]

        fake_model_dir = tmp_path / "models" / "admet" / "herg_inhibition" / "artifact"
        fake_model_dir.mkdir(parents=True)
        shutil.copy(real_root / real_registry["artifact"]["path"], fake_model_dir / "model.joblib")
        real_registry["artifact"]["sha256"] = "0" * 64  # deliberately wrong

        fake_registry_path = _fake_registry_dir(tmp_path) / "registry.json"
        fake_registry_path.write_text(json.dumps(real_registry))

        with pytest.raises(IntegrityError, match="checksum mismatch"):
            load_model_bundle(registry_path=fake_registry_path)

    def test_tampered_manifest_checksum_raises_integrity_error(self, tmp_path) -> None:
        """The inference-support manifest carries the k-NN/conformal
        thresholds shown in every applicability-domain and uncertainty
        verdict. It must be checksum-verified like every other artifact in
        the bundle (Phase 7 hardening — this was previously the one
        unverified file in the bundle)."""
        import shutil

        from drugsim_predict.model_registry import get_predict_settings

        real_path = get_predict_settings().registry_path
        real_registry = json.loads(real_path.read_text())
        real_root = real_path.resolve().parents[2]

        fake_artifact_dir = tmp_path / "models" / "admet" / "herg_inhibition" / "artifact"
        fake_artifact_dir.mkdir(parents=True)
        fake_admet_dir = tmp_path / "models" / "admet" / "herg_inhibition"

        shutil.copy(real_root / real_registry["artifact"]["path"], fake_artifact_dir / "model.joblib")
        real_registry["artifact"]["path"] = "models/admet/herg_inhibition/artifact/model.joblib"

        shutil.copy(real_root / real_registry["inference_support"]["npz_path"], fake_artifact_dir / "inference_support.npz")
        real_registry["inference_support"]["npz_path"] = "models/admet/herg_inhibition/artifact/inference_support.npz"

        shutil.copy(real_root / real_registry["inference_support"]["scaler_path"], fake_artifact_dir / "descriptor_ad_scaler.joblib")
        real_registry["inference_support"]["scaler_path"] = "models/admet/herg_inhibition/artifact/descriptor_ad_scaler.joblib"

        shutil.copy(real_root / real_registry["inference_support"]["manifest_path"], fake_admet_dir / "inference_support_manifest.json")
        real_registry["inference_support"]["manifest_path"] = "models/admet/herg_inhibition/inference_support_manifest.json"
        real_registry["inference_support"]["manifest_sha256"] = "0" * 64  # deliberately wrong

        fake_registry_path = _fake_registry_dir(tmp_path) / "registry.json"
        fake_registry_path.write_text(json.dumps(real_registry))

        with pytest.raises(IntegrityError, match="checksum mismatch"):
            load_model_bundle(registry_path=fake_registry_path)
