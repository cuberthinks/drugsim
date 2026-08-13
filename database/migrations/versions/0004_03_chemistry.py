"""chemistry domain

Revision ID: 0004
Revises: '0003'
Create Date: 2026-08-06

Generated from database/ddl/03_chemistry.sql at authoring time — see that file's
README for why this migration embeds the SQL directly rather than reading the
(mutable) ddl file at run time.
"""

from __future__ import annotations

from typing import Optional

from alembic import op

revision: str = "0004"
down_revision: Optional[str] = '0003'
branch_labels: Optional[str] = None
depends_on: Optional[str] = None

_SQL = r"""
-- DrugSim — Chemistry domain
-- Phase 1 Step 3 §4, with the Step 4 §1 correction and the Step 4 §2.2
-- multi-component-structure fields folded in directly (written fresh here rather
-- than as a later ALTER, since there is no prior version of this table to correct).

-- ============================================================================
-- compound — surrogate-keyed identity (ADR-008)
-- ============================================================================

CREATE TABLE compound (
    compound_uid          ulid           PRIMARY KEY,
    source_smiles         TEXT           NOT NULL,
    canonical_smiles      TEXT           NOT NULL,
    isomeric_smiles       TEXT           NOT NULL,
    standardized_smiles   TEXT           NOT NULL,
    parent_smiles         TEXT,
    inchi                 TEXT           NOT NULL,
    inchikey_full         inchikey27     NOT NULL,
    inchikey_skeleton     inchikey14     NOT NULL,
    parent_inchikey       inchikey27,
    molecular_formula     TEXT           NOT NULL CHECK (molecular_formula ~ '^([A-Z][a-z]?[0-9]*)+$'),
    bemis_murcko_scaffold TEXT,
    generic_scaffold      TEXT,
    stereo_completeness   stereo_state_t NOT NULL,
    standardization_flags TEXT[]         NOT NULL DEFAULT '{}',

    -- Multi-component structures (Phase 1 Step 4 §2.2). A genuine mixture with no
    -- clear parent is flagged and excluded from descriptor computation rather than
    -- silently reduced to its largest fragment — that would compute descriptors
    -- for a molecule that was never tested.
    component_count       SMALLINT       NOT NULL DEFAULT 1 CHECK (component_count > 0),
    is_mixture             BOOLEAN        NOT NULL DEFAULT FALSE,

    mol                   mol            NOT NULL,
    morgan_fp_r2_2048     bfp            NOT NULL,

    -- Provenance (Phase 1 data dictionary §B) — per-record, not per-dataset, because
    -- BindingDB is internally split-licensed (ADR-007).
    source_id             TEXT           NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    source_record_id      TEXT,
    snapshot_id           TEXT           NOT NULL REFERENCES ingestion_snapshot (snapshot_id) ON DELETE RESTRICT,
    source_license        TEXT           NOT NULL,
    license_tier          license_tier_t NOT NULL,
    is_commercial_ok      BOOLEAN        NOT NULL,
    toolchain_id          TEXT           NOT NULL REFERENCES toolchain (toolchain_id) ON DELETE RESTRICT,
    pipeline_version       git_sha       NOT NULL,
    drugsim_release        semver        NOT NULL,
    ingested_at            TIMESTAMPTZ   NOT NULL DEFAULT now(),

    -- Governance (P8: nothing deleted or silently altered)
    created_by             ulid          NOT NULL REFERENCES system_user (user_uid) ON DELETE RESTRICT,
    is_deleted              BOOLEAN      NOT NULL DEFAULT FALSE,
    deleted_reason          TEXT,

    CONSTRAINT uq_compound_inchikey UNIQUE (inchikey_full),
    CONSTRAINT ck_skeleton_prefix CHECK (inchikey_skeleton = LEFT(inchikey_full, 14)),
    CONSTRAINT ck_deleted_reason CHECK (NOT is_deleted OR deleted_reason IS NOT NULL),
    CONSTRAINT ck_mixture_no_parent CHECK (NOT is_mixture OR parent_inchikey IS NULL)
);

CREATE INDEX ix_compound_mol      ON compound USING gist (mol);
CREATE INDEX ix_compound_fp       ON compound USING gist (morgan_fp_r2_2048);
CREATE INDEX ix_compound_parentik ON compound (parent_inchikey) WHERE parent_inchikey IS NOT NULL;
CREATE INDEX ix_compound_skeleton ON compound (inchikey_skeleton);
CREATE INDEX ix_compound_tier     ON compound (license_tier) WHERE NOT is_deleted;
CREATE INDEX ix_compound_scaffold ON compound (bemis_murcko_scaffold) WHERE bemis_murcko_scaffold IS NOT NULL;

COMMENT ON CONSTRAINT ck_skeleton_prefix ON compound IS
    'Makes the derived-field relationship a database invariant rather than a '
    'pipeline promise — cheap, and it catches a whole class of ETL bug.';

COMMENT ON INDEX ix_compound_mol IS
    'Substructure search (mol @> query). Without the RDKit cartridge this becomes '
    'a full scan over ~3M rows (ADR-003).';

COMMENT ON INDEX ix_compound_fp IS
    'Tanimoto similarity search (fp % query).';

-- ============================================================================
-- compound_descriptor — versioned per toolchain (ADR-005)
-- ============================================================================
-- Step 4 §1 correction applied: logd_74 and logs_mol_l are NOT columns here.
-- LogP is a deterministic function of structure (Crippen); LogD and LogS are
-- measured or predicted quantities and belong in measurement/prediction, never in
-- a version-pinned deterministic-computation table (P4).

CREATE TABLE compound_descriptor (
    compound_uid            ulid  NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    descriptor_spec_version TEXT  NOT NULL REFERENCES descriptor_spec (descriptor_spec_version) ON DELETE RESTRICT,

    mw_g_mol            NUMERIC(10, 4) NOT NULL CHECK (mw_g_mol > 0 AND mw_g_mol < 10000),
    mw_parent_g_mol     NUMERIC(10, 4) CHECK (mw_parent_g_mol > 0),
    exact_mass_g_mol    NUMERIC(12, 6) NOT NULL CHECK (exact_mass_g_mol > 0),
    logp_crippen        NUMERIC(8, 4)  NOT NULL,
    molar_refractivity  NUMERIC(8, 3)  CHECK (molar_refractivity >= 0),
    tpsa_a2             NUMERIC(8, 3)  NOT NULL CHECK (tpsa_a2 >= 0 AND tpsa_a2 < 1000),
    rotatable_bonds     INTEGER        NOT NULL CHECK (rotatable_bonds BETWEEN 0 AND 200),
    aromatic_rings      INTEGER        NOT NULL CHECK (aromatic_rings >= 0),
    ring_count          INTEGER        NOT NULL CHECK (ring_count >= 0),
    heavy_atom_count    INTEGER        NOT NULL CHECK (heavy_atom_count > 0),
    formal_charge       INTEGER        NOT NULL CHECK (formal_charge BETWEEN -20 AND 20),

    -- Both HBD/HBA conventions are stored — RDKit's two definitions disagree for
    -- the same molecule (Phase 1 Step 4 §E.1). Rule evaluation must always use the
    -- *_lipinski variants; the strict variants are available for modelling but must
    -- never be substituted into rule evaluation.
    hbd_lipinski        INTEGER        NOT NULL CHECK (hbd_lipinski >= 0),
    hba_lipinski        INTEGER        NOT NULL CHECK (hba_lipinski >= 0),
    hbd_strict          INTEGER        NOT NULL CHECK (hbd_strict >= 0),
    hba_strict          INTEGER        NOT NULL CHECK (hba_strict >= 0),

    heteroatom_count    INTEGER        NOT NULL CHECK (heteroatom_count >= 0),
    fraction_csp3       NUMERIC(6, 5)  NOT NULL CHECK (fraction_csp3 BETWEEN 0 AND 1),
    num_stereocentres   INTEGER        NOT NULL CHECK (num_stereocentres >= 0),
    largest_ring_size   INTEGER        CHECK (largest_ring_size >= 0),
    computed_at         TIMESTAMPTZ    NOT NULL DEFAULT now(),

    PRIMARY KEY (compound_uid, descriptor_spec_version),
    CONSTRAINT ck_mass_consistency CHECK (abs(exact_mass_g_mol - mw_g_mol) < 0.5)
);

CREATE INDEX ix_desc_mw   ON compound_descriptor (descriptor_spec_version, mw_g_mol);
CREATE INDEX ix_desc_logp ON compound_descriptor (descriptor_spec_version, logp_crippen);

COMMENT ON TABLE compound_descriptor IS
    'Composite PK (compound_uid, descriptor_spec_version) is the point: descriptors '
    'computed under different RDKit versions coexist as separate rows, so a model '
    'trained last year remains reproducible after a toolchain upgrade. Putting '
    'descriptors as plain columns on compound — the obvious design — silently '
    'destroys that and is the most common reproducibility failure in cheminformatics '
    'databases.';

COMMENT ON CONSTRAINT ck_mass_consistency ON compound_descriptor IS
    'Catches unit and parsing errors early: monoisotopic and average mass diverge '
    'for heavy elements but never by >=0.5 Da for drug-like molecules.';

-- ============================================================================
-- compound_drug_likeness
-- ============================================================================

CREATE TABLE compound_drug_likeness (
    compound_uid            ulid NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    descriptor_spec_version TEXT NOT NULL REFERENCES descriptor_spec (descriptor_spec_version) ON DELETE RESTRICT,

    lipinski_violations   INTEGER       NOT NULL CHECK (lipinski_violations BETWEEN 0 AND 4),
    lipinski_pass         BOOLEAN       NOT NULL,
    veber_pass            BOOLEAN       NOT NULL,
    ghose_pass            BOOLEAN       NOT NULL,
    egan_pass             BOOLEAN       NOT NULL,
    muegge_pass           BOOLEAN       NOT NULL,
    rule_of_three_pass    BOOLEAN       NOT NULL,
    -- Martin (2005) tiers. Corrected in Sprint 2.5: the original CHECK omitted
    -- 0.85 (the top anion tier) entirely -- the real rule is anions scored by
    -- TPSA (0.85/0.56/0.11), neutral/zwitterionic/cationic scored by Lipinski
    -- Ro5 pass/fail (0.55/0.17). See src/drugsim_chem/drug_likeness.py for
    -- the corrected implementation and the ionisation-state caveat.
    bioavailability_score NUMERIC(4, 3) NOT NULL
        CHECK (bioavailability_score IN (0.110, 0.170, 0.550, 0.560, 0.850)),
    qed_score             prob_unit     NOT NULL,
    sa_score              NUMERIC(5, 3) NOT NULL CHECK (sa_score BETWEEN 1 AND 10),
    np_likeness_score     NUMERIC(6, 3),
    pains_alerts          INTEGER       NOT NULL CHECK (pains_alerts >= 0),
    brenk_alerts          INTEGER       NOT NULL CHECK (brenk_alerts >= 0),
    cns_mpo_score         NUMERIC(4, 2) CHECK (cns_mpo_score BETWEEN 0 AND 6),
    -- Extended rule catalogue (Phase 1 Step 4 §7). Only the two rules the
    -- pipeline (src/drugsim_chem/drug_likeness.py) actually computes are
    -- added here; the remaining catalogue entries (golden_triangle_pass,
    -- lead_like_pass, reos_pass, bbb_likelihood_pass, mce_18) are deferred —
    -- unimplemented rules with no column would be a schema promising data
    -- that is never populated.
    -- Named "_flag" not "_pass": these mark elevated risk, not failure
    -- (Step 4 §7) — a downstream reader must not assume the "_pass" polarity.
    pfizer_3_75_flag       BOOLEAN,
    gsk_4_400_flag         BOOLEAN       NOT NULL,
    rule_catalogue_version TEXT          NOT NULL DEFAULT 'v1',

    PRIMARY KEY (compound_uid, descriptor_spec_version),
    FOREIGN KEY (compound_uid, descriptor_spec_version)
        REFERENCES compound_descriptor (compound_uid, descriptor_spec_version) ON DELETE RESTRICT,
    CONSTRAINT ck_lipinski_consistency CHECK (lipinski_pass = (lipinski_violations <= 1))
);

COMMENT ON TABLE compound_drug_likeness IS
    'Separate from compound_descriptor because rules are interpretations of '
    'descriptors and their definitions evolve independently. The composite FK '
    'guarantees a rule verdict can never reference descriptors that do not exist '
    'under the same spec version. bioavailability_score is a coarse 4-tier '
    'heuristic, not a calibrated probability — present because conventional, not '
    'because it should be trusted as one.';

-- ============================================================================
-- compound_split_assignment — global, once-assigned (ADR-009)
-- ============================================================================

CREATE TABLE compound_split_assignment (
    compound_uid        ulid        PRIMARY KEY REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    scaffold_key         TEXT        NOT NULL,
    split_group          INTEGER     NOT NULL CHECK (split_group BETWEEN 0 AND 9),
    split_salt           TEXT        NOT NULL,
    assigned_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    assigned_in_release  semver      NOT NULL,
    is_frozen            BOOLEAN     NOT NULL DEFAULT TRUE
);

CREATE INDEX ix_split_group    ON compound_split_assignment (split_group);
CREATE INDEX ix_split_scaffold ON compound_split_assignment (scaffold_key);

-- The leakage guarantee expressed as a constraint, not a pipeline convention: one
-- scaffold cannot map to two split groups. Cross-dataset leakage (Step 2 §8.3)
-- becomes a database-level impossibility.
CREATE UNIQUE INDEX uq_scaffold_single_group
    ON compound_split_assignment (scaffold_key, split_group);

COMMENT ON INDEX uq_scaffold_single_group IS
    'A scaffold present in Caco-2 training data and DILI test data would leak '
    'across any multi-task model or shared encoder. With 475-compound datasets '
    '(Phase 1 Step 1), a handful of leaked scaffolds materially moves the metric. '
    'This index makes that impossible rather than merely discouraged.';

-- ============================================================================
-- compound_xref — external identifier cross-references
-- ============================================================================

CREATE TABLE compound_xref (
    xref_uid     ulid NOT NULL PRIMARY KEY,
    compound_uid ulid NOT NULL REFERENCES compound (compound_uid) ON DELETE RESTRICT,
    xref_source  TEXT NOT NULL,
    xref_id      TEXT NOT NULL,
    is_primary   BOOLEAN NOT NULL DEFAULT FALSE,
    source_id    TEXT NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    CONSTRAINT uq_xref UNIQUE (compound_uid, xref_source, xref_id)
);

CREATE INDEX ix_xref_lookup ON compound_xref (xref_source, xref_id);
"""


def upgrade() -> None:
    """Apply 03_chemistry.sql."""
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
