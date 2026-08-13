# TDS §11 — Risk Register

**Scoring:** Likelihood and Impact are Low / Medium / High. **Severity** = the combination, prioritised by what would be hardest to recover from rather than by simple multiplication.

**Owner roles:** Tech Lead (TL) · Data Owner (DO) · ML Owner (MLO) · Security Owner (SO) · Product Owner (PO) · Quality/Regulatory (QA)

---

## 11.1 Critical Risks

Risks that could invalidate substantial completed work or the product proposition itself.

### R1 — ShareAlike copyleft reaches model weights
**Likelihood:** Medium · **Impact:** High · **Owner:** PO (legal), TL (technical)

ChEMBL (CC BY-SA 3.0), DrugCentral, PharmGKB and part of BindingDB carry ShareAlike. Whether model weights and predictions constitute "Adapted Material" is genuinely unsettled — and ChEMBL, the anchor source, is on CC BY-SA **3.0**, which predates CC 4.0's explicit handling of *sui generis* database rights.

**Mitigation:** licence tier is a physical partition and a per-record column (ADR-007); `model_version.training_license_tiers` makes "is this commercially shippable?" a query; a Green/Amber-only fallback path is a standing requirement, and its accuracy cost is quantified in Phase 3.
**Trigger for escalation:** written legal opinion required before Phase 3 completes. This is the only external dependency that can invalidate completed work.
**Residual:** if the opinion is adverse, DrugSim ships the fallback models at a measured accuracy cost — degraded, not blocked.

### R2 — Units cannot be established for key endpoints
**Likelihood:** Medium · **Impact:** High · **Owner:** DO

TDC does not document units for most ADME/Tox endpoints (verified 2026-08-05). Unit assignment is therefore empirical.

**Mitigation:** the five-step G4 protocol (range, distribution, cross-source triangulation, reference compounds, **sign convention**); `unit_verified_method='unverified'` blocks publication (UV-05).
**Worst case, named:** the LD50 sign convention. A sign inversion trains cleanly, converges, and reports good metrics while ranking safe compounds as dangerous. Range and distribution checks all pass on inverted data — **only the reference-compound sign check catches it.**
**Residual:** an endpoint whose units cannot be established is excluded. Unusable is acceptable; confidently wrong is not.

### R3 — Small-data ceiling; endpoints cannot reach usable accuracy
**Likelihood:** **High** · **Impact:** Medium · **Owner:** MLO

Verified corpus sizes: bioavailability 640, half-life 667, DILI 475, carcinogenicity 278.

**Mitigation:** Phase 3's gate exists to surface this before a UI promises anything; positioning is triage rather than replacement (§1.1.1); `training_set_size` is exposed in every prediction response.
**Residual:** the product's endpoint coverage will be narrower than the brief's full list. This is a scope outcome, not a failure — but it must be discovered in Phase 3, not after Phase 8.

### R4 — Cross-tenant disclosure of customer structures
**Likelihood:** Low · **Impact:** **Very High** · **Owner:** SO

A pre-patent structure disclosed to a competitor can destroy patentability. This is the risk most likely to end a customer relationship and potentially the company.

**Mitigation:** `tenant_id` never client-supplied; **RLS as the enforcement layer**, not application filters; 404-not-403 on cross-tenant access; evidence drawn only from public data; automated cross-tenant probes in CI; structures never in logs (five layers, §7.2.3); structures never used for training.
**Residual:** low, but non-zero. Notification threshold is deliberately set at *possible* exposure, not confirmed exfiltration, so customers retain the ability to act on their own filings.

### R5 — Training/serving skew
**Likelihood:** Medium · **Impact:** High · **Owner:** MLO, TL

Descriptors computed differently at inference than at training produce silently wrong predictions at scale, with no error and no obvious symptom.

**Mitigation:** one shared `drugsim_chem` library, CODEOWNERS-protected; a lint rule prohibiting RDKit imports elsewhere; `feature_set_id` content-addressing including the RDKit version; **runtime assertion that raises and fails the request** on mismatch; the mismatch counter alerts on any non-zero value.
**Residual:** low, provided the assertion is never downgraded to a warning. That downgrade — under deadline pressure, to unblock a deploy — is the realistic failure path.

---

## 11.2 Scientific Risks

### R6 — Model bias from actives-biased literature data
**Likelihood:** **High** · **Impact:** Medium · **Owner:** MLO, DO

ChEMBL is abstracted from medicinal chemistry literature, which overwhelmingly reports actives. Models learn a skewed prior and systematically over-predict activity.

**Mitigation:** ToxCast/Tox21 provide large volumes of genuine negatives under public domain licensing — a primary reason for their high priority in Phase 1; class balance monitored per endpoint; calibration corrects some but not all of the bias.
**Residual:** persistent and inherent to public data. Should be documented in model cards rather than implied away.

### R7 — Confident predictions on out-of-domain molecules
**Likelihood:** **High** (absent controls) · **Impact:** High · **Owner:** MLO

Novel designed molecules are, by construction, where training data is thinnest.

**Mitigation:** `ad_verdict NOT NULL`; three combined AD methods plus novel-element detection; conformal intervals that widen honestly; `refused_out_of_domain` as a supported response; `must_display` plus frontend conformance tests making suppression a build failure.
**Residual:** users may still over-trust a point estimate. Mitigated by design and copy, not eliminable.

### R8 — Physically incoherent PK prediction sets
**Likelihood:** Medium · **Impact:** Medium · **Owner:** MLO

Half-life, VDss and clearance predicted by independent models can violate t½ = ln2·Vss/CL.

**Mitigation:** `pk_consistency_check` at 3-fold tolerance; inconsistency is **flagged, never silently reconciled** — it usually indicates at least one prediction is out of domain, which is exactly the signal to surface.
**Residual:** low once implemented; the risk is failing to implement it, since nothing else in the stack would notice.

### R9 — Data quality: silent pipeline regression
**Likelihood:** Medium · **Impact:** High · **Owner:** DO

A standardisation change silently alters hundreds of thousands of structures and is noticed two releases later.

**Mitigation:** golden set (~500 hand-verified compounds incl. every salt-stripping edge case) in CI; idempotency property tests; statistical process control per release; cross-source consistency monitoring.
**Residual:** low, provided golden-set differences are always explained rather than rubber-stamped.

### R10 — Upstream source decay
**Likelihood:** **High** (already occurring) · **Impact:** Medium · **Owner:** DO

SIDER is frozen at 2015 and its funding ended; DrugCentral's cadence appears to have slowed to 2023. This is not hypothetical.

**Mitigation:** registry cadence monitoring with staleness alerts; `is_stale` exposed in the Dataset contract; openFDA FAERS adopted in place of SIDER; EBI's SIDER successor tracked.
**Residual:** accepted. Public data infrastructure is chronically underfunded, and the correct response is transparency about staleness rather than pretending currency.

---

## 11.3 Engineering Risks

### R11 — Managed-Postgres unavailability constrains deployment
**Likelihood:** High (certain) · **Impact:** Low–Medium · **Owner:** TL

The RDKit cartridge is unavailable on RDS, Cloud SQL and Aurora, so Postgres is self-managed.

**Mitigation:** custom `postgres-rdkit` image as a first-class, signed, change-controlled artefact; pgBackRest with tested quarterly restores; replica for failover; IaC for reproducible rebuild.
**Residual:** accepted in ADR-003 — the capability is central. The real cost is operational burden, which must be staffed rather than assumed away.

### R12 — Scalability: Postgres as the single stateful component
**Likelihood:** Low · **Impact:** Medium · **Owner:** TL

**Mitigation:** verified data volumes are modest (§3.12 sizing); vertical scaling plus a read replica covers well beyond initial needs; the job queue is abstracted for migration to a dedicated broker (§3.4) if contention appears.
**Residual:** low. The greater risk is over-engineering for scale that never arrives — explicitly guarded against by P10.

### R13 — Malicious or malformed chemical file upload
**Likelihood:** Medium · **Impact:** Medium–High · **Owner:** SO

RDKit is a large C++ library parsing untrusted, structurally complex input.

**Mitigation:** sandboxed subprocess with `rlimit` and seccomp; hard per-record timeout; size and record-count caps; compressed uploads rejected; property fields never evaluated or rendered.
**Residual:** low. Subprocess isolation converts a potential RCE into a handled child-process crash.

### R14 — Supply chain compromise
**Likelihood:** Low · **Impact:** High · **Owner:** SO

**Mitigation:** hash-pinned lockfile; digest-pinned base images; vulnerability scanning and SBOM in CI; signed images verified at deploy; `postgres-rdkit` built in-repo rather than pulled from a community source.
**Residual:** low, with residual exposure to a compromised upstream package before detection.

### R15 — Maintenance burden: constraints and triggers silently lost
**Likelihood:** Medium · **Impact:** High · **Owner:** TL

Much of DrugSim's integrity lives in database constraints and triggers, which are invisible in application code and easy to drop in a migration. Functional tests would all still pass.

**Mitigation:** `tests/constraints/` asserts that violating inserts **fail**, for every constraint and trigger; forward-only migrations under review by the data owner.
**Residual:** low, provided the constraint suite is maintained alongside new constraints — which is itself a review-checklist item.

---

## 11.4 Regulatory and Organisational Risks

### R16 — Regulatory process burden under-resourced
**Likelihood:** **High** · **Impact:** High · **Owner:** QA, PO

Phase 9 is mostly not software: validation documentation, SOPs, change control, signature workflows. It is the phase most likely to be underestimated.

**Mitigation:** schema and audit machinery built from Phase 1 so nothing is retrofitted; `docs/validation/` exists from the start; validation *execution* deliberately deferred to Phase 5+ so runway is not consumed early.
**Residual:** **high, and this is a hiring dependency rather than an engineering one.** Staffing Phase 9 with engineers alone will fail. Flag early to leadership.

### R17 — Part 11 compliance overestimated from a compliant-looking schema
**Likelihood:** Medium · **Impact:** High · **Owner:** QA

Part 11 is a property of the whole system — hosting, access control, SOPs, training, change control — not of a database schema.

**Mitigation:** stated explicitly in the Phase 1 regulatory addendum and again here; validation scope defined by QA, not by engineering.
**Residual:** medium. The failure mode is organisational confidence outrunning organisational readiness, and the only mitigation is repeated, explicit statement.

### R18 — Product positioning drifts toward overclaiming
**Likelihood:** Medium · **Impact:** High · **Owner:** PO

Commercial pressure pushes toward "replaces animal testing"; the data supports "improves experimental prioritisation".

**Mitigation:** non-goals are explicit (§1.5); `training_set_size` exposed in every response; `must_display` conformance; unpopulated endpoints absent from the UI entirely rather than shown as empty; the mandatory `interpretation_note` on drug-likeness.
**Residual:** medium. Technical controls constrain the product surface but cannot constrain a sales deck. This needs periodic review by PO and a scientific reviewer.

### R19 — Key-person dependency on cheminformatics expertise
**Likelihood:** Medium · **Impact:** Medium · **Owner:** TL

Correct use of ToxCast hit calls, Ames strain panels, standardisation edge cases and AD calibration requires domain knowledge that is scarce and hard to recover once lost.

**Mitigation:** the Phase 1 corpus and this TDS document *reasoning*, not just decisions; ADRs preserve rejected alternatives; golden set encodes edge-case knowledge as executable tests.
**Residual:** medium. Documentation reduces but does not eliminate it; a second cheminformatics hire is the real mitigation.

---

## 11.5 Summary

| ID | Risk | L | I | Owner | Phase |
|---|---|---|---|---|---|
| R1 | ShareAlike reaches model weights | M | H | PO/TL | 3 |
| R2 | Units cannot be established | M | H | DO | 2 |
| R3 | Small-data ceiling | **H** | M | MLO | 3 |
| R4 | Cross-tenant structure disclosure | L | **VH** | SO | 7+ |
| R5 | Training/serving skew | M | H | MLO/TL | 7 |
| R6 | Actives-biased training data | **H** | M | MLO/DO | 3 |
| R7 | Confident OOD predictions | **H** | H | MLO | 4 |
| R8 | Incoherent PK sets | M | M | MLO | 5 |
| R9 | Silent pipeline regression | M | H | DO | 2 |
| R10 | Upstream source decay | **H** | M | DO | 2, 10 |
| R11 | Self-managed Postgres burden | H | L–M | TL | 2 |
| R12 | Postgres scaling ceiling | L | M | TL | — |
| R13 | Malicious chemical upload | M | M–H | SO | 7 |
| R14 | Supply chain compromise | L | H | SO | 2 |
| R15 | Constraints lost in migration | M | H | TL | 2 |
| R16 | Regulatory burden under-resourced | **H** | H | QA/PO | 9 |
| R17 | Part 11 compliance overestimated | M | H | QA | 9 |
| R18 | Positioning overclaims | M | H | PO | 8 |
| R19 | Cheminformatics key-person | M | M | TL | — |

**Review cadence:** quarterly, or on any phase gate. Each risk's owner reports status; new risks are added by PR to this document under the change control in README §0.3.

**The three to watch hardest:** R1 (can invalidate completed work), R4 (can end the company), R16 (most likely to be underestimated, and the mitigation is hiring rather than engineering).

---

*End §11. TDS complete.*
