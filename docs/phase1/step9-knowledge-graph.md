# DrugSim — Phase 1, Step 9
## Biomedical Knowledge Graph

**Document status:** Draft for approval
**Date:** 2026-08-05
**Depends on:** Steps 1–8 (approved)
**Related:** ADR-004 (defer Neo4j to Phase 3; materialise from Postgres)

---

## 1. Position

The brief asks why a graph database could complement the relational one. The honest answer has two halves, and the second is the one usually omitted:

**Where a graph genuinely wins:** variable-depth traversal, path finding, and structural graph algorithms. These are awkward-to-impossible in SQL and are exactly what target prediction, mechanism hypothesis and drug repurposing need.

**Where it does not:** everything else DrugSim does. Aggregation, filtering, constraint enforcement, transactional integrity, and licence auditing are all better in Postgres. A graph database is a **specialised read projection**, not a replacement system of record.

This is why ADR-004 defers Neo4j to Phase 3 and derives it from Postgres rather than running it as a second writable store. Two writable stores means two sources of truth and a synchronisation problem with no upside.

---

## 2. Graph Schema

### 2.1 Node types

| Label | Source table | Key property |
|---|---|---|
| `Compound` | `compound` | `compound_uid`, `inchikey_full`, `canonical_smiles` |
| `Protein` | `protein` | `uniprot_accession`, `is_reviewed` |
| `Gene` | `gene` | `ensembl_id`, `hgnc_symbol` |
| `Target` | `target` | `target_uid`, `target_type` |
| `Disease` | `disease` | `efo_id` / `mondo_id` |
| `Pathway` | `pathway` | `reactome_id` |
| `BiologicalProcess` | `pathway` (GO subset) | `go_id` |
| `AdverseEvent` | `compound_adverse_event` | `meddra_pt_code` + `meddra_version` |
| `DrugClass` | `drug_class` | `atc_code` |
| `Scaffold` | `compound.bemis_murcko_scaffold` | `scaffold_smiles` |
| `AOPEvent` | `aop_event` | `event_type` (MIE / KE / AO) |
| `StructuralAlert` | `structural_alert` | `alert_name`, `is_genotoxic_alert` |

`Enzyme` and `Transporter` are **not** node labels — they are properties on `Protein`, consistent with Step 3 §5 treating them as roles rather than types. A protein can be both an enzyme and a drug target; separate labels would force duplication.

### 2.2 Edge types

| Relationship | From → To | Key properties |
|---|---|---|
| `BINDS_TO` | Compound → Target | `pchembl_value`, `activity_type`, `confidence` |
| `INHIBITS` / `ACTIVATES` / `MODULATES` | Compound → Protein | `action_type`, `is_direct` |
| `METABOLISED_BY` | Compound → Protein | `interaction_role='substrate'` |
| `INHIBITS_ENZYME` | Compound → Protein | DDI-relevant |
| `TRANSPORTED_BY` | Compound → Protein | `transport_direction` |
| `HAS_COMPONENT` | Target → Protein | `stoichiometry` |
| `ENCODED_BY` | Protein → Gene | — |
| `PARTICIPATES_IN` | Protein → Pathway | — |
| `ASSOCIATED_WITH` | Gene/Target → Disease | `association_score`, `evidence_type` |
| `CAUSES_AE` | Compound → AdverseEvent | `prr`, `ror`, `is_signal` |
| `HAS_SCAFFOLD` | Compound → Scaffold | — |
| `SIMILAR_TO` | Compound → Compound | `tanimoto` (materialised above threshold) |
| `ORTHOLOG_OF` | Protein → Protein | `sequence_identity_pct`, `relationship` |
| `TRIGGERS_MIE` | Compound → AOPEvent | — |
| `LEADS_TO` | AOPEvent → AOPEvent | `evidence_level`, `is_adjacent` |
| `HAS_ALERT` | Compound → StructuralAlert | `match_count` |
| `IS_A` / `PART_OF` | ontology terms | from `ontology_relation` |

**Every edge carries `source_id` and `license_tier`**, propagated from the relational layer. The graph is a projection, so it inherits the licensing model rather than escaping it — a graph query that traverses red-tier edges must be identifiable as such.

The chain in the brief — Compound → Protein → Gene → Disease → Pathway → Side Effect → Enzyme → Transporter → Drug Class → Biological Process — is fully expressible; it is a path through the schema above rather than a fixed structure.

---

## 3. What the Graph Enables That SQL Cannot

Four capability classes, each mapping to a planned DrugSim module. These are the justification; absent them, the graph is not worth its operational cost.

### 3.1 Variable-depth mechanism paths
*"By what mechanistic route might this compound cause hepatotoxicity?"*

```cypher
MATCH path = (c:Compound {inchikey_full: $ik})-[:INHIBITS|BINDS_TO*1..2]->(p:Protein)
             -[:PARTICIPATES_IN]->(:Pathway)-[:ASSOCIATED_WITH*1..3]->(d:Disease)
WHERE d.name CONTAINS 'hepat'
RETURN path, length(path) AS hops ORDER BY hops LIMIT 20
```

In SQL this is a recursive CTE with hand-managed cycle detection and a different query shape per depth. Beyond three hops it becomes unmaintainable — the point where ADR-004 said to revisit.

### 3.2 Guilt-by-association target prediction
*"Which targets is this novel compound likely to hit?"* — propagate from structurally similar compounds through their known targets. This is the **Protein Target Prediction** module from the brief, and it is a graph problem: a two-hop traversal over `SIMILAR_TO` then `BINDS_TO`, weighted by Tanimoto and potency.

### 3.3 Repurposing by path discovery
*"Which approved drugs connect to disease D by a plausible mechanistic path?"* — path-finding between a drug set and a disease node, ranked by path length and evidence strength. Expressible in SQL only as a fixed-shape join with a pre-chosen number of hops.

### 3.4 Graph embeddings for link prediction
Node2vec, TransE, or a GNN over the KG produces embeddings supporting link prediction — the modern approach to drug–target interaction and repurposing. This requires the graph as a **first-class object**, not as query results.

**Important caveat, given Step 1:** KG embeddings are highly susceptible to the same leakage problem as ADMET models, and worse — a compound's edges leak information about its neighbours. Any KG-embedding evaluation must hold out **edges and their endpoints** consistently with the global `split_group` (ADR-009), not just random edges. Random edge holdout on a biomedical KG produces impressively wrong performance numbers. This is a known, frequently-repeated error in the literature.

---

## 4. Materialisation Strategy

**Direction: Postgres → Neo4j, one-way, rebuilt per release.** Never the reverse.

| Aspect | Decision |
|---|---|
| Trigger | On `drugsim_release` publication (post-G6) |
| Method | Full rebuild into a new database, atomic alias swap |
| Not incremental | A full rebuild at this scale takes minutes; incremental sync is a class of bug for no benefit |
| Provenance | Every node and edge carries `drugsim_release`, `source_id`, `license_tier` |
| Writability | **Read-only in production.** Enforced by user permissions, not convention |

**`SIMILAR_TO` is the one edge type that is computed, not projected.** All-pairs Tanimoto over 3M compounds is 4.5×10¹² comparisons — infeasible and useless. Materialise only edges above a threshold (≥0.7) using the RDKit cartridge's GiST index to generate candidates in Postgres first. Even then, expect a large edge count; consider restricting to compounds carrying measurements.

**Scale estimate.** Nodes ~3.5M (dominated by compounds); edges ~50–150M (dominated by `BINDS_TO` from 24.5M ChEMBL activities [V] and `SIMILAR_TO`). Comfortably within single-instance Neo4j, which reinforces the ADR-002 point that DrugSim does not have a distributed-systems problem.

---

## 5. What Stays in Postgres

Explicitly **not** moved to the graph:

- Measurements and their values — aggregation and filtering, not traversal
- Predictions and model registry — transactional, audited
- Audit log, signatures, validation records — Part 11 integrity requires ACID
- Licence tiering enforcement — constraint-based
- Descriptors and feature data — columnar, bulk-read

**The graph holds relationships; Postgres holds facts and governance.** An edge in the graph says *that* a compound binds a target; the measured pChEMBL value, its provenance, its licence, and its quality score live in Postgres. The graph carries enough properties to rank and filter traversals, and refers back for detail.

---

## 6. Alternatives Considered

| Option | Assessment |
|---|---|
| **Neo4j** | **Recommended for Phase 3.** Mature, Cypher is readable, strong GDS library for embeddings/centrality, good operational tooling. Community edition lacks some clustering features — irrelevant at this scale |
| **RDF triplestore + SPARQL** | Superior semantics and native ontology alignment; biomedical data is well served by RDF (UniProt, ChEMBL and Reactome all publish it). Rejected for Phase 3 on operational and skills cost — SPARQL is materially harder to hire for and to debug. **Revisit if formal ontology reasoning becomes a requirement** |
| **Postgres recursive CTEs only** | Adequate to ~3 hops. This is the Phase 1–2 position and is genuinely sufficient until the target-prediction module exists |
| **Apache AGE (graph in Postgres)** | Attractive — one system, Cypher support. Rejected: less mature, no GDS-equivalent algorithm library, and the embedding workloads are the main reason for adopting a graph at all |
| **In-memory graph (NetworkX/igraph)** | Genuinely viable for analysis at this scale and much cheaper. **Recommended as the Phase 2 stopgap** — build the graph in memory for a specific analysis rather than standing up a service |

The in-memory option deserves emphasis: for a 3.5M-node graph, `igraph` in a notebook answers most exploratory questions without any infrastructure. Standing up Neo4j should follow a demonstrated need from a product module, not precede it.

---

## 7. Risks

| Risk | Mitigation |
|---|---|
| **Two sources of truth** | One-way projection, read-only, rebuilt per release |
| **Spurious paths** | Every edge carries evidence strength; path queries filter on it. A path through a weak text-mined edge is not a mechanism hypothesis |
| **Licence leakage via traversal** | Edges carry `license_tier`; graph-derived outputs record consumed tiers, exactly as models do |
| **Embedding leakage** | Split-aware edge holdout using global `split_group` (§3.4) |
| **Scope creep** | The graph is justified by four named capabilities (§3). If none is being built, it should not be stood up |

---

*End Step 9.*
