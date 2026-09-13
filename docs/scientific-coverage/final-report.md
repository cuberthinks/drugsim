# Scientific Coverage Upgrade — Final Report

**Date:** 2026-09-09, updated 2026-09-10 · **Endpoint focus:** hERG and
CYP3A4 inhibition (both now have full external-generalisation + AD analysis;
identity coverage covers both) · **Models changed: none.**

Reports against the ten items the brief asks for at completion.

> **2026-09-10 update:** this report originally covered hERG only. A same-day
> follow-up commit (`9945167`) extended the external-generalisation and
> applicability-domain analysis to CYP3A4, ran the database constraint suite
> for the first time (75 passed), and completed the Section 17/18 audits this
> report had listed as "not done." This version reconciles those changes —
> see the updated tables below and the corrected "Work not completed"
> section. A second follow-up (this pass) added a compound-level
> false-positive/false-negative sample (Section 9) and dataset-transparency
> page fields (Section 15), both genuinely absent before now.

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
changed is that it is now measured properly, on both production endpoints.

| Metric | hERG internal (n=800) | hERG external (n=3,956) | CYP3A4 internal (n=459) | CYP3A4 external (n=12,161) |
|---|---|---|---|---|
| Positive fraction | 0.611 | 0.094 | 0.667 | 0.419 |
| Precision | 0.694 | 0.218 | 0.751 | 0.595 |
| Specificity | 0.373 | **0.682** | 0.405 | **0.612** |
| ROC-AUC | 0.784 | **0.865** | 0.800 | 0.776 |
| MCC | 0.335 | 0.327 | 0.356 | **0.401** |

The reviewer's premise does not survive measurement on either endpoint.
**Specificity is higher externally on both**, hERG's MCC is unchanged and
CYP3A4's is *higher* externally, and hERG's ROC-AUC is higher (CYP3A4's is
flat). Precision falls on both because the base rate falls — hERG's by 85%
(0.611→0.094, precision falls 69%), CYP3A4's by a smaller 37%
(0.667→0.419, precision falls 21%). **Precision loss scales with base-rate
loss across two independent endpoints and two independent external sources
(PubChem qHTS, TDC/PubChem qHTS)** — the signature of a base-rate effect, not
a model failing to generalise.

## 3. Main failure modes

**One dominant systematic mode on both endpoints:** over-calling the positive
class on chemically novel, lower-prevalence populations. hERG's external
errors run **1,139 false positives to 52 false negatives** (22:1); CYP3A4's
run 2,747:1,056 (2.6:1) — smaller because CYP3A4's prevalence shift is
smaller. In both cases the great majority of external compounds sit in the
`chemically_novel` or `out_of_domain` tiers, which supply almost all false
positives.

A curated "most important individual false positives" list is still not
provided, and for the same reason as before: with a single well-understood
systematic mode, hand-picking compounds would add narrative confidence
without adding evidence. What the brief's Section 9 asks for instead — a
compound-level record with AD status, chemical distance, dataset, model
version, and an explanation — **is now provided as a fixed-seed random
sample** (not a curated "worst offenders" list) in
`scripts/scientific_coverage/04_compound_level_errors_report.json`, 15 false
positives and 15 false negatives per endpoint. Every row carries the same
explanation because only one systematic mode has been found; assigning
different explanations per row without new evidence would itself be a
fabrication.

## 4. Applicability-domain findings

**The AD mechanism works on both production endpoints, and an earlier
conclusion was too pessimistic.**

Phase 4.5 judged it *"PARTIALLY supported, not cleanly monotonic"* using
ROC-AUC. ROC-AUC is prevalence-insensitive, and these tiers range from 44% to
1% positive — the wrong instrument. With prevalence-aware metrics:

**hERG**

| Tier | n | PR-AUC | MCC |
|---|---|---|---|
| highly_similar | 48 | **0.825** | 0.405 |
| moderately_similar | 425 | **0.663** | 0.450 |
| chemically_novel | 2,592 | **0.404** | 0.298 |
| out_of_domain | 891 | **0.131** | **0.085** |

**CYP3A4**

| Tier | n | PR-AUC | MCC |
|---|---|---|---|
| highly_similar | 27 | **0.956** | 0.574 |
| moderately_similar | 675 | **0.767** | 0.416 |
| chemically_novel | 10,660 | **0.719** | 0.399 |
| out_of_domain | 799 | **0.285** | **0.180** |

PR-AUC is monotonic on both endpoints; MCC collapses toward the out-of-domain
tier on both (0.085 for hERG, 0.180 for CYP3A4) — markedly weaker
discrimination, exactly as the AD claims. Confirming this on a second,
independent endpoint and a second, independent external source rules out
the result being an artifact of one dataset. **Recommendation: keep the
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

Database constraint tests were run for the first time in the 2026-09-09
follow-up commit: **75 passed.** `CHANGELOG.md`'s note that they could not be
run (missing Docker) is now itself stale and superseded by the CHANGELOG's
own later "Verified — database constraint tests finally executed" entry.

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

## Work not completed, as of this update (2026-09-10)

Stated plainly rather than left implied. This section itself has already
needed two corrections (see the update note at the top) — treat it as
accurate as of this file's own last-edit date, not as a permanent record.

- **Sections 15–17 — corrected.** Section 17 (audit of "more data improves
  accuracy" website copy) was completed 2026-09-09: swept, no unsupported
  claim found, none added or removed — recorded in `CHANGELOG.md`. Section 15
  (dataset-transparency page) was genuinely incomplete until this pass —
  `SourcesPage.tsx` had no per-endpoint train/val/test sizes or split
  methodology — now added; see `docs/scientific-coverage/README.md`'s
  "Dataset transparency" section for what changed and where. Section 16
  (model transparency) was already satisfied by the existing
  `models/registry/*.json` structure, predating this workstream.
- **Section 18** benchmark-reproducibility metadata — recorded for the two new
  analyses at the time; **existing production benchmarks were retrofitted**
  the same day (`frontend/src/lib/benchmarks.ts`: `randomSeed`,
  `preprocessing` version block) — see `CHANGELOG.md`.
- **CYP3A4 — corrected.** Originally received identity-coverage measurement
  only. A same-day follow-up (`03_cyp3a4_external_generalisation.py`)
  extended the external-generalisation and AD analysis to CYP3A4 and
  independently reproduced the hERG finding (Sections 2–4 above).
- **Constraint tests — corrected.** Run the same day: 75 passed (see §8).
- **Section 9 (compound-level error record) — completed this pass.** See §3
  above and `04_compound_level_errors_report.json`.
- **Still not done:** a broader identity name-dictionary for gap G1 (proposed,
  not built — see `data-gap-analysis.md`); Section 11's controlled-
  augmentation protocol has not been exercised for any *new* dataset (the
  separate `drugsim_curation`/curated-retraining work satisfies its
  mechanics incidentally, but was not scoped as part of this brief and is not
  claimed as such here).
