# Phase 3.5 Scientific Audit — hERG Inhibition Model v0.1.0

**Scope:** focused audit of the EXPERIMENTAL hERG model per the Phase 3.5 brief. Read-only — no retraining, no architecture change, no data silently removed. All supporting analysis is committed, reproducible code (`models/admet/herg_inhibition/audit_assay_heterogeneity.py`, `threshold_sensitivity.py`) with JSON reports alongside it.

**Outcome: no BLOCKER found. Model status unchanged: EXPERIMENTAL. Five WARNING-level findings require attention before any promotion beyond EXPERIMENTAL.**

---

## 1. hERG endpoint homogeneity

Bulk-fetched assay-level metadata (description, `assay_organism`, `confidence_score`, `bao_label`) for all 2,651 assays referenced in the raw pull (`audit_assay_heterogeneity.py`).

**Finding: ChEMBL's own `assay_type` field (B/F/T/A) is not a reliable paradigm partition for this target.** A "Binding affinity to human ERG" assay is filed under type `T`; genuine two-electrode voltage-clamp and manual patch-clamp assays appear under type `A`. Classification instead used assay description text.

| Category (by record count) | Fraction | Interpretation |
|---|---|---|
| Functional electrophysiology (patch clamp, IKr current) | 33.5% | Direct functional channel block |
| Ambiguous/generic ("Inhibition of human ERG", no further detail) | 33.0% | Cannot determine paradigm from text alone |
| Binding displacement (radioligand, e.g. MK-499) | 25.4% | Target *affinity*, not necessarily functional block |
| Functional flux/fluorescence (FLIPR, Rb⁺/Tl⁺ flux) | 6.8% | Functional, different readout mechanism |
| Unclassified | 1.3% | — |

**Finding — genuine cross-species records:** 3 assays (16 compounds, 15 surviving into the final 9,589-compound dataset) are native guinea-pig cardiac myocyte measurements (e.g. *"Blockade of the delayed rectifier K+ current (IKr) of guinea pig myocytes"*), assigned to the human target CHEMBL240 by ChEMBL via homology (`confidence_score=8`, not the modal 9). This is a real species proxy, not a curation error — guinea pig IKr pharmacology correlates with but is not identical to human hERG.

**Finding — one data-quality anomaly:** assay `CHEMBL5058672` has `assay_organism="Blocker"` (not a real organism — a corrupted ChEMBL field on one safety-screen assay). Affects 1 molecule, **0 of which survive into the final dataset** — moot for the current model.

**Target confidence:** 96.6% of records at `confidence_score=9` (direct single protein, the ceiling), 3.4% at `confidence_score=8`. No records below 8.

**Disposition (per record/compound, not silently altered):**

| Group | Disposition |
|---|---|
| Single-paradigm records (95.6% of raw-filtered molecules) | **Remain** — no ambiguity |
| Guinea-pig native-tissue records (16 compounds / 15 in final dataset) | **Should be quarantined or flagged** in a future rebuild — not done here (out of scope: would require rebuilding the dataset) |
| The one `assay_organism="Blocker"` record | **No action needed** — already absent from the final dataset |
| Mixed binding+functional records for the same compound (see §3) | **Should require a separate-endpoint or stratified-aggregation policy** in Phase 4 |

**Classification: WARNING.** Material, quantified assay heterogeneity exists; it does not invalidate the current EXPERIMENTAL model (leakage checks and y-scrambling in the original report are unaffected by this finding — they test the model/data relationship, not assay provenance), but a single "hERG inhibition" label currently blends at least two distinguishable experimental paradigms.

---

## 2. The 10 µM threshold — sensitivity analysis

Re-labeled the existing 9,589-compound dataset (no refetch, no recomputation) at 1/3/10/30 µM and retrained the exact registered Random Forest config at each (`threshold_sensitivity.py`).

| Threshold | Class split (blocker/non) | Changed vs. 10 µM | Val ROC-AUC | Test ROC-AUC | Test balanced accuracy |
|---|---|---|---|---|---|
| 1 µM | 19.3% / 80.7% | 4,508 (47.0%) | 0.8533 | 0.8245 | 0.6455 |
| 3 µM | 35.9% / 64.1% | 2,917 (30.4%) | 0.8392 | 0.8252 | **0.7153** |
| **10 µM (registered)** | 66.4% / 33.6% | — | 0.8394 | **0.7875 (lowest)** | 0.6495 |
| 30 µM | 89.0% / 11.0% | 2,174 (22.7%) | 0.8452 | **0.8509 (highest)** | **0.5441 (lowest)** |

**The registered threshold (10 µM) has the *lowest* test ROC-AUC of the four candidates.** Selecting by ROC-AUC alone would favour 30 µM — but 30 µM's class split is 89/11 (only ~88 negatives in the 800-compound test set), and its balanced accuracy (0.5441, barely above the 0.50 chance floor) shows this is a class-imbalance artifact, not genuinely better discrimination. This is exactly the "best metric" trap the audit brief warns against, made concrete: **ROC-AUC and balanced accuracy disagree on which threshold looks best**, and the disagreement is explained by imbalance, not by model quality.

**Nearly half the dataset (47%) changes class between the 1 µM and 10 µM cutoffs.** No single threshold is a small perturbation of another; the four candidates are, in a real sense, four different labeling problems on the same compounds.

**Recommendation (not executed — would require rebuilding and re-validating the dataset, out of this audit's scope):**
- **3 µM is the more scientifically defensible threshold for a future iteration** — best test balanced accuracy, competitive ROC-AUC, and a moderate (not extreme) class split, without cherry-picking the one metric that happens to favour it (unlike 30 µM, which only wins on ROC-AUC).
- **10 µM is not disqualified** — it remains a widely-cited literature default and the model was fully validated (leakage, y-scrambling, AD, conformal) at this threshold. It is not being changed by this audit.
- **Stronger long-term recommendation for Phase 4:** given no threshold is robustly dominant and 47% class-flip sensitivity, reformulate this endpoint as **regression on continuous pIC50** rather than committing to any single binary cutoff, which structurally avoids this problem rather than tuning around it.

**Classification: WARNING.** Does not invalidate the current model (it was validated at its own stated threshold, and the report never claimed 10 µM was metric-optimal), but the threshold choice needs revisiting before promotion beyond EXPERIMENTAL.

---

## 3. Aggregation appropriateness

For the 100 compounds with **both** a binding-displacement and a functional-electrophysiology measurement: potency values are **not reliably interchangeable** — mean log10 ratio 0.19 but stdev 0.87; 23% of pairs differ by >10×, 51% by >3.16× (`audit_assay_heterogeneity.py`, `binding_vs_functional_comparability`).

**Quantified impact on the actual training set:**

| | Count | Fraction of 9,802 candidate molecules |
|---|---|---|
| Single-paradigm (no concern) | 9,373 | 95.6% |
| Mixed-paradigm, caught by the existing >10× discordance filter (already excluded) | 77 | 0.8% |
| **Mixed-paradigm, silently geometric-averaged (≤10× spread, no flag)** | **352** | **3.6%** |

The existing discordance filter (`aggregate_continuous`, >10× spread → excluded) already catches the worst cross-paradigm disagreements. It does **not** distinguish "two functional replicates that happen to differ 5×" from "one binding value and one functional value that happen to agree within 5×" — both look identical to a spread-only check. For 3.6% of candidate compounds, this means the aggregated value blends two paradigms without any record of having done so.

**The geometric-mean aggregation *method* itself is appropriate and unchanged** — potency data is log-normally distributed and geometric mean is the right summary when inputs are comparable. The finding is about **input comparability**, not the formula. Per the instruction not to change the aggregation policy without documenting the reason: **no change made**. Recommended for Phase 4: add an assay-category flag to the discordance check (require same-paradigm agreement, or treat paradigm as a stratification variable rather than aggregating across it silently).

**Classification: WARNING.** Affects 3.6% of the dataset — real and worth fixing, not large enough to retroactively invalidate the EXPERIMENTAL model's already-reported y-scrambling/leakage results (which test model-vs-data relationships that this finding doesn't bear on directly).

---

## 4. Provenance

| Check | Result |
|---|---|
| Raw CSV (`chembl_herg_ic50_raw.csv`) sha256 matches `chembl_herg_ic50_manifest.json` | **PASS** — `098527c1...` confirmed byte-for-byte |
| Processed dataset CSV sha256 matches `herg_inhibition_dataset_manifest.json` | **PASS** — `6c0ecaaf...` confirmed byte-for-byte |
| Live ChEMBL record count still matches the manifest's recorded total | **PASS** — queried live during this audit: 17,099, unchanged from retrieval |
| Long-term bit-reproducibility of `fetch_chembl_data.py` | **WARNING** (already disclosed in the Phase 3 report) — ChEMBL is a live, growing database; a re-run next month is not guaranteed to reproduce this exact 17,097-row file. The manifest's checksum pins what was actually used; it does not make future re-runs identical. |

### Phase 3 bypasses of the Phase 2 database — technical debt, not silently changed architecture

None of the following were implemented differently than documented in Phase 2/3; this section restates them as an explicit, itemized debt list per the audit brief's instruction.

| Phase 2 mechanism | Phase 3 actually did |
|---|---|
| `drugsim_ingest.landing.LandingZone` (S3-backed, write-once immutability) | Wrote plain CSV files directly to `datasets/raw/`, no immutability enforcement beyond a manual checksum in a JSON manifest |
| `drugsim_db.registry_sync` + `ingestion_snapshot` table | No `data_source`/`ingestion_snapshot` row created for the ChEMBL pull; provenance lives only in a local JSON file |
| `drugsim_db.bulk_load` → `compound`/`compound_descriptor`/`compound_drug_likeness` | Never invoked — standardised compounds live in a flat CSV, not the real schema |
| `measurement` / `measurement_aggregate` tables | `aggregate_continuous` was called as a pure function (correct reuse of the *logic*), but its output was never persisted through the actual DB tables built for exactly this |
| `compound_split_assignment` (with `uq_scaffold_single_group` enforcement) | `split_group` computed and stored only in a local `.npz`/CSV; the real constraint was never exercised |
| `model` / `model_version` / `model_validation_record` | Captured as a JSON file (`models/registry/herg_inhibition_v1.json`), not real DB rows |

**Root cause (unchanged since Phase 2): no live Postgres in this environment (no Docker).** This is the same limitation documented in `docs/phase2/phase2-completion-report.md`, not a new decision made in Phase 3. **Classification: WARNING (technical debt, explicitly tracked).** Reconciling Phase 3's artifacts into the real schema is a prerequisite for any production path, not for continued EXPERIMENTAL-status research use.

---

## 5. Phase 3 report fact-check

Every numerical claim in `docs/phase3/phase3-model-validation-report.md` was checked against its generating JSON artifact (`train_manifest.json`, `leakage_report.json`, `y_scrambling_report.json`, `evaluation_report.json`, `reliability_report.json`, `herg_inhibition_dataset_manifest.json`, `herg_inhibition_features_manifest.json`).

**One factual error found and corrected:** §1's endpoint-comparison table cited hERG's total record count as "19,807 across all potency bands." This came from summing seven potency-band queries whose boundaries (100/1,000/4,000/10,000/40,000/100,000 nM) were inclusive on both sides, double-counting every record sitting exactly at a boundary (verified directly: re-querying with correct non-overlapping filter syntax reproduces exactly 19,807 for the flawed method and exactly 17,099 for the true unfiltered total — the actual number `fetch_chembl_data.py` paginated over). **Corrected in the report** with an inline note; does not change the endpoint-selection conclusion (hERG is still the largest of the three candidates compared).

**Every other checked figure matched exactly:** dataset counts (9,589 / 6,363 / 3,226), split group sizes (6,792/976/1,021/800), scaffold count (5,079), all three candidate models' validation ROC-AUC, all leakage-check counts (0 duplicate/scaffold violations, 15 near-duplicate pairs, 3 exact collisions), y-scrambling (0.8394 vs. 0.4890±0.0427), both evaluation splits' full metric sets and confusion matrices, the ROC-AUC gap (0.0613), conformal coverage (0.8988), calibration Brier/ECE for all three variants, and both applicability-domain accuracy breakdowns. No wording was changed beyond what the correction required.

**Classification: PASS** (one error found and fixed; everything else verified accurate).

---

## 6. Summary

| # | Area | Classification |
|---|---|---|
| 1 | Endpoint homogeneity (assay-paradigm mix) | **WARNING** |
| 1 | Cross-species records (16 compounds, homology-assigned) | **WARNING** (low materiality — <0.2% of dataset) |
| 1 | Organism-field data anomaly | **PASS** (0 compounds in final dataset) |
| 1 | Target confidence (96.6% at ceiling) | **PASS** |
| 2 | 10 µM threshold vs. sensitivity analysis | **WARNING** |
| 3 | Aggregation method (geometric mean) | **PASS** (method itself correct) |
| 3 | Silent cross-paradigm averaging (3.6% of compounds) | **WARNING** |
| 4 | Checksums / manifest reproducibility | **PASS** |
| 4 | Long-term fetch reproducibility | **WARNING** (disclosed limitation) |
| 4 | Phase 2 DB bypass | **WARNING** (tracked technical debt) |
| 5 | Report fact-check | **PASS** (1 error found and corrected) |

**No BLOCKER-level finding.** Nothing here contradicts the original report's leakage checks, y-scrambling result, or conformal coverage — those tested the model-data relationship directly and remain valid. The WARNINGs are about **what the endpoint and label actually represent** (assay mix, threshold choice, aggregation homogeneity) and **how disconnected this pipeline still is from the real Phase 2 schema** — both legitimate blockers to promotion *beyond* EXPERIMENTAL, neither a reason to retract the current status.

**Model status: unchanged — EXPERIMENTAL.** Recommended before any promotion to VALIDATED FOR INTERNAL RESEARCH: resolve the five WARNING items above, in priority order (3) aggregation stratification, (1) endpoint/assay-paradigm decision, (2) threshold reconsideration or regression reformulation, (4) DB integration. Phase 4 is not started by this audit.
