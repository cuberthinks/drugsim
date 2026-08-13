# DrugSim — Phase 1, Step 10
## Technology Stack

**Document status:** Draft for approval
**Date:** 2026-08-05
**Depends on:** Steps 1–9 (approved)
**Consolidates:** ADR-001 … ADR-012 (Step 2 §10)

---

## 1. Selection Criteria

Ranked by weight, derived from what Step 1 established about the problem:

1. **Reproducibility** — every added system is reproducibility surface area (P7)
2. **Correctness guarantees** — constraints, ACID, typed schemas; the dominant risk is silent scientific error
3. **Licence compatibility** — a commercially restrictive dependency is as blocking as a restrictive dataset
4. **Operational simplicity** — small team, small data; complexity is a real cost with no offsetting benefit
5. **Regulatory fit** — Part 11 needs auditability and access control
6. **Performance** — genuinely last. The largest artefact is ~5.4 GB and the ADMET sets are ≤13k rows

Criterion 6 being last is the whole architecture in one line. Systems chosen for scale we do not have would cost us on 1–4, which is where the risk actually lives.

---

## 2. Head-to-Head Comparison

Scored 1–5 for DrugSim's specific workload. These are not general-purpose rankings.

| | PostgreSQL | Neo4j | MongoDB | DuckDB | Redis | MinIO | Elasticsearch | Vector DB |
|---|---|---|---|---|---|---|---|---|
| Referential integrity | **5** | 2 | 1 | 2 | 1 | 1 | 1 | 1 |
| Constraint enforcement | **5** | 2 | 1 | 3 | 1 | 1 | 1 | 1 |
| ACID | **5** | 4 | 3 | 3 | 2 | 2 | 1 | 2 |
| Chemical search (native) | **5**¹ | 1 | 1 | 1 | 1 | 1 | 2 | 3² |
| Analytical scan speed | 3 | 2 | 2 | **5** | 1 | 1 | 3 | 2 |
| Graph traversal | 2³ | **5** | 1 | 1 | 1 | 1 | 1 | 1 |
| Bulk immutable storage | 2 | 1 | 2 | 2 | 1 | **5** | 1 | 1 |
| Full-text search | 3⁴ | 1 | 2 | 1 | 1 | 1 | **5** | 3 |
| Semantic/vector search | 3⁵ | 2 | 2 | 1 | 2 | 1 | 3 | **5** |
| Audit / Part 11 fit | **5** | 3 | 2 | 2 | 1 | 3 | 2 | 1 |
| Operational simplicity | 4 | 3 | 4 | **5** | 4 | 4 | 2 | 3 |
| Licence (OSS, commercial-safe) | **5** | 3⁶ | 3⁷ | **5** | 4⁸ | 4 | 3⁹ | varies |
| **Role in DrugSim** | **System of record** | **Phase 3 projection** | **Rejected** | **Analytics engine** | **Phase 5, if needed** | **Data lake** | **Phase 4** | **Phase 4** |

¹ With the RDKit cartridge — substructure and Tanimoto search with GiST indexes.
² Chemical fingerprints as vectors work, but Tanimoto on binary fingerprints is better served by the cartridge.
³ Recursive CTEs adequate to ~3 hops (ADR-004).
⁴ `tsvector` is adequate for moderate corpora.
⁵ `pgvector` extension.
⁶ GPLv3 community / commercial enterprise — acceptable for a read-only internal projection; verify before any embedded distribution.
⁷ SSPL — problematic for some commercial models.
⁸ Redis licensing changed in recent years; **Valkey** is the safe fork.
⁹ Elastic dual-license SSPL/ELv2; **OpenSearch** is the Apache-2.0 alternative.

---

## 3. Decisions

### 3.1 Adopted — Phase 1

**PostgreSQL 16 + RDKit cartridge — system of record.** (ADR-003)
Wins on every criterion that matters most. The cartridge is decisive: without it, substructure and similarity search become application-layer scans over ~3M compounds. The Part 11 fit is also unmatched — CHECK constraints, ACID, row-level security and mature audit patterns.

*Operational cost, stated:* the cartridge is not available on managed Postgres (RDS, Cloud SQL, Aurora). This means self-managed Postgres or a container. That is a real constraint on the deployment options and should be weighed at infrastructure planning; it is accepted because the capability is central.

**DuckDB — analytical engine.** (ADR-002)
Reads Parquet natively, single-node, zero-ops, embedded. For the entire ETL and analysis workload this is faster and dramatically simpler than any cluster. MIT-licensed.

**MinIO / S3-compatible object storage — data lake.** (ADR-011)
The S3 API is the interface; MinIO for local and self-hosted, cloud object storage in production. Identical code paths, no lock-in. Object-lock supports the Part 11 retention requirement on Z1.

**Parquet — lake file format.** (ADR-010) Columnar, compressed, universally readable, DuckDB-native. Plain Parquet with manifest versioning now; Iceberg when concurrent writers or >50 curated tables appear.

**Dagster — orchestration.** (ADR-006) Asset-oriented, so lineage is structural rather than documented. Apache-2.0.

**Python 3.12 + RDKit + Polars.** RDKit is the only serious open cheminformatics toolkit (BSD-3); Polars for typed, fast dataframe transforms.

### 3.2 Deferred — with triggers

| Technology | Phase | Trigger |
|---|---|---|
| **Neo4j** | 3 | Target-prediction or repurposing module begins; routine >3-hop traversal. Consider in-memory `igraph` first (Step 9 §6) |
| **Vector DB / pgvector** | 4 | AI Scientific Assistant begins. **Start with `pgvector`** — one fewer system; move to a dedicated store only if it proves limiting |
| **OpenSearch** | 4 | Full-text search over the DailyMed corpus. Postgres `tsvector` may well suffice |
| **Valkey (Redis fork)** | 5 | A *measured* latency problem. Not before |

**On the vector database question specifically:** the brief lists it, and it is genuinely needed for the AI Assistant's RAG over DailyMed and literature. But `pgvector` in the existing Postgres handles corpora of this size well, and adding a dedicated vector store in Phase 1 would mean operating a system with no consumer for two or more phases.

### 3.3 Rejected

**MongoDB — rejected.**
Not on performance, but on integrity. DrugSim's core requirement is per-record licence provenance with referential integrity and CHECK constraints; a document store cannot enforce these, so the guarantees would move into application code — precisely where they are least reliable and least auditable. The SSPL licence is a secondary concern. Document storage needs are met by `JSONB` in Postgres, used narrowly.

**Spark / distributed compute — rejected.** (ADR-002) No workload justifies it. Non-deterministic shuffle ordering also complicates the reproducibility guarantees.

**Feast / managed feature store — rejected.** (ADR-005) Solves online/offline skew at scale with streaming freshness. DrugSim has deterministic features and ~10⁶ entities.

**DrugBank, PDBbind, commercial pKa predictors — deferred/excluded** on licensing (Step 1 §5.4, Step 4 §4).

---

## 4. Final Architecture

```
┌──────────────────────────────────────────────────────────────┐
│  ORCHESTRATION      Dagster (software-defined assets)        │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  DATA LAKE          MinIO / S3  ·  Parquet                   │
│                     Z1 landing (immutable, object-lock)      │
│                     Z2 conformed  ·  Z3 curated              │
│                     partitioned by license_tier              │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  COMPUTE            DuckDB (SQL over Parquet)                │
│                     Polars (transforms)                      │
│                     RDKit (chemistry, version-pinned)        │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  SYSTEM OF RECORD   PostgreSQL 16 + RDKit cartridge          │
│                     30+ tables · Part 11 audit · RLS         │
│                     measurement partitioned by license_tier  │
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  FEATURE STORE      Content-addressed Parquet on S3          │
│                     feature_set_id = hash(spec+rdkit+pipeline)│
└──────────────────────────────────────────────────────────────┘
┌──────────────────────────────────────────────────────────────┐
│  DEFERRED           Neo4j (P3) · pgvector (P4)               │
│                     OpenSearch (P4) · Valkey (P5)            │
└──────────────────────────────────────────────────────────────┘
```

**Phase 1 runs on four systems: Postgres, MinIO, DuckDB, Dagster.** Everything else is deferred behind a named trigger. For a small team building a reproducibility-critical scientific platform, that restraint is the design, not a shortcut.

---

## 5. Licence Audit of the Stack

Applying to dependencies the same discipline Step 1 applied to data.

| Component | Licence | Commercial | Note |
|---|---|---|---|
| PostgreSQL | PostgreSQL Licence | ✅ | Permissive |
| RDKit + cartridge | BSD-3-Clause | ✅ | Permissive |
| DuckDB | MIT | ✅ | |
| Polars | MIT | ✅ | |
| Parquet / Arrow | Apache-2.0 | ✅ | |
| MinIO | AGPLv3 | ⚠️ | Fine as a deployed service; **AGPL matters if embedded/distributed**. Cloud object storage avoids the question entirely |
| Dagster | Apache-2.0 | ✅ | |
| Python | PSF | ✅ | |
| Neo4j Community | GPLv3 | ⚠️ | Acceptable for internal read-only projection; verify before distribution |
| Valkey | BSD-3 | ✅ | Redis fork — use instead of Redis |
| OpenSearch | Apache-2.0 | ✅ | Use instead of Elasticsearch |

**Two flags worth acting on now.** MinIO's AGPL is unproblematic for internal deployment but would matter for a distributed/on-prem product edition — using cloud object storage in production sidesteps it. And the Redis→Valkey / Elasticsearch→OpenSearch substitutions should be made by default rather than discovered later; both were relicensed in ways that complicate commercial use.

---

## 6. Estimated Infrastructure Footprint

| Component | Phase 1 | Notes |
|---|---|---|
| Postgres | 8–16 vCPU, 64 GB RAM, 1–2 TB SSD | Sized by ChEMBL activities + GiST fingerprint indexes |
| Object storage | 2–5 TB | Z1 landing dominates; grows with every snapshot retained |
| Compute (ETL) | 8–16 vCPU, 64–128 GB RAM | Single node; batch, not continuous |
| Feature store | 100–500 GB | Multiple feature-set versions coexist by design |

Modest — one substantial server plus object storage. Worth stating plainly, because "AI drug discovery platform" invites assumptions about GPU clusters that this workload does not support. GPUs become relevant in Phase 3+ for model training, and even then modestly, given dataset sizes verified in Step 1.

---

*End Step 10.*
