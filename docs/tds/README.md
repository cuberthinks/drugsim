# DrugSim — Technical Design Specification (TDS)

**Version:** 1.0.0-draft
**Date:** 2026-08-05
**Status:** Draft for approval
**Supersedes:** none
**Authority:** This specification is normative. Where implementation diverges from the TDS, either the implementation is corrected or the TDS is amended through change control (§0.3). Undocumented divergence is a defect.

---

## 0.1 Purpose

This document is the engineering blueprint for DrugSim. It is written to be used by engineers who did not participate in Phase 1 and who may join the project years from now. Every significant decision states its reasoning, because a decision whose rationale is lost will be reversed by someone who assumes it was arbitrary.

The TDS covers **how DrugSim is built**. Phase 1 (`docs/phase1/`) covers **what DrugSim is built on** — the dataset survey, data architecture, database schema, and scientific design. The TDS does not restate Phase 1; it references it and remains authoritative on engineering matters.

---

## 0.2 Contents

| § | Document | Covers |
|---|---|---|
| 1, 12 | [01-overview-and-principles.md](01-overview-and-principles.md) | Executive summary, scope, non-goals, development standards |
| 2 | [02-system-architecture.md](02-system-architecture.md) | Component architecture, data flow, boundaries |
| 3 | [03-technology-stack.md](03-technology-stack.md) | Every technology with rationale, alternatives, trade-offs |
| 4 | [04-data-contracts.md](04-data-contracts.md) | Entity contracts: Compound, Prediction, Model, Dataset, Target, Protein, User, Experiment, Simulation |
| 5 | [05-api-specification.md](05-api-specification.md) | Endpoint definitions, schemas, errors, auth |
| 6 | [06-ml-architecture.md](06-ml-architecture.md) | Training, validation, inference, registry, uncertainty, rollback |
| 7 | [07-security-architecture.md](07-security-architecture.md) | AuthN/Z, encryption, secrets, customer IP protection, supply chain |
| 8, 9 | [08-engineering-standards.md](08-engineering-standards.md) | Repository standards, code style, testing, QA, acceptance criteria |
| 10 | [09-deployment-strategy.md](09-deployment-strategy.md) | Environments, IaC, backup, DR, rollback, observability |
| 11 | [10-risk-register.md](10-risk-register.md) | Technical and scientific risks with owners |

**Phase 1 references** (`docs/phase1/`): dataset survey · data architecture · data dictionary · relational schema · compound/ADMET/biology/toxicology schemas · cleaning pipeline · knowledge graph · stack selection · repository design · roadmap. **ADRs** (`docs/adr/`): ADR-001 … ADR-012.

---

## 0.3 Change Control

The TDS is under change control from approval onward. This is not ceremony — under the confirmed regulatory path (Phase 1 Step 2 addendum), design documentation is part of the validation evidence.

| Change type | Process | Version |
|---|---|---|
| Correction (typo, clarification) | PR, one reviewer | PATCH |
| Addition (new endpoint, new entity, new component) | PR, two reviewers incl. tech lead | MINOR |
| Alteration of an existing decision | **New ADR required**, PR, tech lead + domain owner | MAJOR |
| Anything touching validated models or Part 11 controls | Above, plus quality/regulatory sign-off | MAJOR |

**A decision reversal requires a new ADR that supersedes the old one.** The original ADR is never edited or deleted — it is marked `Superseded by ADR-NNN`. The history of why a decision was made and later reversed is more valuable than a clean document.

---

## 0.4 How to Read This

**New engineer, week one:** §1 (what and why) → §12 (principles) → §2 (architecture) → the Phase 1 dataset survey. Do not start with the schema; it will not make sense without the data survey's findings on licensing and dataset sizes.

**Implementing a feature:** §4 (contracts) → §5 (API) → relevant Phase 1 schema step → §8 (standards).

**Reviewing a PR:** §8 (standards, testing requirements) → §12 (principles). The principles are the review criteria for anything touching data or predictions.

**Debugging a prediction:** §6 (ML architecture, provenance chain) → Phase 1 Step 2 §7 (reproducibility contract).

---

## 0.5 Terminology

| Term | Meaning |
|---|---|
| **Core DB** | The PostgreSQL system of record, versioned as `core-db-vN.N.N` |
| **Zone (Z0–Z5)** | Data lake layer (Phase 1 Step 2 §3) |
| **Gate (G1–G7)** | Pipeline validation checkpoint (Phase 1 Step 2 §4, addendum §3.3) |
| **Licence tier** | green / amber / red / black (Phase 1 Step 1 §5.1) |
| **AD** | Applicability domain |
| **OOD** | Out of domain |
| **`feature_set_id`** | Content hash pinning descriptor spec + RDKit version + pipeline version |
| **`split_group`** | Global, once-assigned scaffold-level split (ADR-009) |
| **Envelope** | A prediction plus its mandatory uncertainty and provenance (§4, §5) |
| **Customer structure** | A molecular structure uploaded by a user; treated as confidential IP (§7) |

---

*End of index.*
