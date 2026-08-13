# TDS §1 & §12 — Overview and Development Principles

---

## 1.1 What DrugSim Is

DrugSim is an **AI-assisted preclinical prioritisation platform**. A researcher uploads a molecular structure (SMILES, MOL, SDF) and receives predicted ADMET properties, drug-likeness assessment, target hypotheses and toxicity flags — each accompanied by a quantified confidence and an explicit statement of whether the molecule falls within the model's applicability domain.

Its purpose is to help researchers **decide which molecules to make and test first**, reducing wasted synthesis and animal testing by improving the ordering of an experimental queue.

### 1.1.1 What DrugSim is not

This distinction is load-bearing and was established by evidence, not caution. Phase 1 verified the corpus behind the headline endpoints:

| Endpoint | Public training compounds |
|---|---|
| Human oral bioavailability | **640** |
| Human half-life | **667** |
| DILI (hepatotoxicity) | **475** |
| Carcinogenicity | **278** |
| Clinical toxicity (ClinTox) | 1,484, imbalanced, noisy labels |

Models trained on a few hundred compounds have narrow applicability domains and degrade sharply outside them — which is precisely where newly designed molecules live. DrugSim is therefore **not** a replacement for laboratory or animal testing, and must never be positioned as one. Any claim the data cannot support invites scientific criticism it cannot withstand and, given the safety-adjacent subject matter, potential regulatory attention.

The honest and commercially defensible claim is **triage**: better ordering of experiments, with calibrated uncertainty, not substitution for them.

---

## 1.2 Scientific Objectives

1. **Predict ADMET properties** with calibrated, validated uncertainty across the endpoints where public data supports a credible model
2. **State applicability domain** for every prediction, so users know when the model is extrapolating
3. **Preserve provenance end to end** — every prediction traceable to the data, code and toolchain that produced it
4. **Support mechanistic reasoning**, not just point predictions — structural alerts, AOP linkage, nearest-neighbour evidence
5. **Meet regulatory expectations** where applicable: OECD (Q)SAR validation principles, ICH M7 dual-methodology mutagenicity assessment, 21 CFR Part 11 controls

---

## 1.3 Target Users

| User | Needs | Implication for design |
|---|---|---|
| **Medicinal chemist** (primary) | Rapid triage of designed compounds; understanding *why* a compound is flagged | Fast turnaround, interpretable output, structural alert visualisation |
| **DMPK / PK scientist** | ADMET profile with credible uncertainty; PK parameter coherence | Intervals, AD, PK consistency checking (Phase 1 Step 5 §5) |
| **Toxicologist** | Mechanistic hypotheses, not just binary flags | AOP linkage, alert provenance, literature references incl. contradicting evidence |
| **Computational chemist** | Programmatic access, reproducibility, batch throughput | API, stable contracts, pinned toolchain, exportable provenance |
| **Regulatory / QA** | Validation evidence, audit trail, model documentation | QMRF, OECD records, Part 11 audit log, e-signatures |

The medicinal chemist is the primary user, but **the toxicologist and regulatory reviewer are the hardest to satisfy**, and designing for them raises quality for everyone. A system that can defend a prediction to a toxicologist is a system a chemist can trust.

---

## 1.4 Core Philosophy

> **A prediction without its uncertainty is not a scientific result. It is a number.**

Four commitments follow, and they are enforced structurally rather than by policy:

1. **Uncertainty is not optional.** `ad_verdict` is `NOT NULL`; a prediction cannot exist in the database without a domain assessment.
2. **Measurements and predictions never mix.** A CHECK constraint (`evidence_type <> 'predicted'`) makes it impossible to store a prediction in a measurement table.
3. **Raw data is immutable.** Landed bytes are never edited; corrections are forward transformations replayable from source.
4. **"We don't know" is a valid, first-class output.** Out-of-domain, indeterminate, and discordant are supported states, not failure modes to be smoothed over.

---

## 1.5 Scope

### In scope
- Ingestion and curation of public biomedical data (nine Tier 1 sources, Phase 1 Step 1)
- The Core DB: compounds, biology, evidence, models, predictions, governance
- ADMET, drug-likeness, toxicity and target prediction with uncertainty
- Molecular similarity and scaffold analysis
- REST API and web interface
- Report generation and an AI scientific assistant grounded in regulatory text
- Regulatory validation artefacts

### Non-goals
Explicit, because each has been proposed for platforms of this kind and each would change the architecture:

| Non-goal | Why |
|---|---|
| **Replacing laboratory or animal testing** | Not supported by the data (§1.1.1) |
| **De novo molecular generation** | Different problem, different validation burden. Optimisation suggestions are Phase 4+ and remain human-directed |
| **Physics-based simulation** (docking, MD, free-energy) | Different compute profile and expertise. "Virtual Drug Simulation" in the brief means PBPK-style PK simulation, Phase 5+ |
| **Clinical decision support** | DrugSim informs preclinical research. It is not a medical device and must not be used for patient care |
| **A chemical registry / ELN** | Not a system of record for a customer's compound collection |
| **Real-time / sub-second inference** | Batch and near-real-time are sufficient; the scientific work is not latency-bound |
| **Multi-tenant data pooling** | Customer structures are never combined across tenants or used for training (§7) |

The clinical decision support exclusion should appear in the product's terms of use, not only here.

---

## 12. Development Standards

These are the engineering principles. They are the review criteria for any change touching data, models or predictions, and each maps to an enforcement mechanism — a principle without enforcement is an aspiration.

| # | Principle | Enforcement |
|---|---|---|
| **P1** | **Scientific reproducibility over speed.** A result that cannot be reproduced has no value, regardless of how quickly it was produced | Seven-axis versioning (Phase 1 Step 2 §7); golden-set regression in CI |
| **P2** | **Every prediction is traceable.** Model, feature set, training snapshot, toolchain — recoverable from the prediction record alone | FK constraints on `prediction`; `feature_set_id` trigger (PR-01) |
| **P3** | **Never overwrite raw experimental data.** Z1 landing is write-once; corrections are forward transformations | Object-lock on Z1; no `UPDATE`/`DELETE` grants |
| **P4** | **Every dataset retains provenance.** Per-record, not per-dataset — BindingDB is internally split-licensed | `source_license` `NOT NULL` on every fact table; LC-01 |
| **P5** | **Every model is reproducible.** Same data + same code + same toolchain = same weights | Content-addressed `feature_set_id`; pinned `toolchain_id`; seeded training |
| **P6** | **Every prediction carries confidence and applicability.** No exceptions, no suppression | `ad_verdict NOT NULL`; API conformance tests (§5) |
| **P7** | **Every release passes scientific validation.** Not just tests — golden set, benchmark regression, drift checks | G6/G7 gates; release blocked on failure |
| **P8** | **Nothing is deleted or silently altered.** Soft delete with reason; append-only audit | No `ON DELETE CASCADE`; `change_reason NOT NULL` |
| **P9** | **Every architectural decision is documented.** An undocumented decision will be reversed by someone who assumes it was arbitrary | ADR required for any §MAJOR change |
| **P10** | **Prefer boring, inspectable technology.** Every added system is reproducibility surface area | New infrastructure requires an ADR with a named consumer |
| **P11** | **Customer structures are confidential IP.** Never logged, never used for training, never crossed between tenants | Tenant isolation; structure redaction in logs (§7) |
| **P12** | **Honest failure over confident error.** Refusing to answer is always available and often correct | OOD, indeterminate, discordant are first-class states |

### 12.1 Applying the principles in review

A pull request touching data or predictions should be able to answer:

- Can a prediction produced by this code be traced to its inputs? (P2)
- Does this change alter existing stored values? If so, is it a MAJOR release? (P1, P7)
- Is provenance preserved through this transformation? (P4)
- Could this cause a prediction to be rendered without its uncertainty? (P6)
- Does this log, persist, or transmit a customer structure anywhere new? (P11)

**If a reviewer cannot answer these, the PR is not ready** — not because the code is wrong, but because the answer is not evident, and evidence is the product.

---

*End §1 & §12.*
