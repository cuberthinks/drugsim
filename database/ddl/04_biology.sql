-- DrugSim — Biology domain
-- Phase 1 Step 3 §5. Extension tables from Step 6 (orthologs, transporter
-- directionality, tissue expression, ontology closure) are deferred — see
-- database/ddl/README.md.

CREATE TABLE organism (
    taxon_id        INTEGER PRIMARY KEY,
    scientific_name TEXT    NOT NULL UNIQUE,
    common_name     TEXT
);

CREATE TABLE gene (
    gene_uid     ulid    PRIMARY KEY,
    hgnc_symbol  TEXT,
    ensembl_id   TEXT,
    ncbi_gene_id INTEGER,
    taxon_id     INTEGER NOT NULL REFERENCES organism (taxon_id) ON DELETE RESTRICT,
    CONSTRAINT uq_gene_ensembl UNIQUE (ensembl_id),
    CONSTRAINT ck_gene_has_id CHECK (hgnc_symbol IS NOT NULL OR ensembl_id IS NOT NULL)
);

CREATE TABLE protein (
    protein_uid        ulid           PRIMARY KEY,
    uniprot_accession  uniprot_acc    NOT NULL,
    uniprot_entry_name TEXT,
    isoform_id         TEXT,
    is_reviewed        BOOLEAN        NOT NULL,
    gene_uid           ulid           REFERENCES gene (gene_uid) ON DELETE RESTRICT,
    taxon_id           INTEGER        NOT NULL REFERENCES organism (taxon_id) ON DELETE RESTRICT,
    sequence           TEXT           CHECK (sequence ~ '^[ACDEFGHIKLMNPQRSTVWYUOXBZJ]+$'),
    sequence_length    INTEGER        CHECK (sequence_length > 0),
    ec_number          TEXT           CHECK (ec_number ~ '^\d+\.\d+\.\d+\.\d+$'),
    protein_class      TEXT,
    is_enzyme          BOOLEAN        NOT NULL DEFAULT FALSE,
    is_transporter     BOOLEAN        NOT NULL DEFAULT FALSE,
    source_id          TEXT           NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    license_tier       license_tier_t NOT NULL,
    CONSTRAINT uq_protein UNIQUE (uniprot_accession, isoform_id),
    CONSTRAINT ck_seq_length CHECK (sequence IS NULL OR length(sequence) = sequence_length)
);

CREATE INDEX ix_protein_reviewed    ON protein (uniprot_accession) WHERE is_reviewed;
CREATE INDEX ix_protein_enzyme      ON protein (protein_uid) WHERE is_enzyme;
CREATE INDEX ix_protein_transporter ON protein (protein_uid) WHERE is_transporter;

COMMENT ON COLUMN protein.is_reviewed IS
    'Swiss-Prot (true) vs TrEMBL (false). Ground truth is restricted to Swiss-Prot '
    '(Phase 1 Step 1 §3.6) — TrEMBL is automated annotation, unsuitable as labels.';

COMMENT ON TABLE protein IS
    'is_enzyme / is_transporter are roles, not types — CYP3A4 is a protein that '
    'happens to be an enzyme, and many proteins hold multiple roles. Separate '
    'tables would force duplication; partial indexes give the query performance '
    'of separate tables without the modelling error.';

CREATE TABLE target (
    target_uid       ulid           PRIMARY KEY,
    target_name      TEXT           NOT NULL,
    target_type      TEXT           NOT NULL CHECK (target_type IN (
        'SINGLE PROTEIN', 'PROTEIN COMPLEX', 'PROTEIN FAMILY', 'PROTEIN-PROTEIN INTERACTION',
        'CHIMERIC PROTEIN', 'SELECTIVITY GROUP', 'ORGANISM', 'TISSUE', 'CELL-LINE',
        'NUCLEIC-ACID', 'SUBCELLULAR', 'UNKNOWN'
    )),
    taxon_id         INTEGER        REFERENCES organism (taxon_id) ON DELETE RESTRICT,
    chembl_target_id TEXT,
    source_id        TEXT           NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT,
    license_tier     license_tier_t NOT NULL
);

CREATE TABLE target_component (
    target_uid    ulid    NOT NULL REFERENCES target (target_uid) ON DELETE RESTRICT,
    protein_uid   ulid    NOT NULL REFERENCES protein (protein_uid) ON DELETE RESTRICT,
    stoichiometry INTEGER CHECK (stoichiometry > 0),
    PRIMARY KEY (target_uid, protein_uid)
);

COMMENT ON TABLE target IS
    'target and protein are distinct entities, mirroring ChEMBL''s model. A target '
    'may be a complex, a family, or a cell line — not always one protein. '
    'Collapsing them loses the distinction between "binds EGFR" and "binds an '
    'EGFR-containing complex", which matters for both mechanism and selectivity.';

CREATE TABLE disease (
    disease_uid ulid PRIMARY KEY,
    efo_id      TEXT,
    mondo_id    TEXT,
    mesh_id     TEXT,
    name        TEXT NOT NULL,
    CONSTRAINT ck_disease_ontology CHECK (coalesce(efo_id, mondo_id, mesh_id) IS NOT NULL)
);

CREATE TABLE pathway (
    pathway_uid ulid PRIMARY KEY,
    reactome_id TEXT,
    kegg_id     TEXT,
    go_id       TEXT,
    name        TEXT NOT NULL,
    source_id   TEXT NOT NULL REFERENCES data_source (source_id) ON DELETE RESTRICT
);

CREATE TABLE drug_class (
    drug_class_uid ulid PRIMARY KEY,
    atc_code       TEXT,
    chebi_id       TEXT,
    name           TEXT NOT NULL,
    parent_uid     ulid REFERENCES drug_class (drug_class_uid) ON DELETE RESTRICT
);

COMMENT ON COLUMN drug_class.parent_uid IS
    'Self-reference implementing the ATC hierarchy, which is a strict tree — '
    'unlike disease/pathway ontologies (EFO, MONDO, GO), which are DAGs and would '
    'need the ontology_relation/ontology_closure pattern from Step 6 instead '
    '(deferred; see database/ddl/README.md). Traversal uses recursive CTEs '
    '(ADR-004) pending a demonstrated need for a graph store.';
