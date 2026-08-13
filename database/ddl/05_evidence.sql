-- DrugSim — Evidence domain: endpoints, assays, measurements
-- Phase 1 Step 3 §6, with the Step 4 §1 relaxation of ck_direction applied
-- directly (physicochemical endpoints such as logD/logS have no universal
-- "higher is worse" direction).

-- ============================================================================
-- endpoint — the canonical unit registry, as data rather than as documentation
-- ============================================================================
-- This table exists because Therapeutics Data Commons does not document units
-- for most ADME/Tox endpoints (verified 2026-08-05, Phase 1 Step 1). Unit
-- correctness cannot be asserted from documentation and is instead asserted
-- empirically at gate G4 — see unit_verified_method.

CREATE TABLE endpoint (
    endpoint_id           TEXT             PRIMARY KEY,
    endpoint_class        endpoint_class_t NOT NULL,
    display_name          TEXT             NOT NULL,
    canonical_unit        TEXT             NOT NULL,
    is_categorical        BOOLEAN          NOT NULL,
    expected_min          NUMERIC(14, 6),
    expected_max          NUMERIC(14, 6),
    higher_is_worse       BOOLEAN,
    species_specific      BOOLEAN          NOT NULL DEFAULT TRUE,
    unit_verified_method  TEXT             NOT NULL
        CHECK (unit_verified_method IN ('documented', 'range_assertion', 'cross_source', 'unverified')),
    oecd_defined_endpoint TEXT,
    notes                 TEXT,
    CONSTRAINT ck_continuous_bounds
        CHECK (is_categorical OR (expected_min IS NOT NULL AND expected_max IS NOT NULL)),
    -- Step 4 §1 relaxation: physicochemical endpoints (logD, logS) have no
    -- universal direction of "worse" — the CHECK permits NULL only there.
    CONSTRAINT ck_direction
        CHECK (is_categorical OR higher_is_worse IS NOT NULL OR endpoint_class = 'physicochemical')
);

COMMENT ON COLUMN endpoint.higher_is_worse IS
    'NOT NULL for continuous, non-physicochemical endpoints by construction '
    '(ck_direction) — this exists specifically to force an explicit decision on '
    'cases like LD50, where a sign inversion trains cleanly and reports good '
    'metrics while ranking safe compounds as dangerous (Phase 1 Step 2 §G.1, the '
    'highest-risk conversion in the system).';

COMMENT ON COLUMN endpoint.unit_verified_method IS
    'Gate UV-05 refuses publication while this remains ''unverified''. Nothing '
    'reaches a model with unknown units.';

-- ============================================================================
-- assay
-- ============================================================================

CREATE TABLE assay (
    assay_uid        ulid           PRIMARY KEY,
    source_assay_id  TEXT,
    description      TEXT,
    assay_type       CHAR(1)        CHECK (assay_type IN ('B', 'F', 'A', 'T', 'P', 'U')),
    taxon_id         INTEGER        REFERENCES organism (taxon_id) ON DELETE RESTRICT,
    tissue           TEXT,
    cell_line        TEXT,
    confidence_score SMALLINT       CHECK (confidence_score BETWEEN 0 AND 9),
    target_uid       ulid           REFERENCES target (target_uid) ON DELETE RESTRICT,
    reference_doi    TEXT,
    reference_pmid   TEXT,
    source_id        TEXT           NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    snapshot_id      TEXT           NOT NULL REFERENCES ingestion_snapshot (snapshot_id) ON DELETE RESTRICT,
    license_tier     license_tier_t NOT NULL,
    assay_metadata   JSONB          NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX ix_assay_target ON assay (target_uid) WHERE target_uid IS NOT NULL;
CREATE INDEX ix_assay_conf   ON assay (confidence_score) WHERE confidence_score >= 8;

COMMENT ON INDEX ix_assay_conf IS
    'Serves the standard training-set filter (confidence_score >= 8, Phase 1 '
    'Step 1 §3.1).';

-- ============================================================================
-- measurement — supertype, LIST-partitioned by license_tier
-- ============================================================================
-- Partitioning makes the licence audit a partition scan (LC-03) and lets black-
-- tier data be physically isolated or dropped wholesale for a commercial build.
-- The partition key must be in the primary key, hence the composite PK — a
-- deliberate, documented 3NF exception (Phase 1 Step 3 §11.3).

CREATE TABLE measurement (
    measurement_uid       ulid             NOT NULL,
    license_tier          license_tier_t   NOT NULL,
    compound_uid          ulid             NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    endpoint_id           TEXT             NOT NULL REFERENCES endpoint (endpoint_id) ON DELETE RESTRICT,
    assay_uid             ulid             REFERENCES assay (assay_uid) ON DELETE RESTRICT,

    -- Value, per ADR-012: source and canonical forms both retained, with the
    -- conversion audited, so a unit fix is correctable without re-ingestion.
    source_value          NUMERIC(14, 6),
    source_unit           TEXT,
    canonical_value       NUMERIC(14, 6),
    canonical_unit        TEXT             NOT NULL,
    conversion_factor     NUMERIC(18, 9),
    conversion_formula    TEXT,
    conversion_mw_basis   TEXT             CHECK (conversion_mw_basis IN ('parent', 'salt', 'n_a')),
    unit_verified_method  TEXT             NOT NULL
        CHECK (unit_verified_method IN ('documented', 'range_assertion', 'cross_source', 'unverified')),

    value_relation        value_relation_t NOT NULL DEFAULT '=',
    measurement_status    meas_status_t    NOT NULL,
    evidence_type         evidence_type_t  NOT NULL,

    taxon_id              INTEGER          REFERENCES organism (taxon_id) ON DELETE RESTRICT,
    tissue_or_system      TEXT,
    ph_reference          NUMERIC(4, 2)    CHECK (ph_reference BETWEEN 0 AND 14),
    temperature_c         NUMERIC(5, 2)    CHECK (temperature_c BETWEEN -80 AND 200),
    n_replicates          INTEGER          CHECK (n_replicates > 0),
    std_error             NUMERIC(14, 6)   CHECK (std_error >= 0),
    loq_value             NUMERIC(14, 6),
    loq_unit              TEXT,
    confidence_score      prob_unit,
    data_validity_flag    TEXT,

    source_id             TEXT             NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    source_record_id      TEXT,
    snapshot_id           TEXT             NOT NULL REFERENCES ingestion_snapshot (snapshot_id) ON DELETE RESTRICT,
    source_license        TEXT             NOT NULL,
    is_commercial_ok      BOOLEAN          NOT NULL,
    pipeline_version      git_sha          NOT NULL,
    drugsim_release       semver           NOT NULL,
    ingested_at           TIMESTAMPTZ      NOT NULL DEFAULT now(),
    created_by            ulid             NOT NULL REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    is_deleted            BOOLEAN          NOT NULL DEFAULT FALSE,
    deleted_reason        TEXT,

    PRIMARY KEY (measurement_uid, license_tier),

    -- P4 as a database constraint, not a convention: a predicted value cannot be
    -- inserted into a measurement table, whatever a future developer intends.
    CONSTRAINT ck_not_predicted CHECK (evidence_type <> 'predicted'),

    -- Three distinct null states (Phase 1 Step 2 §8.4) never collapse to a bare NULL.
    CONSTRAINT ck_status_value CHECK (
        (measurement_status = 'measured' AND canonical_value IS NOT NULL)
        OR (measurement_status IN ('below_loq', 'above_loq') AND loq_value IS NOT NULL)
        OR (measurement_status IN ('not_measured', 'inconclusive', 'withdrawn_by_source'))
    ),
    CONSTRAINT ck_logd_ph CHECK (endpoint_id <> 'logd_74' OR ph_reference IS NOT NULL),
    CONSTRAINT ck_deleted_reason CHECK (NOT is_deleted OR deleted_reason IS NOT NULL)
) PARTITION BY LIST (license_tier);

CREATE TABLE measurement_green PARTITION OF measurement FOR VALUES IN ('green');
CREATE TABLE measurement_amber PARTITION OF measurement FOR VALUES IN ('amber');
CREATE TABLE measurement_red   PARTITION OF measurement FOR VALUES IN ('red');
CREATE TABLE measurement_black PARTITION OF measurement FOR VALUES IN ('black');

CREATE INDEX ix_meas_compound_endpoint ON measurement (compound_uid, endpoint_id);
CREATE INDEX ix_meas_endpoint          ON measurement (endpoint_id) WHERE NOT is_deleted;
CREATE INDEX ix_meas_assay             ON measurement (assay_uid);
CREATE INDEX ix_meas_uncensored        ON measurement (endpoint_id, canonical_value)
    WHERE value_relation = '=' AND measurement_status = 'measured' AND NOT is_deleted;
CREATE INDEX ix_meas_ingested          ON measurement USING brin (ingested_at);

COMMENT ON CONSTRAINT ck_not_predicted ON measurement IS
    'The database-level enforcement of P4. See tests/constraints for the '
    'violating-insert test that proves this actually rejects predicted data.';

COMMENT ON INDEX ix_meas_uncensored IS
    'The workhorse: nearly every training query wants uncensored, measured, '
    'non-deleted values for one endpoint. A partial index keeps it small and '
    'makes accidentally including censored records require deliberate effort.';

-- ============================================================================
-- measurement_bioactivity / measurement_toxicology — disjoint subtypes
-- ============================================================================
-- Neither table duplicates the ~30 shared provenance columns on measurement, and
-- neither is forced into a single wide, mostly-NULL table (Phase 1 Step 3 §6.4).

CREATE TABLE measurement_bioactivity (
    measurement_uid   ulid           NOT NULL,
    license_tier      license_tier_t NOT NULL,
    target_uid        ulid           NOT NULL REFERENCES target (target_uid) ON DELETE RESTRICT,
    activity_type     TEXT           NOT NULL CHECK (activity_type IN
        ('IC50', 'EC50', 'Ki', 'Kd', 'AC50', 'GI50', 'ED50', 'Potency')),
    pchembl_value     NUMERIC(6, 3)  CHECK (pchembl_value BETWEEN 0 AND 14),
    ligand_efficiency NUMERIC(8, 4),
    PRIMARY KEY (measurement_uid, license_tier),
    FOREIGN KEY (measurement_uid, license_tier)
        REFERENCES measurement (measurement_uid, license_tier) ON DELETE RESTRICT
);

CREATE INDEX ix_bioact_target ON measurement_bioactivity (target_uid, pchembl_value);

CREATE TABLE measurement_toxicology (
    measurement_uid      ulid           NOT NULL,
    license_tier         license_tier_t NOT NULL,
    tox_category         TEXT           NOT NULL CHECK (tox_category IN (
        'hepatotoxicity', 'cardiotoxicity', 'nephrotoxicity', 'neurotoxicity',
        'mutagenicity', 'carcinogenicity', 'genotoxicity', 'cytotoxicity',
        'developmental_toxicity', 'herg_inhibition', 'ames', 'ld50', 'noael',
        'skin_sensitisation'
    )),
    administration_route  TEXT           CHECK (administration_route IN
        ('oral', 'iv', 'ip', 'dermal', 'inhalation', 'subcutaneous', 'other', 'n_a')),
    exposure_duration_h   NUMERIC(10, 2) CHECK (exposure_duration_h >= 0),
    dose_value            NUMERIC(14, 6),
    dose_unit             TEXT,
    study_guideline       TEXT,
    is_glp                BOOLEAN,
    PRIMARY KEY (measurement_uid, license_tier),
    FOREIGN KEY (measurement_uid, license_tier)
        REFERENCES measurement (measurement_uid, license_tier) ON DELETE RESTRICT
);

CREATE INDEX ix_tox_category ON measurement_toxicology (tox_category);

COMMENT ON COLUMN measurement_toxicology.is_glp IS
    'An OECD-guideline GLP study and a literature Ames result are not equivalent '
    'evidence; a regulatory submission must be able to distinguish them.';
