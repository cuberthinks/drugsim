# Benchmark Dataset Registry

Field-by-field citation trail for every number in
`frontend/src/lib/benchmarks.ts`. If a number on `/benchmarks` looks wrong,
this is where to check it against the original source.

## hERG (KCNH2/Kv11.1) inhibition

| Field | Value | Source |
|---|---|---|
| `benchmark_id` | `herg_inhibition_v1_scaffold_split` | — |
| `dataset` | ChEMBL, target CHEMBL240, IC50 activities | `models/admet/herg_inhibition/fetch_chembl_data.py` |
| `dataset_version` | v1 | `models/registry/herg_inhibition_v1.json` |
| `n_total` (final compound count) | 9,589 | `models/admet/herg_inhibition/phase4/02_validate_endpoint_report.json` |
| `n_test` (scaffold split) | 800 | `models/admet/herg_inhibition/evaluation_report.json` → `global_split.n_test` |
| `split_method` | Scaffold (ADR-009), split_group 9 held out | same file → `global_split.description` |
| `model_version` | 0.1.0 | `models/registry/herg_inhibition_v1.json` |
| `evaluation_date` | 2026-08-09 | `evaluation_report.json` → `generated_at` |
| ROC-AUC (scaffold split) | 0.7875 | `evaluation_report.json` → `global_split.roc_auc` |
| Balanced accuracy | 0.6495 | same file → `global_split.balanced_accuracy` |
| F1 / precision / recall | 0.7918 / 0.7008 / 0.91 | same file → `global_split.{f1,precision,recall}` |
| Confusion matrix | tn 121, fp 190, fn 44, tp 445 | same file → `global_split.confusion_matrix` |
| Random-split ablation, ROC-AUC gap | 0.8488, gap 0.0613 | same file → `benchmark_split`, `roc_auc_gap` |
| Baselines (majority/random/descriptor-only) | see page | `models/admet/herg_inhibition/phase4/08_baseline_comparison_report.json` |
| External validation dataset | PubChem AID 588834 (NCATS qHTS) | `models/admet/herg_inhibition/phase4/04_external_validation_report.json` → `external_source` |
| External validation metrics | n=3,919 (overlap excluded), ROC-AUC 0.8696 | same file → `performance.excluding_exact_training_overlap` |
| Applicability-domain tiers | 4 Tanimoto-range tiers | `models/admet/herg_inhibition/phase4/05_applicability_domain_report.json` → `tiers` |
| Calibration (Brier/ECE/coverage) | internal + external | `models/admet/herg_inhibition/phase4/06_uncertainty_calibration_report.json` |
| Licence | CC BY-SA 3.0 (ChEMBL, EMBL-EBI) | `datasets/registry.yaml` → `sources[chembl].license` |

## CYP3A4 metabolic inhibition

| Field | Value | Source |
|---|---|---|
| `benchmark_id` | `cyp3a4_inhibition_v1_scaffold_split` | — |
| `dataset` | ChEMBL, target CHEMBL340, IC50 activities | `models/admet/cyp3a4_inhibition/fetch_chembl_data.py` |
| `dataset_version` | v1 | `models/registry/cyp3a4_inhibition_v1.json` |
| `n_total` (final compound count) | 5,344 | `models/registry/cyp3a4_inhibition_v1.json` → `dataset.final_compound_count` |
| `n_test` (scaffold split) | 459 | `models/admet/cyp3a4_inhibition/evaluation_report.json` → `global_split.n_test` |
| `split_method` | Scaffold (ADR-009), split_group 9 held out | same file → `global_split.description` |
| `model_version` | 0.1.0 | `models/registry/cyp3a4_inhibition_v1.json` |
| `evaluation_date` | 2026-08-10 | `evaluation_report.json` → `generated_at` |
| ROC-AUC (scaffold split) | 0.7995, 95% CI [0.7593, 0.8382] | same file → `global_split.{roc_auc,confidence_interval_95pct}` |
| Balanced accuracy | 0.652 | same file → `global_split.balanced_accuracy` |
| F1 / precision / recall | 0.8185 / 0.7514 / 0.8987 | same file → `global_split.{f1,precision,recall}` |
| MCC / specificity | 0.3564 / 0.4052 | same file → `global_split.{matthews_corrcoef,specificity_recall_negative}` |
| Confusion matrix | tn 62, fp 91, fn 31, tp 275 | same file → `global_split.confusion_matrix` |
| Random-split ablation, ROC-AUC gap | 0.8391, gap 0.0396 | same file → `benchmark_split`, `roc_auc_gap` |
| Baselines (majority/logistic/RF-descriptors-only) | see page | `models/admet/cyp3a4_inhibition/baselines_report.json` |
| External validation dataset | TDC `CYP3A4_Veith` (PubChem AID 1851) | `models/admet/cyp3a4_inhibition/external_validation_report.json` → `external_dataset` |
| External validation metrics | n=12,152 (disjoint), ROC-AUC 0.7758 | same file → `metrics_on_disjoint_external_set` |
| Applicability-domain tiers | in-domain/borderline/out-of-domain, plain accuracy | `models/admet/cyp3a4_inhibition/reliability_report.json` → `applicability_domain.two_signal_accuracy_by_verdict` |
| Calibration (Brier/ECE/coverage) | `reliability_report.json` → `calibration`, `conformal_prediction.empirical_coverage` |
| Licence | CC BY-SA 3.0 (ChEMBL, EMBL-EBI) | `datasets/registry.yaml` → `sources[chembl].license` |

## Overall database scale (not either endpoint's training set)

| Field | Value | Source |
|---|---|---|
| Distinct compounds | 2,921,148 | `datasets/registry.yaml` → `sources[chembl].scale.distinct_compounds` |
| Bioactivity measurements | 24,527,044 | same → `scale.activities` |
| Assays | 1,970,438 | same → `scale.assays` |
| Targets | 18,552 | same → `scale.targets` |

These describe the ChEMBL release DrugSim's training data was drawn from —
**not** the size of either endpoint's own labelled training set (9,589 for
hERG, 5,344 for CYP3A4, both far smaller). The Benchmark page keeps these in
a visually and structurally separate section for exactly this reason.

## Endpoints considered and not built

The task that produced this page suggested checking DILI, Ames, aqueous
solubility, human intestinal absorption, bioavailability, Caco-2
permeability, BBB permeability, and half-life as benchmark candidates. None
of these has a live DrugSim model, so none appears on the Benchmark page.
Per `docs/phase9/endpoint-selection.md`, several TDC-sourced candidates in
this list (bioavailability, half-life, Caco-2, solubility, VDss, clearance,
LD50) were passed over specifically because TDC does not document units for
them — a real, disclosed reason, not an oversight. DILI and AMES were not
selected for Phase 9's endpoint expansion for reasons documented in that same
file. Nothing here should be read as "coming soon" — building a new endpoint
is a full validation undertaking (the same one hERG and CYP3A4 each went
through), not a page addition.

## Individual molecule explorer — ground truth citations

| Compound | Public ground truth | Citation |
|---|---|---|
| Aspirin | Non-blocker | No hERG signal reported in the pharmacovigilance literature. |
| Terfenadine | Blocker | Withdrawn from the US market in 1998 for hERG-mediated QT prolongation/torsades de pointes (Woosley RL et al., "Mechanism of the cardiotoxic actions of terfenadine," JAMA 1993;269(12):1532-6). |
| Dofetilide | Blocker | FDA-approved Class III antiarrhythmic; hERG (IKr) blockade is its labelled mechanism of action. |
| Paracetamol | Non-blocker | No hERG signal reported in the pharmacovigilance literature. |

Live predictions for all four were captured on 2026-08-24 against the
production API (`https://drugsim-predict-api.onrender.com/predict`). Values
will differ if the model is ever retrained — `evaluatedAt` on each entry in
`frontend/src/lib/benchmarks.ts` records exactly when these specific numbers
were captured, not a claim that they are permanent.
