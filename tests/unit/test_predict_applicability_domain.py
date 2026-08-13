"""Tests for the applicability-domain verdict logic."""

from __future__ import annotations

import pytest

from drugsim_predict.applicability_domain import assess_applicability_domain
from drugsim_predict.model_registry import load_model_bundle

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]


@pytest.fixture(scope="module")
def bundle():
    return load_model_bundle()


class TestAssessApplicabilityDomain:
    def test_training_compound_itself_is_in_domain(self, bundle) -> None:
        """A compound that IS in the training set must score max Tanimoto
        1.0 to itself and land in_domain (assuming its own scaffold is, of
        course, in the training scaffold set)."""
        fp = bundle.train_fingerprints[0]
        desc = bundle.train_descriptors[0]
        scaffold = next(iter(bundle.train_scaffolds))
        result = assess_applicability_domain(fp, desc, scaffold, bundle)
        assert result.max_tanimoto_to_training == 1.0
        assert result.verdict == "in_domain"

    def test_unseen_scaffold_with_low_similarity_is_out_of_domain(self, bundle) -> None:
        import numpy as np

        # An all-zero fingerprint (no substructures in common with anything)
        # and a descriptor vector far outside the training distribution.
        fp = np.zeros(2048, dtype=np.uint8)
        desc = bundle.train_descriptors.mean(axis=0) + 50 * bundle.train_descriptors.std(axis=0)
        result = assess_applicability_domain(fp, desc, "not_a_real_scaffold_xyz", bundle)
        assert result.verdict == "out_of_domain"
        assert result.max_tanimoto_to_training < 0.4

    def test_none_inputs_are_undeterminable(self, bundle) -> None:
        result = assess_applicability_domain(None, None, None, bundle)
        assert result.verdict == "undeterminable"
        assert result.max_tanimoto_to_training is None

    def test_rationale_is_a_nonempty_plain_language_string(self, bundle) -> None:
        fp = bundle.train_fingerprints[0]
        desc = bundle.train_descriptors[0]
        result = assess_applicability_domain(fp, desc, None, bundle)
        assert isinstance(result.rationale, str)
        assert len(result.rationale) > 20

    def test_scaffold_none_treated_as_not_seen(self, bundle) -> None:
        fp = bundle.train_fingerprints[0]
        desc = bundle.train_descriptors[0]
        result = assess_applicability_domain(fp, desc, None, bundle)
        assert result.scaffold_seen_in_training is False
