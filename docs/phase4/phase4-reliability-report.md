# Phase 4 Reliability Report — hERG Inhibition Model v0.1.0

**Final Decision: VALIDATED FOR INTERNAL RESEARCH** (scope and conditions below — not clinically validated, not production-ready, not a replacement for laboratory testing)

---

## Model

| | |
|---|---|
| Model ID / version | `herg_inhibition` v0.1.0 |
| Endpoint | hERG (KCNH2/Kv11.1) inhibition, binary blocker classification, IC50 ≤ 10 µM = blocker (threshold retained from Phase 3, re-examined and explicitly not changed by Phase 3.5) |
| Dataset | `herg_inhibition` v1, 9,589 compounds (6,363 blocker / 3,226 non-blocker), built from a complete 17,097-record ChEMBL pull (sha256 `098527c1...`) |
| Features | 18 physicochemical descriptors + Morgan/ECFP4 fingerprint (radius 2, 2048 bits, chirality-aware) = 2,066 columns |
| Algorithm | Random Forest (`n_estimators=500, max_depth=None, class_weight="balanced"`, seed 42), selected over Gradient Boosting and Logistic Regression on validation ROC-AUC |

---

## Reproducibility

Re-ran the full deterministic pipeline (`build_dataset → prepare_features → train → evaluate`) from the fixed, checksum-verified raw CSV — not a re-fetch, which would query a live, growing API. **Every output was byte-identical to the registered artifacts, including the `model.joblib` binary itself**, except the intentionally arbitrary `local_compound_id` surrogate key. No unexplained differences; nothing to investigate.

Environment: RDKit 2025.03.3 (pinned), numpy 1.26.4, scikit-learn 1.6.1, Python 3.9 (sandbox) — same toolchain as Phase 3.

---

## Validation

**Endpoint definition** — confirmed unchanged and consistent with Phase 3.5's explicit recommendation to retain 10 µM for this registered model. All six filtering rules verified identical.

**Scaffold-split performance** — held-out test (split_group 9, touched once): ROC-AUC 0.7875, balanced accuracy 0.6495, precision/recall 0.70/0.91.

**Repeated validation (10 seeds)**: test ROC-AUC 0.7895 ± 0.0015 (range 0.7875–0.7926) — very stable, governed almost entirely by RF's internal randomness. The registered value (0.7875) is exactly the minimum of the 10 runs — just outside the ±1 std band on the low side, but the entire range spans only 0.0051, so this is noise-floor variation, not a sign of an unstable estimate.

**Bootstrap perturbation (10× resampled training sets)**: 0.7694 ± 0.0095 — a larger spread, showing moderate (not negligible) sensitivity to exactly which compounds are trained on.

**Feature ablation**: descriptors-only 0.7266, fingerprints-only 0.7722, combined (registered) 0.7875 — both feature types contribute; combining them helps.

**Chemical diversity**: 5,079 distinct scaffolds / 9,589 compounds (ratio 0.53 — moderate diversity, a substantial fraction of the dataset sits in analogue series). Class balance is stable across all 10 split groups (0.59–0.71 positive fraction, std 0.037) — no pathological group-level skew from scaffold clustering.

**External validation** — PubChem AID 588834 (NCATS qHTS hERG inhibition screen), genuinely independent: different lab, assay technology, and data pipeline from ChEMBL; never touched before this evaluation (no influence on training, features, hyperparameters, threshold, or calibration). Overlap check: only 2.75% (111/4,030) of external compounds exactly match a training compound by InChIKey; no additional near-duplicates (Tanimoto ≥ 0.95) beyond those exact matches. Excluding overlap: **ROC-AUC 0.8696 — higher than the internal test set**, real evidence the ranking signal generalizes to an independent population. But the external set's prevalence is only ~9% positive (vs. ~66% training), and the model's fixed 0.5 threshold does not adapt to this: precision 0.22, recall 0.86 — many false positives in absolute terms, a prevalence-shift effect, not evidence of poor discrimination.

**Baseline comparison** (internal test set):

| | ROC-AUC | Balanced accuracy |
|---|---|---|
| Majority-class | n/a (constant) | 0.500 |
| Random (stratified) | 0.500 | 0.502 |
| Simple descriptor (LogP+MW+TPSA only) | 0.601 | 0.569 |
| **Registered model** | **0.7875** | **0.6495** |

Clear, substantial improvement over every baseline (+0.187 ROC-AUC over the simple-descriptor baseline).

---

## Reliability

**Applicability domain** — stratified a combined internal-test + external pool (4,756 compounds) by max-Tanimoto-to-training into four tiers. Raw accuracy is confounded by a sharp prevalence gradient across tiers (64%→42%→10%→1% positive, since the external pool dominates the low-similarity tiers); prevalence-corrected ROC-AUC by tier:

| Tier | Tanimoto range | n | ROC-AUC |
|---|---|---|---|
| Highly similar | ≥0.7 | 405 | 0.807 |
| Moderately similar | 0.4–0.7 | 760 | 0.819 |
| Chemically novel | 0.2–0.4 | 2,700 | **0.851** |
| Out-of-domain | <0.2 | 891 | **0.727** |

**Partial support**, not a clean gradient: out-of-domain is correctly the worst tier (consistent with the TDS's Tanimoto<0.4 OOD claim), but chemically-novel (also below 0.4) is unexpectedly the *best* tier. A single similarity threshold flags the single worst-performing group but does not track error smoothly across the full range.

**Uncertainty** — split conformal prediction, calibration group (split_group 7) used once, never refit. **Precision statement**: conformal coverage is a *marginal, population-level guarantee* — the true label falls in the predicted set at a target rate averaged over many predictions from an exchangeable population. It is **not** a per-instance probability that any single prediction is correct, and this report never describes it as one.

| | Internal test (cited from Phase 3) | External set (new, Phase 4) |
|---|---|---|
| Empirical coverage (90% nominal) | 89.88% | **91.96%** |
| Calibration (Brier / ECE) | 0.1864 / 0.0597 | 0.2014 / **0.3634** |

**Key finding**: conformal *set* coverage survived a real, substantial distribution shift (9% vs. 66% positive rate) — a genuinely reassuring, non-trivial result. Pointwise probability *calibration did not survive* the same shift (ECE 6× worse). **Practical consequence: raw predicted probabilities must not be treated as calibrated absolute risk outside conditions resembling the training population; they remain useful for ranking/triage.**

---

## Error Analysis

Internal test set, 800 compounds, 29.25% overall error rate.

**Dominant, quantified root cause: label fragility near the classification threshold.** 442 of 800 test compounds (55%) have a true aggregated IC50 within 3× of the 10 µM cutoff. Those near-threshold compounds have a **43.4% error rate vs. 11.7%** for compounds far from the boundary — a ~4× difference. Every one of the 10 largest, most-confident errors (predicted probability 0.88–0.99 for the wrong class) is a false positive with a true IC50 just above the cutoff (10,580–16,000 nM) **and** only a single source measurement. This attributes a large share of the model's apparent error to the inherent fragility of binarizing a continuous potency value near an arbitrary cutoff — not to a chemistry-understanding failure — consistent with Phase 3.5's finding that 47% of compounds change class between 1 µM and 10 µM.

**Ruled out**: measurement replication count is *not* a major error driver (single- vs. multi-measurement compounds: 29.1% vs. 30.4% error rate — no meaningful difference).

**Confirmed**: the model's own confidence tracks correctness — borderline predictions (0.4–0.6 probability) have roughly double the error rate of confident ones (45.5% vs. 23.5%).

**Chemical clustering**: several small scaffold groups (n=3–10 test compounds) show elevated error rates (up to 100%); sample sizes this small carry limited statistical weight and are reported as representative examples, not a general scaffold-family conclusion.

**Interpretability**: LogP dominates descriptor importance (0.029), followed by TPSA, molar refractivity, MW — consistent with well-established hERG QSAR literature linking lipophilic, basic structures to channel block. Fingerprint bits carry 81% of total importance vs. 19% for descriptors. *Feature importance reflects statistical usefulness for separating labels in this dataset, not evidence of mechanistic channel-binding causation.* A representative similarity example: two compounds sharing identical connectivity but opposite stereochemistry and opposite labels (Tanimoto 0.884 under the chirality-aware fingerprint) — a concrete illustration of exactly the stereo-sensitivity the Phase 3.5 fingerprint fix addressed.

---

## Limitations — what this model cannot reliably do

1. **Cannot provide calibrated absolute risk outside training-like conditions.** Confirmed empirically: ECE degrades 6× on a population with different class prevalence. Use for relative ranking/triage, not as a standalone calibrated probability, unless recalibrated for the target population.
2. **Cannot reliably classify compounds near the 10 µM potency boundary.** ~55% of typical hERG data sits within this fragile zone; treat borderline-probability (0.4–0.6) predictions as low-confidence and route to human/experimental review.
3. **Applicability domain flag is only a partial safeguard.** Its similarity-tiered performance is not a clean gradient; use it as one input alongside human judgement, not an automatic hard gate.
4. **Endpoint blends multiple assay paradigms** (Phase 3.5: ~25% binding-displacement, ~40% functional, ~33% ambiguous); 3.6% of training compounds have unflagged mixed-paradigm source data.
5. **Not integrated with DrugSim's real database schema** — model artifacts and provenance live in local files, not Postgres (tracked technical debt since Phase 2, unresolved).
6. **Not independently reviewed.** Single-pass analysis, no QMRF, no multi-reviewer sign-off.
7. **Conformal coverage is a population-level guarantee, never a per-instance correctness probability** — do not describe or use it as one.

---

## Final Decision

**VALIDATED FOR INTERNAL RESEARCH.**

Justification: reproducibility is exact; the model beats every baseline decisively; y-scrambling (Phase 3) and all leakage checks (Phase 3.5) remain valid; genuinely independent external validation shows the ranking signal transfers to, and even slightly exceeds, internal test performance; the primary uncertainty mechanism's core coverage guarantee survives a real distribution shift; and the dominant error mode is well-characterized, quantified, and attributable to inherent label fragility near an arbitrary threshold rather than incoherent model failure. This is a materially stronger evidentiary basis than Phase 3's EXPERIMENTAL classification rested on.

The promotion is **conditional and bounded**, not unconditional: it applies to controlled internal research use — relative compound ranking and triage within the documented applicability domain — and explicitly **not** to unsupervised absolute-risk scoring on populations unlike the training set, not to compounds flagged borderline or out-of-domain without human review, and not to any use implying clinical validation, production readiness, or replacement of laboratory hERG assays. The Phase 3.5 WARNINGs (assay-paradigm stratification, threshold reconsideration, database integration) remain open technical debt and should be prioritized in any future iteration.
