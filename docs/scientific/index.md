# Scientific Status (v1.0)

This page summarises DrugSim's scientific status as of v1.0. It is a curated pointer, not a duplicate — every number here was re-verified from the live model registry during the Phase 10 audit; the full detail and methodology live in the linked reports.

## Endpoints

| | hERG inhibition | CYP3A4 inhibition |
|---|---|---|
| Category | Toxicity | Metabolism |
| Definition | label=1 if aggregated IC50 ≤ 10 µM | label=1 if aggregated IC50 ≤ 10 µM |
| Dataset size | 9,589 compounds | 5,344 compounds |
| Training-set size | 6,792 | 3,767 |
| Scaffold-split test ROC-AUC | 0.7875 | 0.7995 (95% CI 0.759–0.838) |
| External validation | Not performed (disclosed gap) | Performed — 12,152 disjoint TDC compounds, ROC-AUC 0.7758 |
| Weakest metric | — | Specificity 0.4052 (real, disclosed) |
| Promotion status | VALIDATED FOR INTERNAL RESEARCH | VALIDATED FOR INTERNAL RESEARCH |

Full endpoint-by-endpoint detail, including feature/preprocessing versions, checksums, applicability-domain and uncertainty methodology: [`../phase10/final-scientific-audit.md`](../phase10/final-scientific-audit.md).

## How validation was done

- hERG: [`phase3-model-validation-report.md`](../phase3/phase3-model-validation-report.md), [`phase3.5-scientific-audit.md`](../phase3/phase3.5-scientific-audit.md), [`phase4-reliability-report.md`](../phase4/phase4-reliability-report.md)
- CYP3A4: [`phase9-admet-expansion-report.md`](../phase9/phase9-admet-expansion-report.md)
- Both, re-verified together for release: [`phase10/final-scientific-audit.md`](../phase10/final-scientific-audit.md), [`phase10/DRUGSIM_V1_FINAL_REPORT.md`](../phase10/DRUGSIM_V1_FINAL_REPORT.md)

## Scientific rules this platform follows

- No endpoint is exposed as a normal prediction unless its registry status is exactly `VALIDATED FOR INTERNAL RESEARCH` — enforced in code (`drugsim_predict.pipeline.run_inference`'s promotion gate), not just by convention.
- Every prediction carries its own uncertainty (split conformal prediction) and applicability-domain assessment — never a bare label.
- Endpoints are never combined into a single "DrugSim score." Each is a separate, independently validated claim about a separate biological mechanism.
- DrugSim does not claim to predict exact human pharmacokinetics, clinical safety, patient outcomes, therapeutic efficacy, or complete ADMET behaviour. It is a collection of validated computational predictions for specific, narrowly defined endpoints — not a simulation of a whole organism.

See [`../legal/attribution-manifest.md`](../legal/attribution-manifest.md) for third-party dataset licensing and attribution.
