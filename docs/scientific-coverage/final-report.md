# Scientific Coverage Upgrade — Final Report

**Date:** 2026-09-09 · **Endpoint focus:** hERG inhibition (with CYP3A4
included in identity coverage) · **Models changed: none.**

Reports against the ten items the brief asks for at completion.

---

## 1. Identity coverage before / after

| | Before | After |
|---|---|---|
| Resolution tiers | exact full-InChIKey only | exact → **unambiguous skeleton** → unidentified |
| Public ChEMBL hERG (n=9,589) | 3.57% | **3.73%** |
| Public ChEMBL CYP3A4 (n=5,344) | 4.21% | **4.53%** |

**The gain is +0.16 / +0.32 percentage points. It is not a fix**, and the
coverage report says so in those words. ~96% of independent public compounds
remain unidentifiable, because the reference set is seeded from compounds
named in DrugSim's *own hERG/CYP3A4 assay files*; a drug in neither assay is
absent regardless of matching quality. Doxorubicin is the worked example.

Measured *before* implementing, not after — which is why the skeleton tier
shipped with hard limits rather than as a claimed solution.

## 2. External performance before / after

**Unchanged — by design.** No model, weight or threshold was modified. What
changed is that it is now measured properly.

| Metric | Internal test (n=800) | External (n=3,956) |
|---|---|---|
| Positive fraction | 0.611 | 0.094 |
| Precision | 0.694 | 0.218 |
| Specificity | 0.373 | **0.682** |
| ROC-AUC | 0.784 | **0.865** |
| MCC | 0.335 | 0.327 |

The reviewer's premise does not survive measurement. **Specificity is nearly
double externally, ROC-AUC is higher, and MCC is unchanged.** Precision falls
because the base rate falls from 61% to 9.4% — arithmetic, not degradation.

## 3. Main failure modes

**One dominant systematic mode:** over-calling "blocker" on chemically novel,
low-prevalence populations. At the production threshold, external errors run
**1,139 false positives to 52 false negatives** (22:1). 89% of external
compounds sit in the `chemically_novel` or `out_of_domain` tiers, which supply
almost all false positives.

Individual "most important" false positives are deliberately **not** listed:
with a single well-understood mode, per-compound storytelling would add
narrative confidence without adding evidence.

## 4. Applicability-domain findings

**The AD mechanism works, and an earlier conclusion was too pessimistic.**

Phase 4.5 judged it *"PARTIALLY supported, not cleanly monotonic"* using
ROC-AUC. ROC-AUC is prevalence-insensitive, and these tiers range from 44% to
1% positive — the wrong instrument. With prevalence-aware metrics:

| Tier | n | PR-AUC | MCC |
|---|---|---|---|
| highly_similar | 48 | **0.825** | 0.405 |
| moderately_similar | 425 | **0.663** | 0.450 |
| chemically_novel | 2,592 | **0.404** | 0.298 |
| out_of_domain | 891 | **0.131** | **0.085** |

PR-AUC is perfectly monotonic; MCC collapses to 0.085 out-of-domain — near-
worthless discrimination, exactly as the AD claims. **Recommendation: keep the
mechanism, do not re-tune it, and update Phase 4.5's stated conclusion.**

## 5. Data gaps discovered

- **G1 — reference-identity scope.** Real, large, and *purely* a reference-data
  gap: it cannot improve model accuracy by one compound.
- **G2 — external-validation breadth.** The `highly_similar` tier rests on 48
  compounds; a measurement-confidence gap, not a capability gap.

## 6. New data sources actually justified

**One, conditionally: a broader named-compound dictionary for G1**, ingested
offline through the existing build script, subject to a `registry.yaml` entry,
licence tiering and `make audit` clearance, plus a load-time/memory check
against the 512MB service ceiling.

**Explicitly rejected:** more hERG training data (the model already ranks
external compounds better than internal ones); UniProt/PDB/AlphaFold (no
measured failure mode implicates target-structure information); transporter/PK
data (supports new endpoints, excluded from this task).

## 7. Prediction-history improvements

Conformal p-values already existed, were already API-exposed, and were already
rendered on the live prediction view — so reviewer point (4) was a *plumbing*
gap, not a statistical one. History now retains and displays, behind a
disclosure: the conformal prediction set, singleton status, nominal
confidence, both p-values, the named uncertainty method, and the predicted
probability — with plain-language text stating that a low p-value is evidence
*against* a label and that it is **not** a significance test and carries no
clinical meaning.

The `statistics` field is optional, so rows saved before this change render
without it rather than being discarded or back-filled with invented values.
History remains **client-side `localStorage` only**, preserving the existing
privacy design; no server-side per-user storage was added.

## 8. Tests

| Suite | Result |
|---|---|
| Backend `tests/unit` + `tests/security` | **693 passed**, 1 failed, 11 errors |
| New `tests/unit/test_identity_resolution_tiers.py` | 12 passed |
| Frontend (vitest, 21 files) | **179 passed**, 0 failed |
| Frontend typecheck (`tsc -b`) | clean |

**"All tests pass" would be false, so it is not claimed.** The 1 failure and
11 errors are **pre-existing and unrelated**, verified by confirming neither
file imports any modified module:

- `test_registry_sync.py::test_mixed_spdx_skips_tier_cross_check` — a BindingDB
  `mixed` licence-tier resolution defect in registry data.
- 11 `test_landing.py` errors — boto3/MinIO connectivity; no MinIO running
  locally.

One existing test *did* break during this work — `HistoryPage` began matching
two elements for the same label text. It was fixed by changing **my new UI** to
render raw conformal class labels instead of duplicating humanised prose. The
existing test was not modified or weakened.

Database constraint tests were **not** run. `CHANGELOG.md:197` still claims
they cannot be, citing missing Docker; **Docker is now installed**, so that
line is stale and the tests are now runnable. Flagged, not fixed.

## 9. Was any model changed?

**No.** No training, retraining, re-thresholding, weight edit or registry
promotion. `SERVABLE_STATUSES` untouched. The four `EXPERIMENTAL` endpoints
remain unservable. The 0.5 decision threshold is unchanged — and is now
*documented as a deliberate recall-favouring choice appropriate to a cardiac-
safety endpoint*, rather than left looking like an unexamined default.

The threshold sweep shows MCC would peak at 0.70. **We recommend against it:**
it triples false negatives (52 → 158) on a safety endpoint in exchange for a
better-looking precision figure.

## 10. Was measurable performance improvement demonstrated?

**No, and none was attempted.**

Identity coverage improved by +0.16/+0.32 pp — real, measured, and far too
small to describe as solving reviewer point (1). **Model performance did not
improve, was not expected to, and was not targeted.**

What improved is understanding: the external "generalisation failure" is a
base-rate/threshold artifact rather than model degradation; the applicability
domain is better-validated than previously concluded; and the identity gap is
now correctly attributed to reference-set scope instead of matching quality.

Per the brief's own definition of success — *"DrugSim understands its data
coverage better, identifies compounds more reliably, explains its limitations
more clearly, and has a scientifically justified path to improving external
generalisation"* — that is the outcome. "DrugSim now has more data" is not
claimed, because it does not.

---

## Work not completed in this pass

Stated plainly rather than left implied:

- **Sections 15–17** (dataset/model transparency pages, and the audit of
  "more data improves accuracy" website copy) — not done.
- **Section 18** benchmark-reproducibility metadata — recorded for the two new
  analyses; existing benchmarks not retrofitted.
- **CYP3A4** received identity-coverage measurement only; the external
  generalisation and AD analysis covers hERG alone.
- Constraint tests not executed (see §8).
