"""Tests for the content-addressed feature-set identifier (ADR-005)."""

from __future__ import annotations

import pytest

from drugsim_features import compute_feature_set_id

pytestmark = pytest.mark.unit


def _id(**overrides: object) -> str:
    kwargs: dict[str, object] = {
        "descriptor_spec_version": "v1",
        "rdkit_version": "2025.3.3",
        "standardization_pipeline_version": "v1",
        "descriptor_names": ["mw_g_mol", "logp_crippen"],
    }
    kwargs.update(overrides)
    return compute_feature_set_id(**kwargs)  # type: ignore[arg-type]


class TestComputeFeatureSetId:
    def test_is_a_64_char_lowercase_hex_digest(self) -> None:
        result = _id()
        assert len(result) == 64
        assert all(c in "0123456789abcdef" for c in result)

    def test_deterministic_for_identical_inputs(self) -> None:
        assert _id() == _id()

    def test_descriptor_name_order_does_not_matter(self) -> None:
        a = _id(descriptor_names=["mw_g_mol", "logp_crippen"])
        b = _id(descriptor_names=["logp_crippen", "mw_g_mol"])
        assert a == b

    def test_different_rdkit_version_changes_the_id(self) -> None:
        assert _id(rdkit_version="2025.3.3") != _id(rdkit_version="2024.9.1")

    def test_different_descriptor_spec_version_changes_the_id(self) -> None:
        assert _id(descriptor_spec_version="v1") != _id(descriptor_spec_version="v2")

    def test_different_standardization_pipeline_version_changes_the_id(self) -> None:
        assert _id(standardization_pipeline_version="v1") != _id(
            standardization_pipeline_version="v2"
        )

    def test_different_descriptor_set_changes_the_id(self) -> None:
        assert _id(descriptor_names=["mw_g_mol"]) != _id(
            descriptor_names=["mw_g_mol", "logp_crippen"]
        )
