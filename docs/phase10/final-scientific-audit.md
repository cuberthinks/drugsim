# Phase 10 — Final Scientific Audit

Every figure below was re-read directly from the live registry files (`models/registry/herg_inhibition_v1.json`, `models/registry/cyp3a4_inhibition_v1.json`) and re-verified by loading and checksum-verifying both model bundles at audit time (`load_model_bundle(model_id=...)`, which hard-fails on any checksum mismatch) — not recalled from the Phase 3/4/9 reports without re-checking. Both loads succeeded with no integrity error.

Two endpoints are registered. Both are audited below. **Neither is downgraded or removed** — both independently meet the promotion bar already applied to them in their own phase.

---

## Endpoint 1: hERG inhibition

| Field | Value |
|---|---|
| Endpoint definition | Binary: label=1 (blocker) if aggregated IC50 ≤ 10,000 nM (10 µM), else label=0 (non-blocker). Threshold is a literature convention (1–30 µM range across published hERG QSAR studies), not a universal biological constant. |
| Target | ChEMBL CHEMBL240 — KCNH2/Kv11.1, *Homo sapiens*, target confidence 9 (direct single protein) |
| Dataset version | `v1` |
| Dataset size | 9,589 compounds (6,363 blocker / 3,226 non-blocker), from 17,097 raw ChEMBL activity records |
| Model version | `0.1.0` |
| Model checksum (SHA-256) | `8e885f43d22048b68612744fbc630b22723fa75ff3e2f30640966184f224e46e` — **re-verified at audit time** |
| Feature version | `feature_set_id = a3ee2afe06243a9c3eca4e1d3f74393e900c0961f915609ac29b07e4d9919b30` |
| Preprocessing version | `standardization_pipeline_version = v1`, `descriptor_spec_version = v1`, RDKit `2025.03.3` |
| Training-set size | 6,792 compounds (split groups 0–6) |
| Validation (scaffold-split test, n=800) | ROC-AUC 0.7875, PR-AUC 0.8446, balanced accuracy 0.6495, F1 0.7918. Benchmark random-split proxy: ROC-AUC 0.8488 (gap 0.0613, attributed to leakage the scaffold split correctly removes). |
| Leakage checks | Duplicate/scaffold/preprocessing/target leakage: PASS. Near-duplicate (15 pairs, 1.88% of test) and exact-feature-collision (3/800) reviewed and documented, not silently ignored. Y-scrambling: real model 0.8394 vs. scrambled mean 0.489 ± 0.043 — collapses to chance as required. |
| Applicability domain | 3-signal (Tanimoto + k-NN descriptor distance + scaffold-seen), with a 2-signal supplementary verdict since scaffold-seen is tautologically false on any scaffold-holdout test. 2-signal accuracy: in-domain 75.4% (n=500), borderline 66.9% (n=166), out-of-domain 58.2% (n=134) — monotonic. |
| Uncertainty methodology | Split conformal prediction, nonconformity = 1 − P(candidate class), calibrated on split group 7 (n=976, touched once). Nominal confidence 90%, empirical coverage 89.88% — within tolerance. Post-hoc calibration (Platt, isotonic) evaluated and found not to improve on raw `predict_proba`; raw is used. |
| External validation status | **Not performed for hERG** — TDC's own download endpoint was unreachable from the training environment at the time Phase 3/4 ran (documented in `evaluate.py`'s own docstring). This gap is real and disclosed, not hidden. |
| Known limitations | Single endpoint, computational estimate only, 10 µM threshold is a convention, no external validation performed, applicability domain's 3-signal `in_domain` verdict is structurally unreachable on a scaffold-holdout test set (by design of ADR-009, not a defect). |
| Promotion status | **VALIDATED FOR INTERNAL RESEARCH** |

---

## Endpoint 2: CYP3A4 inhibition

| Field | Value |
|---|---|
| Endpoint definition | Binary: label=1 (inhibitor) if aggregated IC50 ≤ 10,000 nM (10 µM), else label=0 (non-inhibitor). Same convention class as hERG's threshold, not a universal constant. |
| Target | ChEMBL CHEMBL340 — Cytochrome P450 3A4, *Homo sapiens*, single protein |
| Dataset version | `v1` |
| Dataset size | 5,344 compounds (3,579 inhibitor / 1,765 non-inhibitor), from 12,357 raw ChEMBL activity records |
| Model version | `0.1.0` |
| Model checksum (SHA-256) | `44070914744d4ac572d9cd17d3511f6629786eaf448592e52501f5597f98cfb4` — **re-verified at audit time** |
| Feature version | `feature_set_id = a3ee2afe06243a9c3eca4e1d3f74393e900c0961f915609ac29b07e4d9919b30` — identical to hERG's, correctly: it is a content-address over the *shared toolchain* (RDKit version, descriptor spec, standardisation pipeline), not a per-dataset identifier. Documented in the registry to pre-empt any appearance of error. |
| Preprocessing version | `standardization_pipeline_version = v1`, `descriptor_spec_version = v1`, RDKit `2025.3.3` — same toolchain as hERG |
| Training-set size | 3,767 compounds (split groups 0–6) |
| Validation (scaffold-split test, n=459) | ROC-AUC 0.7995 (95% bootstrap CI 0.7593–0.8382), PR-AUC 0.8922, balanced accuracy 0.6520, MCC 0.3564, sensitivity 0.8987, **specificity 0.4052 (weakest metric)**. Benchmark random-split proxy: ROC-AUC 0.8391 (gap 0.0396). Beats descriptor-only RF/LR and majority-class baselines by +0.0579 ROC-AUC. |
| Applicability domain | Same 3-signal/2-signal method as hERG (shared implementation, `drugsim_predict.applicability_domain`). 2-signal accuracy: in-domain 82.82% (n=262), borderline 69.89% (n=93), out-of-domain 52.88% (n=104) — monotonic. |
| Uncertainty methodology | Same split-conformal method as hERG, calibrated on its own split group 7 (n=514, independent salt `cyp3a4_inhibition_v1`). Nominal 90%, empirical coverage 89.76%. Confident (singleton) predictions 83.68% accurate vs. 56.14% for ambiguous ones — uncertainty demonstrably tracks error. |
| External validation status | **Performed** — TDC `CYP3A4_Veith` (PubChem AID 1851 qHTS screen), 12,152 genuinely disjoint compounds (0.19% overlap with training, checked by InChIKey). ROC-AUC 0.7758, balanced accuracy 0.7022 — consistent with internal test performance. Label-definition caveat documented (qHTS single-concentration screen vs. this model's aggregated dose-response IC50 threshold). |
| Known limitations | Specificity 0.4052 is a real, asymmetric over-calling of "inhibitor" — the clearest weakness of any endpoint in the system; 10 µM threshold is a convention; external validation used a differently-labelled dataset; covers CYP3A4 only, not other CYP isoforms or clinical DDI risk. |
| Promotion status | **VALIDATED FOR INTERNAL RESEARCH** |

---

## Cross-endpoint scientific comparison

Both endpoints are held to the *same* standard, not two different bars:

| | hERG | CYP3A4 |
|---|---|---|
| Scaffold-split test ROC-AUC | 0.7875 | 0.7995 |
| Scaffold-split test balanced accuracy | 0.6495 | 0.6520 |
| Conformal empirical coverage (target 90%) | 89.88% | 89.76% |
| External validation | Not performed (documented gap) | Performed, consistent with internal test |
| Applicability domain behaviour | Monotonic degradation confirmed | Monotonic degradation confirmed |

CYP3A4 is not a weaker model admitted on a lowered bar — on the platform's own historical metric (scaffold-split ROC-AUC), it is marginally *stronger* than the original hERG model, and unlike hERG it has a genuine external validation result. Its specificity weakness is a real, disclosed limitation, not evidence the promotion decision was wrong — hERG has its own disclosed gap (no external validation at all).

## Audit conclusion

Neither endpoint requires downgrading, removal, or re-promotion for v1.0. Both are `VALIDATED FOR INTERNAL RESEARCH` on evidence that was independently re-verified during this audit (fresh checksum verification, fresh registry read, no reliance on cached prior-phase claims). No endpoint in this system carries `EXPERIMENTAL` or `REJECTED` status at v1.0 — there is currently nothing that Phase 10 Sec 1's "must not be presented as fully validated" rule needs to suppress, but the mechanism that would suppress it (the promotion gate in `drugsim_predict.pipeline.run_inference`, raising `EndpointNotAvailableError` for any non-`VALIDATED` status) was verified live and by automated test during Phase 9 and re-confirmed here — see Section "API and pipeline gate" in `docs/phase10/DRUGSIM_V1_FINAL_REPORT.md`.
