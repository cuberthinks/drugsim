# DrugSim — Phase 1, Step 12
## Scientific Development Roadmap (Phases 1–10)

**Document status:** Draft for approval
**Date:** 2026-08-05
**Depends on:** Steps 1–11 (approved)

---

## 0. Structure and Assumptions

This roadmap is organised as **stage-gated R&D**, not a feature backlog. Each phase ends in a **go/no-go gate with a falsifiable criterion**. A phase that fails its gate does not proceed — it either iterates or the programme is rescoped. That is the discipline the brief asked for, and it only means anything if a gate can actually fail.

**Assumptions, stated so the estimates can be judged:**

| Assumption | Value |
|---|---|
| Team | 3–5 FTE: 1–2 data/ML engineers, 1 cheminformatician, 1 backend engineer, fractional DMPK/tox scientist |
| Regulatory scope | Confirmed in scope (Step 2 addendum) |
| Commercial model | Undecided → strict commercial-safe posture throughout |
| Estimates | Calendar time at the above staffing, including review and rework |

**Total to Phase 10: approximately 30–36 months.** Stated plainly because the alternative — an optimistic timeline that slips repeatedly — is worse than an honest one. A non-regulatory version of this programme would reach a comparable product surface in roughly 18–22 months; the regulatory path is the main increment, mostly in Phase 9 and in per-phase documentation overhead.

**Critical-path dependency, flagged early:** the ShareAlike legal opinion (Step 1 §5.2) must resolve before Phase 3 completes. It is the only external dependency that can invalidate work already done.

---

## Phase 1 — Data Foundation *(current)*

| | |
|---|---|
| **Goal** | Define the scientific data foundation before any code, model or interface is built |
| **Tasks** | Dataset survey with primary-source verification · data architecture · master data dictionary · relational schema · ADMET/biology/toxicology schemas · cleaning pipeline design · KG design · stack selection · repo design · this roadmap |
| **Deliverables** | Steps 1–12 documents · `registry.yaml` · 12 ADRs |
| **Time** | 6–8 weeks *(substantially complete)* |
| **Risks** | Over-design without implementation feedback; unverified assumptions ossifying into schema |
| **Dependencies** | None |
| **Outputs** | Approved design corpus; four open decisions (§5) |
| **🚦 Gate** | All 12 steps approved; open decisions either resolved or explicitly deferred with owners |

---

## Phase 2 — Core Database Build

| | |
|---|---|
| **Goal** | A populated, validated, reproducible DrugSim Core DB v1.0.0 |
| **Tasks** | Stand up Postgres+RDKit, MinIO, Dagster · implement `drugsim_chem` · build source adapters (waves W1–W7, Step 1 §6) · implement gates G1–G7 · **empirically determine every TDC unit (Step 8 §5)** · build golden set · global split assignment · attribution manifest · licence audit in CI |
| **Deliverables** | Core DB v1.0.0 · ETL pipeline · golden-set regression suite · constraint test suite · release manifest |
| **Time** | **12–16 weeks** |
| **Risks** | ⚠️ **Unit determination fails for some endpoints** → those endpoints are unusable (mitigation: exclude rather than guess) · ChEMBL↔BindingDB dedup harder than scoped · invitrodb requires more toxicology expertise than available · Part 11 audit machinery slows every write path |
| **Dependencies** | Phase 1 approval; Postgres+RDKit container; fractional toxicologist for ToxCast |
| **Outputs** | Queryable Core DB; per-endpoint data-availability report; **honest count of usable training compounds per endpoint** |
| **🚦 Gate** | All G1–G6 pass on a full run · golden set reproduces exactly · zero `unit_verified_method='unverified'` in published endpoints · licence audit clean |

**The gate's third criterion is the important one.** It means an endpoint whose units could not be established does not ship. Given that TDC documents no units [V], this is a real possibility for several endpoints and the gate must be allowed to bite.

---

## Phase 3 — Baseline Models & Honest Benchmarking

| | |
|---|---|
| **Goal** | Establish real, defensible baseline performance for each ADMET endpoint — and learn which endpoints are not viable |
| **Tasks** | Feature pipeline (content-addressed) · baselines per endpoint (descriptor GBM, Chemprop-style GNN) · evaluate on **both** TDC canonical splits (leaderboard comparability) **and** global `split_group` (internal truth) · quantify the gap · model registry · **Green/Amber-only fallback models to quantify the ShareAlike cost** |
| **Deliverables** | Baseline model per viable endpoint · benchmark report on both split regimes · viability assessment per endpoint · fallback-model cost analysis |
| **Time** | **10–14 weeks** |
| **Risks** | ⚠️ **Global-split performance materially worse than published leaderboards** — expected, and the honest number · endpoints with <500 compounds may fail to reach usable performance · ⚠️ **ShareAlike opinion unresolved** blocks commercial deployability |
| **Dependencies** | Phase 2 gate; **legal opinion on ShareAlike** |
| **Outputs** | Baselines; a ranked list of which endpoints DrugSim can and cannot credibly predict |
| **🚦 Gate** | ≥8 endpoints reach pre-agreed performance thresholds **under global splits** · gap vs. TDC splits documented and explained · fallback-model cost quantified |

**This phase is where the product's real scope is decided.** Step 1 established that DILI has 475 compounds and half-life 667. Some endpoints will not clear the bar. Finding that out here — before a UI promises them — is the purpose.

---

## Phase 4 — Uncertainty, Calibration & Applicability Domain

| | |
|---|---|
| **Goal** | Make every prediction carry a defensible statement of how much to trust it |
| **Tasks** | Conformal prediction per endpoint · calibration (Platt/isotonic/Venn-Abers) · AD implementation (Tanimoto k-NN, descriptor-space distance, scaffold-seen) · empirical coverage validation · define `quality_score` weights from real performance data · out-of-domain behaviour testing on deliberately novel chemotypes |
| **Deliverables** | Calibrated models with valid intervals · AD service · `quality_score` v1 (evidence-based, replacing the provisional weights) · coverage validation report |
| **Time** | **8–10 weeks** |
| **Risks** | Conformal intervals may be so wide on small datasets that they undermine perceived usefulness — **this is a true finding, not a failure to hide** · calibration sets further reduce already-scarce training data |
| **Dependencies** | Phase 3 gate |
| **Outputs** | Predictions with valid coverage; honest OOD behaviour |
| **🚦 Gate** | Empirical coverage within tolerance of nominal on held-out data · OOD compounds reliably flagged · no endpoint ships without an AD definition |

---

## Phase 5 — Mechanistic & Multi-Task Modelling

| | |
|---|---|
| **Goal** | Improve on baselines where single-task learning is data-limited, using mechanism and transfer |
| **Tasks** | Multi-task models across correlated endpoints (leakage-controlled by global splits) · pretraining on unlabelled chemical space · AOP-informed toxicity reasoning (Step 7 §4) · rule-based genotoxicity arm for ICH M7 · PK consistency enforcement (Step 5 §5) · mechanism→outcome models for hepatotoxicity |
| **Deliverables** | Multi-task ADMET model · AOP reasoning layer · ICH M7 dual-methodology pipeline · PK consistency service |
| **Time** | **12–16 weeks** |
| **Risks** | Multi-task learning may not beat single-task at these dataset sizes — **plausible; must be measured, not assumed** · AOP coverage for the target organ toxicities may be too sparse to be useful · negative transfer between weakly related endpoints |
| **Dependencies** | Phase 4 gate; AOP-Wiki licence verification |
| **Outputs** | Improved models where justified; mechanistic explanations |
| **🚦 Gate** | Multi-task beats single-task on ≥50 % of endpoints, or is dropped with the negative result recorded · ICH M7 pipeline produces classifiable outputs on a validation set |

---

## Phase 6 — Target Prediction, Similarity & Knowledge Graph

| | |
|---|---|
| **Goal** | Deliver target prediction and similarity search; stand up the KG if — and only if — these justify it |
| **Tasks** | Similarity search on RDKit cartridge · scaffold and MMP analysis · **in-memory graph first** (Step 9 §6) · Neo4j projection only if traversal need is demonstrated · KG embeddings with **split-aware edge holdout** · target prediction by guilt-by-association |
| **Deliverables** | Similarity/scaffold service · target prediction model · KG projection (conditional) |
| **Time** | **10–14 weeks** |
| **Risks** | ⚠️ **KG embedding leakage** — random edge holdout produces impressively wrong numbers (Step 9 §3.4) · Neo4j stood up without a consumer · target prediction limited by ChEMBL's actives-biased coverage |
| **Dependencies** | Phase 5 gate |
| **Outputs** | Target prediction with AD; similarity search |
| **🚦 Gate** | Target prediction validated on temporally held-out ChEMBL data · KG adoption justified by a named module or not adopted |

---

## Phase 7 — Platform Services

| | |
|---|---|
| **Goal** | Expose the foundation through stable, provenance-preserving services |
| **Tasks** | Prediction API · molecule upload/validation (SMILES/MOL/SDF) · **shared `drugsim_chem` on the serving path** (no reimplementation) · feature-set consistency enforcement (PR-01) · authn/authz aligned to Part 11 §11.10(d) · rate limiting · audit capture on every prediction |
| **Deliverables** | Prediction API · ingestion service · auth · API documentation |
| **Time** | **10–12 weeks** |
| **Risks** | ⚠️ **Training/serving skew** if the shared library is bypassed under deadline pressure · stereoisomer enumeration policy (Step 4 §2.3) still unresolved would block the upload contract |
| **Dependencies** | Phase 4 gate minimum; stereoisomer decision |
| **Outputs** | Programmatic access with full provenance |
| **🚦 Gate** | `feature_set_id` mismatch impossible · every response carries AD verdict and provenance · OOD verdicts structurally unsuppressible (PR-05) |

---

## Phase 8 — Product Surface

| | |
|---|---|
| **Goal** | A researcher-facing interface that communicates uncertainty as clearly as it communicates predictions |
| **Tasks** | Upload and results UI · **uncertainty-first result presentation** · evidence display (nearest neighbours with measured values) · report generation · AI Scientific Assistant (RAG over DailyMed + literature, `pgvector`) · PK inconsistency and OOD surfacing |
| **Deliverables** | Web application · report templates · AI assistant |
| **Time** | **14–18 weeks** |
| **Risks** | ⚠️ **UI overstating confidence** — the single largest reputational risk in the programme · AI assistant hallucinating over regulatory text · report templates implying endpoints DrugSim does not credibly predict |
| **Dependencies** | Phase 7 gate |
| **Outputs** | Usable platform |
| **🚦 Gate** | Design review confirms no endpoint is presented without AD and interval · unpopulated endpoints (NOAEL, nephro-, neurotoxicity) absent from the UI entirely · assistant answers are citation-grounded |

**The gate's second criterion enforces Step 7 §7.** Endpoints with no data must not appear as empty cards inviting the inference that a prediction is merely unavailable today.

---

## Phase 9 — Regulatory Validation

| | |
|---|---|
| **Goal** | Bring the platform and its models to a defensible regulatory standard |
| **Tasks** | Complete OECD five-principle validation records per model · QMRF documentation · Part 11 system validation (IQ/OQ/PQ) · SOPs for change control, model update, expert review · e-signature workflow · ICH M7 expert review process · external validation on independent datasets · audit-trail continuity verification |
| **Deliverables** | Validation dossier · QMRFs · SOPs · Part 11 evidence · G7 passing |
| **Time** | **16–20 weeks** *(process-bound, not engineering-bound)* |
| **Risks** | ⚠️ **Process burden exceeds engineering burden** and the team is not staffed for it · external validation reveals worse performance than internal · a model update mid-validation resets the effort |
| **Dependencies** | Phases 5–8; quality/regulatory personnel (**a hiring dependency, not an engineering one**) |
| **Outputs** | Regulatory-ready platform |
| **🚦 Gate** | G7 passes · every deployed model has complete OECD records and a QMRF · audit trail continuous and complete |

**This phase is mostly not software.** It is documentation, process and evidence, and it is the phase most likely to be underestimated. Staffing it with engineers alone will fail.

---

## Phase 10 — Continuous Learning & Expansion

| | |
|---|---|
| **Goal** | Keep the platform current, monitored, and honest as data and chemistry evolve |
| **Tasks** | Scheduled source refresh with change control · **prediction-vs-outcome monitoring** where experimental results become available · drift detection · AD boundary monitoring · new endpoints as sources appear (SIDER successor, NOAEL) · retraining under change control · expansion (metabolite prediction, PBPK, transporter panel) |
| **Deliverables** | Monitoring service · refresh pipeline under change control · expansion backlog |
| **Time** | **Ongoing** |
| **Risks** | Model drift as chemical space evolves · **each retraining is a change-controlled revalidation event under the regulatory path** — retraining is not free · upstream sources degrading (DrugCentral cadence already slowed; SIDER already dead) |
| **Dependencies** | Phase 9 |
| **Outputs** | Sustained, monitored platform |
| **🚦 Gate** | Continuous — quarterly review of drift, coverage and source freshness |

---

## Critical Risk Register

Risks that could invalidate substantial completed work, rather than merely delay it.

| # | Risk | Phase | Impact | Mitigation |
|---|---|---|---|---|
| R1 | **ShareAlike opinion says model weights are adapted material** | 3 | Commercial model invalidated | Green/Amber fallback path quantified in Phase 3; architecture already tier-partitioned |
| R2 | **Unit determination fails for key endpoints** | 2 | Endpoints unusable | Empirical protocol (Step 8 §5); exclude rather than guess |
| R3 | **Small-data ceiling** — endpoints cannot reach usable accuracy | 3 | Product scope shrinks | Phase 3 gate is designed to surface this; positioning is triage, not replacement |
| R4 | **Conformal intervals too wide to be useful** | 4 | Perceived value drops | It is the true answer; frame as triage confidence, not a defect to engineer around |
| R5 | **Regulatory process burden under-resourced** | 9 | Timeline doubles | Staff quality/regulatory early; do not defer to Phase 9 |
| R6 | **Training/serving skew reintroduced** | 7 | Silent wrong predictions | Shared `drugsim_chem`; `feature_set_id` enforcement; CODEOWNERS |
| R7 | **UI overstates confidence** | 8 | Reputational and possibly regulatory | Uncertainty-first design; gate criterion; OOD unsuppressible |
| R8 | **Upstream source decay** | 2, 10 | Data staleness | Registry cadence monitoring; SIDER already demonstrates the failure mode |

---

## Phase Summary

| Phase | Focus | Weeks | Cumulative |
|---|---|---|---|
| 1 | Data foundation | 6–8 | ~2 mo |
| 2 | Core DB build | 12–16 | ~6 mo |
| 3 | Baselines & benchmarking | 10–14 | ~9 mo |
| 4 | Uncertainty & AD | 8–10 | ~11 mo |
| 5 | Mechanistic & multi-task | 12–16 | ~15 mo |
| 6 | Target prediction & KG | 10–14 | ~18 mo |
| 7 | Platform services | 10–12 | ~21 mo |
| 8 | Product surface | 14–18 | ~25 mo |
| 9 | Regulatory validation | 16–20 | ~30 mo |
| 10 | Continuous learning | ongoing | — |

**A defensible internal tool exists at Phase 4 (~11 months).** A commercial product exists at Phase 8 (~25 months). Regulatory readiness at Phase 9 (~30 months). If runway is shorter than that, the honest options are to descope the regulatory path or narrow the endpoint set — not to compress the gates.

---

*End Step 12. Phase 1 design corpus complete.*
