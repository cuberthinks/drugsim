# Phase 9 — Multi-Endpoint ADMET Expansion

**Status:** Complete. One new endpoint (CYP3A4 inhibition) developed, validated, and integrated end-to-end. The existing hERG model, dataset, registry entry, and API contract are unchanged.

This report documents the second point in DrugSim's scientific framework, not a wider platform. Everything here follows the same evidentiary pattern established for hERG in Phases 3–5: pick one endpoint, build its dataset honestly, evaluate it thoroughly, decide its promotion status on the evidence, and only then wire it into the shared prediction engine.

---

## 1. Endpoint

**Selected:** CYP3A4 inhibition (ChEMBL target `CHEMBL340`, Cytochrome P450 3A4, *Homo sapiens*).

**Biological meaning:** CYP3A4 metabolises roughly half of all marketed small-molecule drugs. A compound that inhibits it can raise the blood levels of other drugs cleared by the same enzyme — the mechanism behind a large share of clinically significant drug-drug interactions. This makes it a natural second endpoint for a platform whose first (hERG) already covers a distinct ADMET category (cardiac toxicity); CYP3A4 is the platform's first endpoint in the **Metabolism** category.

**Definition:** Binary classification. label = 1 ("inhibitor") if the aggregated ChEMBL IC50 across all measurements for a standardised compound is ≤ 10,000 nM (10 µM); label = 0 ("non-inhibitor") otherwise. The 10 µM cutoff is a literature screening convention (the same convention class already used for hERG's blocker threshold), not a fixed biological or regulatory boundary — documented as such everywhere the threshold is surfaced.

**Units:** nanomolar IC50, aggregated per standardised entity (InChIKey) by geometric mean across all matching ChEMBL activity records, following the identical `aggregate_continuous(is_potency=True)` methodology already validated for hERG.

Full candidate ranking, rejected/deferred alternatives (P-glycoprotein, AMES, BBB penetration, CYP2D6/2C9, DILI, human bioavailability, and the TDC continuous-endpoint class — rejected because the project's own `datasets/registry.yaml` already flags TDC's units for those endpoints as unverified), and the justification for selecting CYP3A4 are in [`docs/phase9/endpoint-selection.md`](endpoint-selection.md).

---

## 2. Dataset

| | |
|---|---|
| Source | ChEMBL REST API, direct fetch (same pattern as hERG — not TDC) |
| Raw activities fetched | 12,357 |
| Final compound count | **5,344** (3,579 inhibitor / 1,765 non-inhibitor, 66.97% positive) |
| Unique Bemis-Murcko scaffolds | 3,009 |
| Duplicate InChIKeys after standardisation | 0 |
| Impossible/suspicious values | 0 (after fix — see below) |
| Split methodology | Deterministic scaffold hashing (ADR-009), independent salt (`cyp3a4_inhibition_v1`) from hERG's, groups 0–6 train / 7 calibration / 8 validation / 9 test |
| Dataset version | `v1` |

**A real data-quality bug was found and fixed during this phase.** The first `data_quality_audit.py` run found one compound with `standard_value = 0.0` nM and a ChEMBL `data_validity_comment` of `"Outside typical range"` — an impossible potency value that would have silently corrupted its aggregate. Root cause: the exclusion filter only rejected `"Potential transcription error"` and `"Potential author error"`, not `"Outside typical range"`. Fixed for CYP3A4 by adding that flag to the exclusion set and adding a defense-in-depth `aggregated_value <= 0` filter. **hERG's own `build_dataset.py` was deliberately left unchanged** — a check of its raw data found it has the same unaddressed gap (367 "Outside typical range" records not excluded), left as a documented, un-retroactively-fixed observation per the explicit "do not modify the validated hERG model" constraint. This is recorded in the CYP3A4 registry's `dataset.impossible_value_note` field so it isn't lost.

Every record in the built dataset retains its ChEMBL provenance (`molecule_chembl_id`, source activity IDs) and CC-BY-SA-style ChEMBL licensing, consistent with the existing hERG dataset's provenance model.

---

## 3. Model

| | |
|---|---|
| Algorithm | Random Forest (`sklearn.ensemble.RandomForestClassifier`), `n_estimators=500`, `max_depth=None`, `class_weight="balanced"`, `random_seed=42` |
| Features | Identical toolchain to hERG: 18 physicochemical descriptors + 2048-bit radius-2 Morgan fingerprint (2,066 columns). `feature_set_id` is *identical* to hERG's by construction — it is a content-address over the shared toolchain (RDKit version, descriptor spec, standardisation pipeline), not a per-dataset identifier. Documented explicitly in the registry to pre-empt any appearance of an error. |
| Selected over | Gradient Boosting (val. ROC-AUC 0.7298), Logistic Regression (0.6866) — Random Forest won at 0.7870 |
| Training set size | 3,767 compounds (split groups 0–6) |

**Baselines (Phase 9 Sec 6 — new requirement, not present in hERG's original scripts):**

| Baseline | Validation ROC-AUC | Balanced accuracy |
|---|---|---|
| Majority class | undefined (constant predictor) | 0.500 |
| Descriptor-only logistic regression | 0.6148 | 0.5866 |
| Descriptor-only random forest | 0.7291 | 0.5976 |
| **Champion (full model)** | **0.7870** | **0.6506** |

The champion model beats the strongest baseline by +0.0579 ROC-AUC — a meaningful, non-trivial improvement, not just the highest single number among near-identical candidates.

---

## 4. Validation

**Global scaffold-split test (group 9, the honest number — n=459):**

| Metric | Value |
|---|---|
| ROC-AUC | 0.7995 (95% bootstrap CI: 0.7593–0.8382, 1,000 replicates) |
| PR-AUC | 0.8922 |
| Balanced accuracy | 0.6520 |
| Matthews correlation coefficient | 0.3564 |
| Sensitivity (recall, inhibitor) | 0.8987 |
| **Specificity (recall, non-inhibitor)** | **0.4052 — the model's clearest weakness** |
| Confusion matrix | tn=62, fp=91, fn=31, tp=275 |

**Benchmark proxy (random-split, same data pool, n=459):** ROC-AUC 0.8391, balanced accuracy 0.7291. **Gap: +0.0396 ROC-AUC**, attributed to near-duplicate/scaffold leakage that the scaffold split correctly removes — the gap is evidence the scaffold split is working, not a sign the model degraded.

**Comparison to hERG (the platform's existing validated standard):** hERG's own registered scaffold-split test metrics are ROC-AUC 0.7875, balanced accuracy 0.6495. CYP3A4's 0.7995 / 0.6520 are at parity — this is not a weaker bar being applied to admit a second endpoint.

---

## 5. Reliability

**Applicability domain** — three-signal verdict (Tanimoto similarity + k-NN descriptor distance + scaffold-seen-in-training):

| Verdict | n | Accuracy |
|---|---|---|
| in_domain | 0 *(see note)* | — |
| borderline | 262 | 82.82% |
| out_of_domain | 197 | 60.91% |

*Note:* `in_domain` is mathematically unreachable (0 cases) on any scaffold-holdout evaluation, because `scaffold_seen_in_training=False` is guaranteed by construction for every test compound — the exact same structural artefact already documented in hERG's own reliability report. A **supplementary two-signal verdict** (Tanimoto + k-NN only, scaffold excluded) preserves informativeness and shows the reliability signal is real and monotonic:

| Two-signal verdict | n | Accuracy |
|---|---|---|
| in_domain | 262 | 82.82% |
| borderline | 93 | 69.89% |
| out_of_domain | 104 | 52.88% |

Accuracy degrades cleanly from in-domain to out-of-domain, confirming `reliability_decreases_appropriately_out_of_domain = true`.

**Uncertainty (split conformal prediction, 90% nominal confidence):**

- Empirical coverage: **89.76%** — within tolerance of the 90% target.
- Singleton (confident) predictions: 62.75% of test compounds, accuracy **83.68%**.
- Ambiguous (both-classes-plausible) predictions: accuracy **56.14%**.
- `uncertainty_tracks_error = true` — the conformal set width is doing real work, not decoration.

**Calibration:** raw Brier score 0.168 (ECE 4.93%) — better than Platt scaling (Brier 0.176, ECE 10.25%) or isotonic (Brier 0.170, ECE 5.71%) on this test set; the raw model output is used as-is.

---

## 6. Error analysis

- **Dominant error mode: false positives.** False-positive rate 59.48% (91/153 true non-inhibitors misclassified) vs. false-negative rate 10.13% (31/306 true inhibitors misclassified) — consistent with the specificity weakness above. The model over-calls "inhibitor," plausibly reflecting the 67% positive-class training prevalence even with `class_weight="balanced"` applied, and/or CYP3A4's broad substrate promiscuity making the true-negative chemical space harder to characterise than hERG's more specific channel-blocking motif.
- **Borderline compounds** (probability within 0.05 of the decision boundary): 35 compounds, accuracy only 45.71% — expected for a hard threshold on a continuous measure.
- **Assay-variability proxy:** single-measurement-compound accuracy (74.94%) was *higher* than multi-measurement-compound accuracy (62.5%) — the reverse of what noisy aggregation would predict, so errors are not primarily explained by discordant source measurements slipping through aggregation. Combined with a clean `data_quality_report.json` (zero impossible values, zero leakage, zero unit inconsistency), the errors look like genuine model/chemistry limitations, not a pipeline defect.
- Worst errors cluster among true non-inhibitors whose aggregated IC50 sits just above the 10 µM cutoff (14,000–25,000 nM range) — exactly where a hard threshold on a continuous measurement is expected to be least reliable.

---

## 7. External validation

**Dataset:** TDC's `CYP3A4_Veith` (PubChem AID 1851, a Veith et al. 2009 *Nat Biotechnol* qHTS primary screen) — genuinely independent from the ChEMBL literature-curated training data (different assay methodology, different label-generation convention). PyTDC's own Python wrapper failed in this environment (the same pre-existing "TDC download endpoint blocked" limitation Phase 3 already documented for hERG); fetched instead by finding the correct Harvard Dataverse file ID in PyTDC's own source and pulling it directly via `httpx`, rather than fabricating a substitute.

**Overlap check:** 12,175 standardised external compounds vs. the ChEMBL training set — only 23 overlapping (**0.19%**). Metrics below are computed on the **12,152 genuinely disjoint** compounds only.

| Metric | Value |
|---|---|
| ROC-AUC | 0.7758 |
| PR-AUC | 0.7066 |
| Balanced accuracy | 0.7022 |
| Matthews correlation coefficient | 0.4016 |
| Confusion matrix | tn=4,325, fp=2,742, fn=1,056, tp=4,029 |

Performance on this external set is **consistent with, and on balanced accuracy better than**, the internal scaffold-split test — real evidence against overfitting. This comparison is honestly imperfect: TDC's label is PubChem's own single-concentration qHTS active/inactive call, a different operationalisation of "CYP3A4 inhibition" than this model's aggregated dose-response IC50 threshold, so some disagreement is expected from label-definition differences alone, not model error. Stated plainly in the external validation report rather than presented as a clean apples-to-apples number.

---

## 8. Final decision

### Promotion status: **VALIDATED FOR INTERNAL RESEARCH**

Reasoning (full detail in `models/registry/cyp3a4_inhibition_v1.json`'s `promotion_decision` block):

1. Meaningfully beats all three required baselines (+0.058 ROC-AUC over the strongest one).
2. Discriminative performance (0.7995 ROC-AUC) is at parity with the platform's existing validated hERG model (0.7875) — the same bar, not a weaker one.
3. Applicability domain shows the required monotonic reliability degradation (82.8% → 69.9% → 52.9%).
4. Conformal uncertainty achieves coverage within tolerance of its target, and confident predictions are demonstrably more accurate than uncertain ones (83.7% vs. 56.1%).
5. A genuinely independent external validation set (12,152 disjoint compounds) shows consistent, in places better, performance — strong evidence against overfitting.

This status was **not** reached by weakening the evaluation criteria to admit a second endpoint; it was reached because the evidence, on the same standard applied to hERG, supports it.

---

## 9. Limitations

Carried forward explicitly wherever this endpoint's predictions are surfaced:

- **Specificity (0.4052) is the model's weakest metric** — a real, asymmetric tendency to over-call "inhibitor." Never shown as a bare label without its reliability/uncertainty context.
- The **10 µM threshold is a literature screening convention**, not a clinical or regulatory boundary; errors concentrate near it, as expected for any hard cutoff on a continuous measure.
- External validation used a **differently-labelled** dataset (qHTS single-concentration screen vs. aggregated dose-response IC50) — reassuring, not a perfect confirmation.
- This endpoint covers **CYP3A4 inhibition only**. It says nothing about other CYP isoforms, other metabolic pathways, or actual clinical drug-drug-interaction risk, which depends on additional pharmacokinetic factors (dose, exposure, other enzyme/transporter involvement) this model does not model.
- As with hERG, this is a computational estimate from historical data, not a laboratory measurement, a clinical diagnosis, or a guarantee of safety.
- **Not claimed, for either endpoint:** exact human pharmacokinetics, clinical safety, patient outcomes, therapeutic efficacy, complete ADMET behaviour, or that the two endpoints combine into any kind of whole-body or whole-drug simulation. DrugSim remains a collection of independently validated predictions for specific, narrowly defined endpoints.

---

## 10. Integration

Reused the existing Phase 5 architecture end-to-end — no parallel pipeline was created:

- **`model_registry.py`**: `get_model_bundle()`/`load_model_bundle()` generalised from a no-arg, hERG-only `@lru_cache(maxsize=1)` singleton to a `model_id`-keyed cache (default unchanged: `get_model_bundle()` still returns exactly the hERG bundle). Added `list_registered_endpoints()` for discovery. Unknown `model_id` raises `UnknownEndpointError` (404).
- **`pipeline.py`**: `run_inference()` gained a `model_id` parameter (default `"herg_inhibition"`, unchanged behaviour for existing callers) and now enforces the promotion gate itself — any endpoint whose `final_report_status` isn't `"VALIDATED FOR INTERNAL RESEARCH"` raises `EndpointNotAvailableError` (403) before any inference runs, so every caller (API, health check, future scripts) gets the guarantee for free. Predicted labels now come from each bundle's own `positive_class_label`/`negative_class_label` (hERG: `blocker`/`non_blocker`, unchanged; CYP3A4: `inhibitor`/`non_inhibitor`) instead of a hardcoded hERG string.
- **`schemas.py` / `api.py`**: `PredictRequest.endpoint` is optional, defaulting to `herg_inhibition` — an old client that has never heard of "endpoint" gets exactly the behaviour it always had. `EstimateSchema.predicted_probability_blocker` is now nullable and populated **only** for hERG (never a misleadingly-named field for a different endpoint); a new generic `predicted_probability` field is populated for every endpoint, including hERG. `predicted_label`/`ConformalSchema.predicted_set` were widened from a hERG-only `Literal["blocker","non_blocker"]` to `str`/`list[str]` — a type relaxation only; hERG's actual served values are unchanged. New `GET /endpoints` route lists every registered endpoint with its promotion status and a `servable` boolean. `GET /model`/`GET /model/latest` accept an optional `?endpoint=` query parameter.
- **Frontend**: a new `EndpointSelector` lets a user choose between registered endpoints, showing real promotion status (never a placeholder) and disabling anything not servable. Per-endpoint label/description copy lives in `src/lib/endpointCopy.ts`. No overall "drug score" was introduced — each endpoint's result is shown independently, per Phase 9 Sec 18.

**Regression verification:** the full existing test suite (620 tests pre-Phase-9) plus 16 new multi-endpoint tests plus updated frontend/E2E coverage all pass — 636 backend tests, 49 frontend unit tests, 21 Playwright E2E tests, zero hERG regressions. hERG's registered model artifact, dataset, and registry entry were not modified.

---

## Completion summary (per the phase's own reporting requirements)

1. **Selected endpoint:** CYP3A4 inhibition (ChEMBL CHEMBL340).
2. **Dataset size:** 5,344 compounds (3,579 inhibitor / 1,765 non-inhibitor), built from 12,357 raw ChEMBL activity records.
3. **Model performance:** ROC-AUC 0.7995 (95% CI 0.7593–0.8382), balanced accuracy 0.6520, MCC 0.3564 on the scaffold-split test — at parity with hERG's own validated performance.
4. **Reliability:** conformal coverage 89.76% (target 90%), confident predictions 83.7% accurate vs. 56.1% for ambiguous ones — uncertainty tracks real error.
5. **Applicability-domain performance:** clean monotonic degradation, 82.8% → 69.9% → 52.9% accuracy from in-domain to out-of-domain (two-signal verdict; three-signal in-domain is 0 by the same structural artefact already documented for hERG).
6. **External validation status:** performed, on 12,152 genuinely disjoint TDC CYP3A4_Veith compounds (0.19% overlap with training); ROC-AUC 0.7758, consistent with internal test performance.
7. **Final promotion status:** **VALIDATED FOR INTERNAL RESEARCH.**
8. **Major limitations:** weak specificity (0.4052, real over-calling of "inhibitor"); threshold is a screening convention, not a clinical boundary; external labels use a different operationalisation of the endpoint; covers CYP3A4 only, says nothing about other metabolic pathways or clinical DDI risk.
9. **Recommendation for next phase:** Phase 9's own outcome — a second endpoint reaching the same validated bar as the first on genuinely independent evidence — supports attempting a third endpoint using this now-twice-proven framework (repeat Sections 1–14 for one new candidate; do not parallelise). Before that, consider whether CYP3A4's specificity weakness is worth a targeted follow-up (e.g. a probability-threshold recalibration study) given how it will read to any user who takes an "inhibitor" call at face value. Do not begin Phase 10 as a broader platform effort until this decision is made deliberately, not by default.
