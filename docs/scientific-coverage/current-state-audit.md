# Current-State Audit — Scientific Coverage & Generalisation

**Date:** 2026-09-09
**Scope:** compound identity, external generalisation, applicability domain,
prediction history, dataset/model transparency.
**Status of this document:** audit only. No model was trained, retrained or
modified while producing it. Every number below was read from a committed
artifact or computed by a script in `scripts/scientific_coverage/`.

This audit exists because external reviewers with biomedical/drug-discovery
experience raised four points:

1. rare/known compounds are not always identified;
2. external (non-training-data) precision/specificity is relatively low;
3. datasets, models, validation and limitations should be more transparent;
4. prediction history should expose statistical/reliability information.

Each is treated below as a claim to be checked, not a fact to be accepted.

---

## 1. Current architecture

### 1.1 Compound identity

| Concern | Where | Behaviour |
|---|---|---|
| Standardisation | `src/drugsim_chem/standardize.py` | Fragment classification, salt stripping to a parent structure, mixture detection (`is_mixture`) |
| Identifiers | `src/drugsim_chem/identity.py` | Canonical/isomeric SMILES, InChI, **`inchikey_full` (27 char)** and **`inchikey_skeleton` (first 14)**, Bemis–Murcko scaffold |
| Reference data | `src/drugsim_identity/data/compound_identity_snapshot.json` | **960 compounds**, 952 distinct skeletons |
| Resolution | `src/drugsim_identity/snapshot.py::resolve_identity` | **Exact `inchikey_full` dict lookup, and nothing else** |
| Snapshot build | `scripts/build_compound_identity_snapshot.py` | Offline, from `datasets/golden/compounds.csv` (drug rows) + `seed_compounds.yaml`, enriched via PubChem **at build time only** |
| Serving | `src/drugsim_predict/pipeline.py:218` | Loaded once per process, then a pure in-memory lookup |
| UI | `frontend/src/components/CompoundIdentity.tsx` | Renders identity separately from prediction; "Unidentified" is a normal outcome |

**Privacy posture is already correct here and must not regress.** PubChem is
called only by the offline build script. The live `/predict` path performs no
external lookup, so a customer's novel structure is never transmitted to a
third party. This satisfies engineering principle 11 (customer structures are
confidential IP) *by construction*, not by policy.

### 1.2 Prediction, uncertainty, applicability domain

| Concern | Where | Behaviour |
|---|---|---|
| Promotion gate | `src/drugsim_predict/pipeline.py:46` | `SERVABLE_STATUSES = {"VALIDATED FOR INTERNAL RESEARCH"}` — `EXPERIMENTAL` models load but are refused at serve time |
| Uncertainty | `src/drugsim_predict/conformal.py` | Split conformal; returns a prediction **set**, `nominal_confidence`, `is_singleton`, and **`p_value_blocker` / `p_value_non_blocker`** |
| Applicability domain | `src/drugsim_predict/applicability_domain.py` | `METHOD_NAME = "tanimoto_knn_distance_scaffold_membership"` (3-signal, with a 2-signal supplementary verdict) |
| History | `frontend/src/lib/history.ts` | **Client-side `localStorage` only**, max 50 entries |
| Audit store | `src/drugsim_predict/store.py` | SQLite; persists `response_json` keyed by an API-key hash |

**Conformal p-values already exist and are already scientifically defined.**
This matters for reviewer point (4): split conformal prediction *does* define a
per-class p-value, so exposing one is legitimate rather than statistical
theatre. They are already computed, already returned by the API
(`schemas.py:181`, `api.py:198`), already typed in the frontend
(`api/types.ts:80`), and already rendered in `UncertaintyPanel.tsx`.

---

## 2. Existing strengths (must not regress)

- **Identity is already independent of prediction.** A valid compound outside
  the snapshot resolves as `unidentified` and *still predicts*. The brief's
  Section 3 requirement is already met; the audit's job is to keep it met.
- **No live external lookup in the request path** (see 1.1).
- **No fabricated descriptions.** `resolve_identity` substitutes the literal
  string `"Verified description unavailable."` rather than generating text.
- **Promotion gate is real**, and was respected when four new `EXPERIMENTAL`
  endpoints (DRD2, HRH1, CYP2D6, BBB) were added — none is servable.
- **Prevalence confounding is already understood.** Phase 4.5's own report
  carries a `confound_warning` explaining that raw accuracy is not comparable
  across similarity tiers because positive fraction moves 64% → 1%.
- **Honest negative results are already published**, including an erratum
  where CYP2D6 had been wrongly rejected using the muscarinic M5 target ID
  (CHEMBL2035 instead of CHEMBL289).

---

## 3. Weaknesses found

### W1 — Reference coverage is the real cause of reviewer point (1), and the obvious fix does not work

Measured by `scripts/scientific_coverage/02_identity_coverage.py` against
**independent public ChEMBL compounds** (not the snapshot's seed list):

| Stratum | n | Exact InChIKey | Unresolved |
|---|---|---|---|
| Public ChEMBL — hERG set | 9,589 | **3.57%** | **96.26%** |
| Public ChEMBL — CYP3A4 set | 5,344 | **4.21%** | **95.42%** |
| Golden drug rows (*build input, upper bound only*) | 5 | 80% | 20% |

The obvious fix — adding an InChIKey-**skeleton** tier, using the
`inchikey_skeleton` field that already exists but is unused — was measured
before being implemented:

- **coverage gain: +0.16% (hERG), +0.32% (CYP3A4).** Negligible.
- **7 of 952 snapshot skeletons are ambiguous**, each mapping to 2–3 distinct
  full InChIKeys. Every observed collision is a stereochemistry pair (e.g.
  `XEEQGYMUWCZPDN` → three stereo forms). Enantiomers can differ sharply in
  pharmacology, so a skeleton match is **not** proof of identity.

**Conclusion:** the coverage problem is not a matching-algorithm problem. It is
that the reference snapshot contains 960 compounds while the space users can
ask about is orders of magnitude larger. A skeleton tier is a marginal,
*safe-if-ambiguity-is-refused* addition, and must not be sold as the fix.

### W2 — Per-tier precision/specificity on external data has never been reported

Phase 4.5 reports accuracy, balanced accuracy and ROC-AUC per similarity tier.
It does **not** report precision, specificity, recall, MCC or PR-AUC per tier —
which is exactly the metric family reviewer point (2) is about. Ranking quality
and thresholded quality are different questions, and only the first is
currently answered per tier. Quantified in
`scripts/scientific_coverage/01_external_generalisation.py`.

The known headline symptom: hERG external ROC-AUC is **0.8696** (good ranking)
while external precision is **0.22** — a fixed 0.5 decision threshold meeting a
distribution whose positive rate is ~10% instead of training's ~66%.

### W3 — Prediction history drops the statistics it already has

`HistoryEntry` (`frontend/src/lib/history.ts`) stores prediction, reliability
rating, AD verdict, model id/version and timestamp. It does **not** retain
uncertainty, the conformal set, or the p-values — even though all are present
in the response object it is constructed from, and already displayed on the
live prediction view. There is also no way to reopen a past prediction in full.

This is reviewer point (4), and it is a *plumbing* gap, not a statistical one.

### W4 — `CHANGELOG.md:197` is stale

It states the 67 database constraint tests "have not been executed... require
Docker". Docker is now installed on the development machine. The blocker
described no longer exists.

---

## 4. Affected files / modules

| Change | Files |
|---|---|
| Identity resolution tier | `src/drugsim_identity/snapshot.py`, `src/drugsim_predict/pipeline.py` |
| Identity result shape | `src/drugsim_predict/schemas.py`, `frontend/src/api/types.ts`, `frontend/src/components/CompoundIdentity.tsx` |
| History statistics | `frontend/src/lib/history.ts`, `frontend/src/pages/HistoryPage.tsx` |
| Transparency copy | `frontend/src/pages/MethodologyPage.tsx`, `SourcesPage.tsx`, `HomePage.tsx` |
| Analyses (new) | `scripts/scientific_coverage/` |
| Documentation (new) | `docs/scientific-coverage/` |

---

## 5. Proposed changes (evidence-gated)

1. **Add a skeleton tier that refuses ambiguity.** Return a distinct
   `match_type` (`exact` vs `skeleton`) and never collapse the two. Justified
   as a small, safe gain — explicitly *not* as a fix for W1.
2. **Publish the per-tier external precision/specificity/PR-AUC** that W2
   identifies as missing, plus a threshold-sensitivity sweep showing how much
   of the precision collapse is threshold-vs-prevalence rather than model
   quality.
3. **Carry uncertainty and p-values into history**, and allow reopening a full
   past prediction. Client-side only, preserving the existing privacy design.
4. **Document the reference-vs-training distinction** so "expand the reference
   snapshot" is never mistaken for "the ADMET model will improve".

---

## 6. What must remain unchanged

- The hERG and CYP3A4 **model weights and thresholds** — no retraining to
  chase a metric.
- **No live external lookup** in the request path.
- The **promotion gate** (`SERVABLE_STATUSES`).
- **Client-side-only history** — server-side history would require
  multi-tenant auth that does not exist.
- Existing tests. Nothing deleted or weakened.
- The rule that an unidentified compound is still predictable.
