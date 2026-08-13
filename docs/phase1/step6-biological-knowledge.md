# DrugSim — Phase 1, Step 6
## Biological Knowledge Database

**Document status:** Draft for approval
**Date:** 2026-08-05
**Depends on:** Steps 1–5 (approved)
**Extends:** Step 3 Domain C (biology) and Domain F (relations)

---

## 1. Coverage of the Brief

| Brief entity | Status |
|---|---|
| Proteins | Step 3 §5 `protein` |
| Genes | Step 3 §5 `gene` |
| Pathways | Step 3 §5 `pathway` |
| Diseases | Step 3 §5 `disease` |
| Targets | Step 3 §5 `target` + `target_component` |
| Drug Classes | Step 3 §5 `drug_class` (self-referencing ATC hierarchy) |
| Enzymes | `protein.is_enzyme` + partial index — role, not type (§2.1) |
| Transporters | `protein.is_transporter` — **extended below**, directionality was missing |
| Drug-Target Interactions | Step 3 §8 `drug_target_interaction` |
| Protein Binding Affinity | Step 3 §6.4 `measurement_bioactivity` (Ki/Kd/IC50 + pChEMBL) |
| Metabolic Enzymes | Step 5 §3 `endpoint_protein` with `interaction_role` |
| Biological Pathways | Step 3 §5 + §8 `protein_pathway` |

The structural work is done. This step fills five gaps that matter scientifically and were not covered.

---

## 2. Gap 1 — Transporter Directionality

`is_transporter` is a boolean, which loses the single most important property of a transporter.

**Why it matters:** P-glycoprotein is an **efflux** pump — it pushes drug *out* of cells, reducing brain penetration and oral absorption. OATP1B1 is an **uptake** transporter — it pulls drug *into* hepatocytes, increasing hepatic exposure and clearance. Both are "transporters"; their ADMET consequences are opposite. A model told only that a compound interacts with "a transporter" has been given almost no information.

```sql
CREATE TABLE transporter_property (
    protein_uid      ulid PRIMARY KEY REFERENCES protein(protein_uid) ON DELETE RESTRICT,
    transport_direction TEXT NOT NULL CHECK (transport_direction IN ('efflux','uptake','bidirectional')),
    transporter_family  TEXT CHECK (transporter_family IN ('ABC','SLC','other')),
    primary_tissue      TEXT[],
    is_bbb_relevant     BOOLEAN NOT NULL DEFAULT FALSE,
    is_hepatic_uptake   BOOLEAN NOT NULL DEFAULT FALSE,
    is_renal_secretion  BOOLEAN NOT NULL DEFAULT FALSE,
    is_intestinal       BOOLEAN NOT NULL DEFAULT FALSE
);
```

The tissue-relevance flags exist because the same transporter has different consequences by location: intestinal P-gp limits absorption, BBB P-gp limits CNS exposure, renal P-gp drives secretion. A single "P-gp substrate" prediction means different things depending on which question is being asked.

---

## 3. Gap 2 — Species Orthology

**This is the most consequential gap in the biology domain**, and it goes to the heart of what DrugSim claims to do.

DrugSim predicts human outcomes, but a large share of the available toxicity data is rodent (LD50 is typically rat; repeat-dose toxicity is rat and dog). Translating animal findings to human requires knowing whether the relevant protein is conserved — and often it is not:

- **Rat CYP enzymes differ substantially from human**; rodent metabolic profiles frequently mispredict human metabolism
- **hERG is well conserved**, which is why cardiac safety translates comparatively well
- Some human targets have **no rodent ortholog at all**, making animal data structurally uninformative for them

Without orthology, DrugSim would silently treat "toxic in rat" as evidence about humans, with no way to flag when that inference is unsupported. That is exactly the kind of confident-but-wrong output Step 1 §5.5 warned about.

```sql
CREATE TABLE protein_ortholog (
    ortholog_uid     ulid PRIMARY KEY,
    protein_uid_a    ulid NOT NULL REFERENCES protein(protein_uid) ON DELETE RESTRICT,
    protein_uid_b    ulid NOT NULL REFERENCES protein(protein_uid) ON DELETE RESTRICT,
    relationship     TEXT NOT NULL CHECK (relationship IN
        ('one_to_one','one_to_many','many_to_many','no_ortholog')),
    sequence_identity_pct NUMERIC(5,2) CHECK (sequence_identity_pct BETWEEN 0 AND 100),
    confidence       prob_unit,
    source_id        TEXT NOT NULL REFERENCES data_source(source_id) ON DELETE RESTRICT,
    license_tier     license_tier_t NOT NULL,
    CONSTRAINT ck_ortholog_distinct CHECK (protein_uid_a <> protein_uid_b),
    CONSTRAINT uq_ortholog UNIQUE (protein_uid_a, protein_uid_b, source_id)
);
CREATE INDEX ix_ortholog_a ON protein_ortholog (protein_uid_a);
```

**`relationship = 'no_ortholog'` is a first-class value, not an absence of rows.** "We know there is no rodent ortholog" and "we have not checked" are different states, and only the former justifies discounting animal data. Encoding the negative explicitly is what lets the system say *why* it is discounting evidence.

**Downstream use:** any cross-species inference records the orthology basis, and a translation with low sequence identity or no ortholog degrades the confidence of the resulting prediction rather than proceeding silently.

Candidate sources: Ensembl Compara, OrthoDB, UniProt cross-references. Licences to verify before ingestion.

---

## 4. Gap 3 — Tissue Expression

Target expression determines where on-target toxicity will occur. A target expressed only in tumour tissue has a very different safety profile from one also expressed in cardiac muscle — and this is knowable in advance, from expression data, before any toxicity is measured.

```sql
CREATE TABLE protein_tissue_expression (
    protein_uid   ulid NOT NULL REFERENCES protein(protein_uid) ON DELETE RESTRICT,
    tissue_uberon_id TEXT NOT NULL,
    tissue_name   TEXT NOT NULL,
    expression_level TEXT CHECK (expression_level IN ('not_detected','low','medium','high')),
    expression_value NUMERIC(12,4),
    expression_unit  TEXT CHECK (expression_unit IN ('nTPM','TPM','FPKM','protein_score')),
    taxon_id      INTEGER NOT NULL REFERENCES organism(taxon_id) ON DELETE RESTRICT,
    source_id     TEXT NOT NULL REFERENCES data_source(source_id) ON DELETE RESTRICT,
    license_tier  license_tier_t NOT NULL,
    PRIMARY KEY (protein_uid, tissue_uberon_id, taxon_id, source_id)
);
CREATE INDEX ix_expr_tissue ON protein_tissue_expression (tissue_uberon_id, expression_level);
```

UBERON is used as the tissue ontology because it is the cross-species standard and integrates with Open Targets (CC0, Step 1). Expression data is available via Open Targets and Human Protein Atlas — **HPA's licence needs verification before ingestion**; it is not confirmed in Step 1.

---

## 5. Gap 4 — Ontology Hierarchies Are DAGs, Not Trees

Disease and pathway ontologies (EFO, MONDO, GO, Reactome) are **directed acyclic graphs**: a term can have multiple parents. "Hepatocellular carcinoma" is both a liver disease and a carcinoma. A `parent_uid` self-reference — the pattern used for `drug_class` in Step 3, which is correct there because ATC *is* a strict tree — cannot represent this.

```sql
CREATE TABLE ontology_relation (
    child_uid    ulid NOT NULL,
    parent_uid   ulid NOT NULL,
    ontology     TEXT NOT NULL CHECK (ontology IN ('EFO','MONDO','GO','REACTOME','UBERON','CHEBI')),
    relation_type TEXT NOT NULL CHECK (relation_type IN ('is_a','part_of','regulates','occurs_in')),
    PRIMARY KEY (child_uid, parent_uid, ontology, relation_type),
    CONSTRAINT ck_no_self_relation CHECK (child_uid <> parent_uid)
);

-- Materialised transitive closure; rebuilt per release
CREATE TABLE ontology_closure (
    ancestor_uid   ulid NOT NULL,
    descendant_uid ulid NOT NULL,
    ontology       TEXT NOT NULL,
    depth          SMALLINT NOT NULL CHECK (depth > 0),
    PRIMARY KEY (ancestor_uid, descendant_uid, ontology)
);
CREATE INDEX ix_closure_desc ON ontology_closure (descendant_uid, ontology);
```

**Why a materialised closure table rather than recursive CTEs:** the query "find all compounds associated with any descendant of *cardiovascular disease*" runs on every disease-scoped search. A recursive CTE re-walks the DAG each time; on a DAG with multiple paths to the same node it also risks combinatorial blowup without careful cycle handling. The closure table turns it into a single indexed join.

**Cost, stated:** the closure must be rebuilt whenever the ontology changes, and it grows superlinearly with depth. At ontology scale (~10⁵ terms) this is a few million rows — entirely manageable, and rebuilt as part of the release pipeline. `ck_no_self_relation` plus the `depth > 0` constraint guard against the cycles that would make the build non-terminating.

---

## 6. Gap 5 — Protein Family Classification

Target-class membership drives read-across ("kinase inhibitors tend to…") and off-target risk assessment.

```sql
CREATE TABLE protein_classification (
    protein_uid   ulid NOT NULL REFERENCES protein(protein_uid) ON DELETE RESTRICT,
    class_level_1 TEXT,   -- e.g. Enzyme
    class_level_2 TEXT,   -- e.g. Kinase
    class_level_3 TEXT,   -- e.g. Protein Kinase
    class_level_4 TEXT,   -- e.g. TK
    class_level_5 TEXT,   -- e.g. EGFR family
    classification_source TEXT NOT NULL CHECK (classification_source IN
        ('chembl_protein_class','uniprot_family','pfam','interpro')),
    source_id     TEXT NOT NULL REFERENCES data_source(source_id) ON DELETE RESTRICT,
    PRIMARY KEY (protein_uid, classification_source)
);
```

Fixed five-level columns rather than a recursive hierarchy: ChEMBL's protein classification is a fixed-depth taxonomy, and flattening it makes the common query (`WHERE class_level_2 = 'Kinase'`) a simple indexed predicate. This is a deliberate denormalisation, justified by the source being fixed-depth — if that changes, it becomes an `ontology_relation` consumer instead.

---

## 7. Gene–Disease Associations

Step 3 has `target_disease_association`. Genetic evidence operates at the gene level and is the strongest single predictor of clinical success, so it deserves its own relation.

```sql
CREATE TABLE gene_disease_association (
    gene_uid      ulid NOT NULL REFERENCES gene(gene_uid) ON DELETE RESTRICT,
    disease_uid   ulid NOT NULL REFERENCES disease(disease_uid) ON DELETE RESTRICT,
    association_score NUMERIC(6,5) CHECK (association_score BETWEEN 0 AND 1),
    evidence_type TEXT CHECK (evidence_type IN
        ('genetic_association','somatic_mutation','known_drug','literature',
         'animal_model','rna_expression','pathway')),
    evidence_count INTEGER CHECK (evidence_count >= 0),
    source_id     TEXT NOT NULL REFERENCES data_source(source_id) ON DELETE RESTRICT,
    license_tier  license_tier_t NOT NULL,
    PRIMARY KEY (gene_uid, disease_uid, evidence_type, source_id)
);
```

Open Targets (CC0) is the natural source and already scores these systematically — a case where Step 1's recommendation to prioritise it pays off directly.

---

## 8. Why This Domain Is Deliberately Read-Mostly

Every table here is **derived from external sources** — DrugSim curates none of it. Two consequences:

1. **No DrugSim-authored biology.** If a relationship is not in an ingested source, it does not exist in the database. Inferred relationships live in the prediction layer with a model attribution, never here. This keeps the knowledge layer auditable against upstream sources.
2. **Refresh is wholesale, not incremental.** When Open Targets publishes a quarterly release, the associated rows are replaced under a new `drugsim_release`, not patched. Patching would make the database diverge from any upstream state and destroy the ability to say "this is Open Targets 26.09 as we received it."

This is why the biology domain is a good candidate for the eventual Neo4j projection (ADR-004): it is read-mostly, traversal-heavy, and rebuilt in bulk — the workload a graph store is actually good at.

---

*End Step 6.*
