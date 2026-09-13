# External Generalisation, Applicability Domain & Threshold Sensitivity

**Endpoint:** hERG inhibition. **Date:** 2026-09-09.
**Produced by:** `scripts/scientific_coverage/01_external_generalisation.py`
**Raw output:** `scripts/scientific_coverage/01_external_generalisation_report.json`

**No model was trained, retrained, re-thresholded or modified.** This is
read-only analysis of the existing registered artifact against an existing
committed external dataset.

---

## 0. Headline finding

External reviewers reported "relatively low precision/specificity on
external/non-training data". The measurement does not support that as stated.

| Metric | Internal test (n=800) | External PubChem (n=3,956) |
|---|---|---|
| Positive fraction | 0.611 | **0.094** |
| Precision | 0.694 | **0.218** |
| Recall | 0.904 | 0.860 |
| **Specificity** | 0.373 | **0.682** |
| ROC-AUC | 0.784 | **0.865** |
| PR-AUC | 0.840 | 0.499 |
| **MCC** | **0.335** | **0.327** |

Three things follow, and they matter:

1. **Specificity is not low externally — it is nearly twice the internal
   value** (0.682 vs 0.373). The reviewer's "low specificity" impression does
   not survive measurement.
2. **Ranking quality is higher externally, not lower** (ROC-AUC 0.865 vs
   0.784). The model discriminates *better* on the independent assay.
3. **MCC is essentially unchanged** (0.327 vs 0.335). Threshold-aware
   agreement quality is the same on both sets.

**Precision falls because the base rate falls, not because the model
degrades.** Precision is `TP/(TP+FP)`; moving from a 61% positive population
to a 9.4% one forces precision down even for an identical, unchanged
classifier. A model whose MCC and ROC-AUC hold — and whose specificity
improves — has not generalised badly. It is being read at an operating point
chosen for a different prevalence.

This reframes the problem: **it is a deployment/threshold-communication issue,
not a model-quality issue**, and it should not be "fixed" by retraining.

---

## 1. Applicability domain — does it actually work?

Section 7 asks whether lower AD reliability genuinely correlates with higher
error. Stratifying **external compounds only** by max-Tanimoto to the training
set (tier boundaries identical to Phase 4.5, for comparability):

| Tier | n | Positive frac. | Precision | Recall | Specificity | ROC-AUC | **PR-AUC** | **MCC** |
|---|---|---|---|---|---|---|---|---|
| highly_similar (≥0.7) | 48 | 0.438 | 0.607 | 0.809 | 0.593 | 0.833 | **0.825** | **0.405** |
| moderately_similar (0.4–0.7) | 425 | 0.299 | 0.474 | 0.921 | 0.564 | 0.850 | **0.663** | **0.450** |
| chemically_novel (0.2–0.4) | 2,592 | 0.082 | 0.192 | 0.836 | 0.685 | 0.839 | **0.404** | **0.298** |
| out_of_domain (<0.2) | 891 | 0.010 | 0.024 | 0.667 | 0.719 | 0.705 | **0.131** | **0.085** |

### 1.1 This corrects an earlier conclusion

Phase 4.5 concluded the AD mechanism was **"PARTIALLY supported, not cleanly
monotonic"**, because it evaluated tiers by ROC-AUC — and ROC-AUC is indeed
non-monotonic here (0.833 → 0.850 → 0.839 → 0.705).

Evaluated with the prevalence-aware metrics that Phase 4.5 did not compute,
the picture is different:

- **PR-AUC is perfectly monotonic**: 0.825 → 0.663 → 0.404 → 0.131.
- **MCC collapses out-of-domain**: 0.405 / 0.450 / 0.298 → **0.085**.

An MCC of 0.085 is close to worthless discrimination. **The applicability
domain is doing its job**, and the earlier "not cleanly monotonic" verdict was
an artifact of using a prevalence-insensitive metric on tiers whose prevalence
varies from 44% to 1%. ROC-AUC was the wrong instrument for this question.

**Recommendation:** keep the AD mechanism; do not re-tune its thresholds
(there is no evidence they are miscalibrated). Update Phase 4.5's stated
conclusion to reference PR-AUC/MCC, and treat `out_of_domain` as a tier where
a positive call carries almost no evidential weight (precision 0.024).

### 1.2 Precision tracks base rate almost exactly

| Tier | Positive fraction | Precision | Ratio |
|---|---|---|---|
| highly_similar | 0.438 | 0.607 | 1.39× |
| moderately_similar | 0.299 | 0.474 | 1.59× |
| chemically_novel | 0.082 | 0.192 | 2.34× |
| out_of_domain | 0.010 | 0.024 | 2.40× |

Precision is consistently ~1.4–2.4× the tier's base rate. The model adds real
information at every tier (ratio > 1), but the *absolute* precision a user
experiences is dominated by how common blockers are in the population they are
screening. This is the single most useful thing to communicate to users, and
it is currently not communicated at all.

---

## 2. Threshold sensitivity (Section 8)

Swept on the external distribution (prevalence 0.094). **This is analysis, not
a change** — the production threshold remains 0.5.

| Threshold | Precision | Recall | Specificity | MCC | Balanced acc. | FN |
|---|---|---|---|---|---|---|
| 0.30 | 0.110 | 0.987 | 0.175 | 0.128 | 0.581 | 5 |
| 0.40 | 0.155 | 0.930 | 0.476 | 0.238 | 0.703 | 26 |
| **0.50 (production)** | 0.218 | 0.860 | 0.682 | 0.327 | 0.771 | 52 |
| 0.60 | 0.330 | 0.768 | 0.839 | 0.428 | **0.803** | 86 |
| 0.70 | 0.451 | 0.573 | 0.928 | **0.451** | 0.750 | 158 |
| 0.80 | 0.619 | 0.324 | 0.979 | 0.409 | 0.652 | 250 |
| 0.90 | 0.800 | 0.076 | 0.998 | 0.229 | 0.537 | 342 |

Raising the threshold to 0.70 would maximise MCC (0.451) and roughly double
precision (0.218 → 0.451).

**We are not recommending that.** hERG is a cardiac-safety liability endpoint.
The dangerous error is a **false negative** — telling a chemist a blocker is
safe. Moving 0.5 → 0.70 raises false negatives from 52 to 158, a 3× increase
in exactly the direction that can hurt someone, in exchange for a precision
number that looks better on a slide.

Per the brief: *"Do not select a threshold solely because it produces the best
internal metric."* The existing 0.5 threshold is **recall-favouring, and that
is the correct bias for a safety-screening endpoint.** It should be documented
as a deliberate, justified choice rather than left to look like an unexamined
default.

---

## 3. Error analysis (Section 9)

At the production threshold on external data: **1,139 false positives vs 52
false negatives** — a 22:1 asymmetry.

Systematic failure mode, stated plainly: **the model over-calls "blocker" on
chemically novel, low-prevalence populations.** This is one mode, not many —
it is the same base-rate/threshold interaction described above, observed
through a different lens. 2,592 of 3,956 external compounds (66%) sit in the
`chemically_novel` tier, and 891 (23%) are `out_of_domain`; together they
supply the overwhelming majority of false positives.

We deliberately do not present a list of individual "most important" false
positives. The brief warns against overinterpreting individual molecules, and
with a single dominant, well-understood systematic mode, per-compound
storytelling would add narrative confidence without adding evidence.

---

## 4. What this means for data (feeds Section 10)

The observed failure mode is **not** explained by missing chemistry knowledge
that more data would supply. The model ranks external compounds *better* than
internal ones (ROC-AUC 0.865 vs 0.784). Adding more hERG training data would
not obviously fix a problem that is fundamentally about operating point and
population prevalence.

The one genuine data-shaped gap: the `highly_similar` external tier has only
**48 compounds**, too few to estimate tier-level performance precisely. More
*independent external* data — not more training data — would tighten these
estimates. That is a measurement-confidence gap, not a model-capability gap.

---

## 5. Reproducibility (Section 18)

| Field | Value |
|---|---|
| Model artifact | `models/admet/herg_inhibition/artifact/model.joblib` |
| External source | PubChem AID 588834 (NCATS qHTS hERG screen) |
| External CSV | `datasets/raw/pubchem_aid588834_raw.csv` |
| Label rule | AC50 ≤ 10,000 nM = blocker (identical to training rule) |
| Overlap control | exact full-InChIKey training overlap excluded |
| Internal test | `split_group == 9`, n=800 |
| External n after exclusions | 3,956 |
| Tier boundaries | identical to Phase 4.5 |
| Decision threshold | 0.5 (production, unchanged) |
| Evaluation date | 2026-09-09 |

Internal and external sets are different populations with different
prevalence; every cross-set comparison above states that explicitly.
