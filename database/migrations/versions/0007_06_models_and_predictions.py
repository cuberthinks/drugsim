"""models, validation, and predictions

Revision ID: 0007
Revises: '0006'
Create Date: 2026-08-06

Generated from database/ddl/06_models_and_predictions.sql at authoring time — see that file's
README for why this migration embeds the SQL directly rather than reading the
(mutable) ddl file at run time.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0007"
down_revision: Optional[str] = '0006'
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
-- DrugSim — Models, validation, and predictions
-- Phase 1 Step 3 §7. Table creation order here differs from the narrative order
-- in Step 3 (expert_review is created before ich_m7_assessment): Step 3 presented
-- ich_m7_assessment first for readability, but it references expert_review by FK,
-- and Postgres requires the referenced table to exist first. This is execution
-- mechanics, not a design change.

CREATE TABLE model (
    model_uid   ulid          PRIMARY KEY,
    model_name  TEXT          NOT NULL UNIQUE,
    endpoint_id TEXT          NOT NULL REFERENCES endpoint (endpoint_id) ON DELETE RESTRICT,
    methodology methodology_t NOT NULL,
    description TEXT          NOT NULL,
    created_by  ulid          NOT NULL REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    created_at  TIMESTAMPTZ   NOT NULL DEFAULT now()
);

CREATE TABLE model_version (
    model_version_uid       ulid                PRIMARY KEY,
    model_uid               ulid                NOT NULL REFERENCES model (model_uid) ON DELETE RESTRICT,
    version                 semver              NOT NULL,
    algorithm                TEXT               NOT NULL,
    hyperparameters          JSONB              NOT NULL,
    feature_set_id           sha256_hex         NOT NULL,
    descriptor_spec_version  TEXT               NOT NULL REFERENCES descriptor_spec (descriptor_spec_version) ON DELETE RESTRICT,
    training_snapshot_id     TEXT               NOT NULL REFERENCES ingestion_snapshot (snapshot_id) ON DELETE RESTRICT,
    training_license_tiers   license_tier_t[]   NOT NULL,
    is_commercial_ok         BOOLEAN            NOT NULL,
    ad_definition            JSONB              NOT NULL,
    ad_method                TEXT               NOT NULL,
    calibration_method       TEXT,
    artifact_uri             TEXT               NOT NULL,
    artifact_sha256          sha256_hex         NOT NULL,
    is_validated             BOOLEAN            NOT NULL DEFAULT FALSE,
    is_regulatory_ready      BOOLEAN            NOT NULL DEFAULT FALSE,
    trained_at               TIMESTAMPTZ        NOT NULL,
    created_by               ulid               NOT NULL REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    CONSTRAINT uq_model_version UNIQUE (model_uid, version),
    CONSTRAINT ck_commercial_tiers
        CHECK (is_commercial_ok = NOT ('black' = ANY (training_license_tiers))),
    CONSTRAINT ck_regulatory_requires_validation
        CHECK (NOT is_regulatory_ready OR is_validated)
);

CREATE INDEX ix_mv_feature_set ON model_version (feature_set_id);

COMMENT ON CONSTRAINT ck_commercial_tiers ON model_version IS
    'Mechanises Phase 1 Step 1 §5: commercial shippability is COMPUTED from the '
    'licence tiers a model actually consumed, not asserted by a human who may not '
    'have checked (TDS §6.5, ADR-007).';

COMMENT ON COLUMN model_version.ad_definition IS
    'NOT NULL because OECD Principle 3 requires a defined applicability domain — '
    'a model without one cannot be created (TDS §6.4).';

CREATE TABLE model_validation_record (
    validation_uid    ulid             PRIMARY KEY,
    model_version_uid ulid             NOT NULL REFERENCES model_version (model_version_uid) ON DELETE RESTRICT,
    principle         oecd_principle_t NOT NULL,
    is_satisfied      BOOLEAN          NOT NULL,
    evidence_text     TEXT             NOT NULL,
    evidence_uri      TEXT,
    metric_name       TEXT,
    metric_value      NUMERIC(10, 6),
    validation_type   TEXT             CHECK (validation_type IN
        ('internal_cv', 'external_test', 'y_scrambling', 'bootstrap', 'temporal_holdout')),
    n_compounds       INTEGER          CHECK (n_compounds > 0),
    reviewed_by       ulid             REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    reviewed_at       TIMESTAMPTZ,
    CONSTRAINT uq_validation UNIQUE (model_version_uid, principle, metric_name)
);

COMMENT ON TABLE model_validation_record IS
    'One row per OECD principle (up to several for Principle 4, which carries '
    'multiple metrics). Structuring validation this way — rather than a free-text '
    'document — makes "which principles are unsatisfied for this model?" a query. '
    'Gate G7 asserts all five are present before a regulatory release.';

CREATE TABLE model_qmrf (
    qmrf_uid          ulid        PRIMARY KEY,
    model_version_uid ulid        NOT NULL UNIQUE REFERENCES model_version (model_version_uid) ON DELETE RESTRICT,
    qmrf_document     JSONB       NOT NULL,
    document_uri      TEXT,
    completed_by      ulid        NOT NULL REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    completed_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================
-- prediction — separate lineage from measurement, always (P4)
-- ============================================================================

CREATE TABLE prediction (
    prediction_uid          ulid          PRIMARY KEY,
    compound_uid             ulid         NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    endpoint_id              TEXT         NOT NULL REFERENCES endpoint (endpoint_id) ON DELETE RESTRICT,
    model_version_uid        ulid         NOT NULL REFERENCES model_version (model_version_uid) ON DELETE RESTRICT,
    predicted_value          NUMERIC(14, 6) NOT NULL,
    predicted_unit           TEXT         NOT NULL,
    interval_low             NUMERIC(14, 6),
    interval_high            NUMERIC(14, 6),
    interval_coverage        NUMERIC(4, 3) CHECK (interval_coverage BETWEEN 0 AND 1),
    confidence_score         prob_unit    NOT NULL,
    calibration_method       TEXT,
    ad_verdict                ad_verdict_t NOT NULL,
    ad_max_tanimoto           prob_unit    NOT NULL,
    ad_knn_distance           NUMERIC(10, 6) CHECK (ad_knn_distance >= 0),
    ad_scaffold_seen          BOOLEAN      NOT NULL,
    feature_set_id            sha256_hex   NOT NULL,
    quality_score             prob_unit    NOT NULL,
    quality_formula_version   TEXT         NOT NULL,
    is_commercial_ok          BOOLEAN      NOT NULL,
    predicted_at              TIMESTAMPTZ  NOT NULL DEFAULT now(),
    requested_by              ulid         REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    CONSTRAINT ck_interval_brackets CHECK (
        (interval_low IS NULL AND interval_high IS NULL)
        OR (interval_low <= predicted_value AND interval_high >= predicted_value)
    ),
    CONSTRAINT ck_interval_pair CHECK ((interval_low IS NULL) = (interval_high IS NULL))
);

CREATE INDEX ix_pred_compound ON prediction (compound_uid, endpoint_id, predicted_at DESC);
CREATE INDEX ix_pred_ood      ON prediction (ad_verdict) WHERE ad_verdict = 'out_of_domain';

COMMENT ON COLUMN prediction.ad_verdict IS
    'NOT NULL — rule PR-02. A prediction cannot exist without a domain '
    'assessment; this is how the "prioritisation, not replacement" positioning '
    '(Phase 1 Step 1 §5.5) becomes structural rather than aspirational.';

CREATE TABLE prediction_evidence (
    evidence_uid              ulid           PRIMARY KEY,
    prediction_uid            ulid           NOT NULL REFERENCES prediction (prediction_uid) ON DELETE RESTRICT,
    neighbour_compound_uid    ulid           NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    tanimoto                  prob_unit      NOT NULL,
    neighbour_measurement_uid ulid,
    neighbour_license_tier    license_tier_t,
    rank                      SMALLINT       NOT NULL CHECK (rank > 0),
    FOREIGN KEY (neighbour_measurement_uid, neighbour_license_tier)
        REFERENCES measurement (measurement_uid, license_tier) ON DELETE RESTRICT,
    CONSTRAINT uq_evidence UNIQUE (prediction_uid, rank)
);

-- ============================================================================
-- expert_review — created before ich_m7_assessment; see file header
-- ============================================================================

CREATE TABLE expert_review (
    review_uid      ulid             PRIMARY KEY,
    reviewer_uid    ulid             NOT NULL REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    outcome         review_outcome_t NOT NULL,
    rationale       TEXT             NOT NULL,
    literature_refs TEXT[],
    reviewed_at     TIMESTAMPTZ      NOT NULL DEFAULT now(),
    signature_uid   ulid             REFERENCES electronic_signature (signature_uid) ON DELETE RESTRICT,
    CONSTRAINT ck_rationale_not_blank CHECK (btrim(rationale) <> '')
);

COMMENT ON COLUMN expert_review.rationale IS
    'NOT NULL and non-blank. An override without a recorded reason is exactly '
    'what a regulator will ask about (Phase 1 Step 3 §7.4).';

-- ============================================================================
-- ich_m7_assessment — the dual-methodology requirement, structurally enforced
-- ============================================================================
-- ICH M7(R2) mandates two COMPLEMENTARY (Q)SAR methodologies — one expert
-- rule-based, one statistical — and permits a no-concern conclusion only when
-- both are negative (verified against FDA M7(R2) guidance). The two distinct,
-- mandatory FKs below make a single-methodology assessment structurally
-- impossible; that the two predictions actually come from the right methodology
-- TYPES is enforced by trigger (09_triggers.sql), since it requires joining
-- through model_version and model.

CREATE TABLE ich_m7_assessment (
    assessment_uid              ulid           PRIMARY KEY,
    compound_uid                 ulid          NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    rule_based_prediction_uid    ulid          NOT NULL REFERENCES prediction (prediction_uid) ON DELETE RESTRICT,
    statistical_prediction_uid   ulid          NOT NULL REFERENCES prediction (prediction_uid) ON DELETE RESTRICT,
    predictions_concordant       BOOLEAN       NOT NULL,
    requires_expert_review       BOOLEAN       NOT NULL,
    expert_review_uid            ulid          REFERENCES expert_review (review_uid) ON DELETE RESTRICT,
    final_class                  ich_m7_class_t,
    conclusion                   TEXT,
    assessed_at                  TIMESTAMPTZ   NOT NULL DEFAULT now(),
    CONSTRAINT ck_distinct_predictions
        CHECK (rule_based_prediction_uid <> statistical_prediction_uid),
    CONSTRAINT ck_review_when_required
        CHECK (NOT requires_expert_review OR expert_review_uid IS NOT NULL),
    CONSTRAINT ck_conclusion_requires_class
        CHECK (conclusion IS NULL OR final_class IS NOT NULL),
    CONSTRAINT uq_m7_compound
        UNIQUE (compound_uid, rule_based_prediction_uid, statistical_prediction_uid)
);

COMMENT ON CONSTRAINT ck_review_when_required ON ich_m7_assessment IS
    'The guideline requires expert judgement for discordant, out-of-domain, or '
    'equivocal results; this makes skipping that review a constraint violation '
    'rather than a process reminder.';
"""


def upgrade() -> None:
    """Apply 06_models_and_predictions.sql."""
    op.execute(_SQL)


def downgrade() -> None:
    """Migrations are forward-only (TDS §8.4, §10.6).

    Raises:
        RuntimeError: Always.
    """
    msg = (
        "DrugSim migrations are forward-only. Roll forward with a new migration "
        "rather than downgrading (TDS §8.4)."
    )
    raise RuntimeError(msg)
