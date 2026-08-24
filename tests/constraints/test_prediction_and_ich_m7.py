"""Constraint and trigger tests: models, predictions, and ICH M7.

Two tests here matter more than the rest of this entire suite combined:

* ``TestFeatureSetConsistencyTrigger`` — proves rule PR-01 (the structural
  prevention of training/serving skew, TDS §6.6, risk R5) actually rejects a
  mismatch rather than silently accepting it.
* ``TestIchM7MethodologyPairing`` — proves the ICH M7(R2) dual-methodology
  requirement is a hard database error, not a code-review-dependent convention.

Both are triggers, not CHECK constraints, and triggers are exactly the kind of
thing that silently stops firing after a careless migration. If either of these
tests is ever accidentally deleted or skipped, that fact should be treated as
seriously as deleting the trigger itself.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from .factories import (
    insert_compound,
    insert_data_source,
    insert_descriptor_spec,
    insert_endpoint,
    insert_ingestion_snapshot,
    insert_model,
    insert_model_version,
    insert_prediction,
    insert_toolchain,
)

pytestmark = [pytest.mark.integration, pytest.mark.constraints]


@pytest.fixture
def prediction_fixtures(session: Session, curator_user_id: str) -> dict[str, str]:
    """A compound, endpoint, model, and a validly-paired model_version."""
    source_id = insert_data_source(session)
    snapshot_id = insert_ingestion_snapshot(session, source_id)
    toolchain_id = insert_toolchain(session)
    descriptor_spec_version = insert_descriptor_spec(session, toolchain_id)
    compound_uid = insert_compound(
        session,
        source_id=source_id,
        snapshot_id=snapshot_id,
        toolchain_id=toolchain_id,
        created_by=curator_user_id,
    )
    endpoint_id = insert_endpoint(session)
    model_uid = insert_model(session, endpoint_id, curator_user_id)
    model_version_uid = insert_model_version(
        session, model_uid, descriptor_spec_version, snapshot_id, curator_user_id,
        feature_set_id="f" * 64,
    )
    session.flush()
    return {
        "compound_uid": compound_uid,
        "endpoint_id": endpoint_id,
        "model_uid": model_uid,
        "model_version_uid": model_version_uid,
        "created_by": curator_user_id,
        "descriptor_spec_version": descriptor_spec_version,
        "snapshot_id": snapshot_id,
    }


class TestFeatureSetConsistencyTrigger:
    """Rule PR-01: prediction.feature_set_id must equal its model's."""

    def test_matching_feature_set_succeeds(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        insert_prediction(
            session,
            prediction_fixtures["compound_uid"],
            prediction_fixtures["endpoint_id"],
            prediction_fixtures["model_version_uid"],
            feature_set_id="f" * 64,  # matches the model_version fixture
        )
        session.flush()  # must not raise

    def test_mismatched_feature_set_raises(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        """This is THE test for risk R5. If it ever stops raising, training/serving
        skew has become possible again."""
        with pytest.raises(DBAPIError, match="feature_set_id mismatch"):
            insert_prediction(
                session,
                prediction_fixtures["compound_uid"],
                prediction_fixtures["endpoint_id"],
                prediction_fixtures["model_version_uid"],
                feature_set_id="0" * 64,  # deliberately WRONG
            )
            session.flush()

    def test_nonexistent_model_version_raises(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        with pytest.raises(DBAPIError):
            insert_prediction(
                session,
                prediction_fixtures["compound_uid"],
                prediction_fixtures["endpoint_id"],
                "Z" * 26,
                feature_set_id="f" * 64,
            )
            session.flush()


class TestPredictionIntervalConstraints:
    """ck_interval_brackets / ck_interval_pair."""

    def test_interval_must_bracket_the_point_estimate(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_interval_brackets"):
            insert_prediction(
                session,
                prediction_fixtures["compound_uid"],
                prediction_fixtures["endpoint_id"],
                prediction_fixtures["model_version_uid"],
                feature_set_id="f" * 64,
                predicted_value=10.0,
                interval_low=20.0,
                interval_high=30.0,
            )
            session.flush()

    def test_both_bounds_null_is_permitted(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        insert_prediction(
            session,
            prediction_fixtures["compound_uid"],
            prediction_fixtures["endpoint_id"],
            prediction_fixtures["model_version_uid"],
            feature_set_id="f" * 64,
            interval_low=None,
            interval_high=None,
        )
        session.flush()  # must not raise

    def test_one_bound_without_the_other_rejected(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_interval_pair"):
            insert_prediction(
                session,
                prediction_fixtures["compound_uid"],
                prediction_fixtures["endpoint_id"],
                prediction_fixtures["model_version_uid"],
                feature_set_id="f" * 64,
                interval_low=0.5,
                interval_high=None,
            )
            session.flush()


class TestModelCommercialTierConsistency:
    """ck_commercial_tiers: shippability is computed from consumed licence tiers,
    never asserted (Phase 1 Step 1 §5, ADR-007)."""

    def test_black_tier_training_data_forbids_commercial_ok(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_commercial_tiers"):
            insert_model_version(
                session,
                prediction_fixtures["model_uid"],
                prediction_fixtures["descriptor_spec_version"],
                prediction_fixtures["snapshot_id"],
                prediction_fixtures["created_by"],
                training_license_tiers=["amber", "black"],
                is_commercial_ok=True,  # contradicts the black tier present
                version="0.2.0",
            )
            session.flush()

    def test_black_tier_with_commercial_ok_false_succeeds(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        insert_model_version(
            session,
            prediction_fixtures["model_uid"],
            prediction_fixtures["descriptor_spec_version"],
            prediction_fixtures["snapshot_id"],
            prediction_fixtures["created_by"],
            training_license_tiers=["amber", "black"],
            is_commercial_ok=False,
            version="0.3.0",
        )
        session.flush()  # must not raise


class TestRegulatoryReadinessRequiresValidation:
    """ck_regulatory_requires_validation."""

    def test_regulatory_ready_without_validation_rejected(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        with pytest.raises(IntegrityError, match="ck_regulatory_requires_validation"):
            insert_model_version(
                session,
                prediction_fixtures["model_uid"],
                prediction_fixtures["descriptor_spec_version"],
                prediction_fixtures["snapshot_id"],
                prediction_fixtures["created_by"],
                is_validated=False,
                is_regulatory_ready=True,
                version="0.4.0",
            )
            session.flush()


class TestIchM7MethodologyPairing:
    """The dual-methodology requirement, verified against FDA M7(R2) guidance:
    absence of alerts from two COMPLEMENTARY methodologies — one expert
    rule-based, one statistical — is what permits a no-concern conclusion."""

    def _make_prediction_from_model(
        self,
        session: Session,
        fx: dict[str, str],
        methodology: str,
        *,
        feature_set_id: str,
    ) -> str:
        model_uid = insert_model(session, fx["endpoint_id"], fx["created_by"], methodology=methodology)
        model_version_uid = insert_model_version(
            session, model_uid, fx["descriptor_spec_version"], fx["snapshot_id"], fx["created_by"],
            feature_set_id=feature_set_id,
        )
        session.flush()
        return insert_prediction(
            session, fx["compound_uid"], fx["endpoint_id"], model_version_uid,
            feature_set_id=feature_set_id,
        )

    def test_correctly_paired_predictions_succeed(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        rule_based_pred = self._make_prediction_from_model(
            session, prediction_fixtures, "expert_rule_based", feature_set_id="1" * 64
        )
        statistical_pred = self._make_prediction_from_model(
            session, prediction_fixtures, "statistical_based", feature_set_id="2" * 64
        )
        session.execute(
            text(
                "INSERT INTO ich_m7_assessment (assessment_uid, compound_uid, "
                "rule_based_prediction_uid, statistical_prediction_uid, "
                "predictions_concordant, requires_expert_review) "
                "VALUES ('A' || repeat('0', 25), :cuid, :rb, :st, true, false)"
            ),
            {"cuid": prediction_fixtures["compound_uid"], "rb": rule_based_pred, "st": statistical_pred},
        )
        session.flush()  # must not raise

    def test_both_from_statistical_models_rejected(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        """The failure mode the trigger exists to prevent: two statistical models
        presented as if they were the required complementary pair."""
        pred_a = self._make_prediction_from_model(
            session, prediction_fixtures, "statistical_based", feature_set_id="3" * 64
        )
        pred_b = self._make_prediction_from_model(
            session, prediction_fixtures, "statistical_based", feature_set_id="4" * 64
        )
        with pytest.raises(DBAPIError, match="expert_rule_based"):
            session.execute(
                text(
                    "INSERT INTO ich_m7_assessment (assessment_uid, compound_uid, "
                    "rule_based_prediction_uid, statistical_prediction_uid, "
                    "predictions_concordant, requires_expert_review) "
                    "VALUES ('B' || repeat('0', 25), :cuid, :a, :b, true, false)"
                ),
                {"cuid": prediction_fixtures["compound_uid"], "a": pred_a, "b": pred_b},
            )
            session.flush()

    def test_statistical_slot_filled_by_rule_based_rejected(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        rule_based_pred = self._make_prediction_from_model(
            session, prediction_fixtures, "expert_rule_based", feature_set_id="5" * 64
        )
        another_rule_based = self._make_prediction_from_model(
            session, prediction_fixtures, "expert_rule_based", feature_set_id="6" * 64
        )
        with pytest.raises(DBAPIError, match="statistical_based"):
            session.execute(
                text(
                    "INSERT INTO ich_m7_assessment (assessment_uid, compound_uid, "
                    "rule_based_prediction_uid, statistical_prediction_uid, "
                    "predictions_concordant, requires_expert_review) "
                    "VALUES ('C' || repeat('0', 25), :cuid, :rb, :st, true, false)"
                ),
                {"cuid": prediction_fixtures["compound_uid"], "rb": rule_based_pred, "st": another_rule_based},
            )
            session.flush()

    def test_identical_prediction_for_both_slots_rejected(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        """The two arms cannot be the same prediction.

        Rejected by the methodology-pairing TRIGGER rather than by
        ``ck_distinct_predictions``: a BEFORE INSERT trigger runs ahead of CHECK
        constraints, and reusing one prediction for both slots necessarily puts a
        rule-based prediction in the statistical slot, which the trigger catches
        first. ``ck_distinct_predictions`` is therefore unreachable in practice --
        a single prediction cannot come from both a statistical and a rule-based
        model -- so it stands as defence in depth, not the active guard. Asserting
        only the constraint name here would fail while the row is, correctly,
        still rejected.
        """
        pred = self._make_prediction_from_model(
            session, prediction_fixtures, "expert_rule_based", feature_set_id="7" * 64
        )
        with pytest.raises(DBAPIError, match="ck_distinct_predictions|statistical_based"):
            session.execute(
                text(
                    "INSERT INTO ich_m7_assessment (assessment_uid, compound_uid, "
                    "rule_based_prediction_uid, statistical_prediction_uid, "
                    "predictions_concordant, requires_expert_review) "
                    "VALUES ('D' || repeat('0', 25), :cuid, :p, :p, true, false)"
                ),
                {"cuid": prediction_fixtures["compound_uid"], "p": pred},
            )
            session.flush()

    def test_requires_review_without_review_uid_rejected(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        """ck_review_when_required: a discordant/OOD/equivocal result cannot skip
        expert review."""
        rule_based_pred = self._make_prediction_from_model(
            session, prediction_fixtures, "expert_rule_based", feature_set_id="8" * 64
        )
        statistical_pred = self._make_prediction_from_model(
            session, prediction_fixtures, "statistical_based", feature_set_id="9" * 64
        )
        with pytest.raises(IntegrityError, match="ck_review_when_required"):
            session.execute(
                text(
                    "INSERT INTO ich_m7_assessment (assessment_uid, compound_uid, "
                    "rule_based_prediction_uid, statistical_prediction_uid, "
                    "predictions_concordant, requires_expert_review, expert_review_uid) "
                    "VALUES ('E' || repeat('0', 25), :cuid, :rb, :st, false, true, NULL)"
                ),
                {"cuid": prediction_fixtures["compound_uid"], "rb": rule_based_pred, "st": statistical_pred},
            )
            session.flush()

    def test_conclusion_without_final_class_rejected(
        self, session: Session, prediction_fixtures: dict[str, str]
    ) -> None:
        """ck_conclusion_requires_class."""
        rule_based_pred = self._make_prediction_from_model(
            session, prediction_fixtures, "expert_rule_based", feature_set_id="a" * 64
        )
        statistical_pred = self._make_prediction_from_model(
            session, prediction_fixtures, "statistical_based", feature_set_id="b" * 64
        )
        with pytest.raises(IntegrityError, match="ck_conclusion_requires_class"):
            session.execute(
                text(
                    "INSERT INTO ich_m7_assessment (assessment_uid, compound_uid, "
                    "rule_based_prediction_uid, statistical_prediction_uid, "
                    "predictions_concordant, requires_expert_review, conclusion, final_class) "
                    "VALUES ('F' || repeat('0', 25), :cuid, :rb, :st, true, false, "
                    "'no concern', NULL)"
                ),
                {"cuid": prediction_fixtures["compound_uid"], "rb": rule_based_pred, "st": statistical_pred},
            )
            session.flush()
