# Compound-Identity Reference Coverage

**Date:** 2026-09-09
**Produced by:** `scripts/scientific_coverage/02_identity_coverage.py`
**Raw output:** `scripts/scientific_coverage/02_identity_coverage_report.json`

Public reference/ChEMBL compounds only. **No customer-submitted structure is
read, counted or reported here** (brief Section 19).

This measures *identity coverage only*. It says nothing about ADMET model
performance — reference data and training data are separate concerns
(Section 12), and expanding one does not improve the other.

---

## 1. What resolution does today

`drugsim_identity.resolve_identity` resolves against a committed offline
snapshot of **960 compounds spanning 952 distinct skeletons**.

The snapshot is seeded from:
- `datasets/golden/compounds.csv` (category `drug` rows), plus
- `src/drugsim_identity/data/seed_compounds.yaml`, plus
- **compounds carrying a `molecule_pref_name` in DrugSim's own raw ChEMBL
  hERG and CYP3A4 assay files.**

That third source supplies most of the 960, and it determines the ceiling
described below.

---

## 2. Measured coverage

| Stratum | n | Exact InChIKey | Skeleton (unambiguous) | Unresolved |
|---|---|---|---|---|
| **B — public ChEMBL, hERG set** *(independent)* | 9,589 | **3.57%** | +0.16% | **96.26%** |
| **C — public ChEMBL, CYP3A4 set** *(independent)* | 5,344 | **4.21%** | +0.32% | **95.42%** |
| A — golden drug rows *(build input; upper bound only)* | 5 | 80% | +0% | 20% |

Stratum A is **not an independent test** — those compounds are part of the
snapshot's own build input. It is reported as a sanity check, and is stated as
such rather than quietly presented alongside the real numbers.

**Reviewer point (1) is confirmed, and it is large:** ~96% of independent
public compounds cannot be named.

---

## 3. The obvious fix was measured before being adopted, and it is not the fix

The natural candidate is an InChIKey **skeleton** (first 14 characters) tier —
attractive because `inchikey_skeleton` is already computed on
`MolecularIdentity` and simply unused for resolution.

**Coverage gain: +0.16% (hERG), +0.32% (CYP3A4).** Negligible against a ~96%
gap.

**Collision risk is real.** 7 of 952 snapshot skeletons map to more than one
full InChIKey, and every observed collision is a stereoisomer set — e.g.
`XEEQGYMUWCZPDN` resolves to three distinct stereo forms. Enantiomers can
differ sharply in pharmacology, so a skeleton match is evidence of *shared
connectivity*, not proof of identity.

### What was implemented, and how it is bounded

The skeleton tier was added, because a small safe gain is still a gain — but
with two hard constraints:

1. **Ambiguity is refused, never resolved.** A skeleton mapping to >1 record
   returns `unidentified`. Naming the wrong enantiomer is worse than naming
   nothing.
2. **It is reported as a different kind of match.** Results carry
   `match_type` (`"exact"` | `"skeleton"`) and, for skeleton matches, a fixed
   reviewed `match_caveat` stating that stereochemistry, isotopic labelling
   and protonation were not confirmed. The two tiers are never merged into one
   "identified" claim.

Regression coverage: `tests/unit/test_identity_resolution_tiers.py`.

---

## 4. Why coverage is capped where it is

Salt handling is **already correct** and needs nothing: standardisation strips
the counter-ion before identity is resolved, so aspirin sodium salt and
aspirin produce the same InChIKey and the same exact match (verified in
`TestSaltEquivalence`).

The real ceiling is scope. ChEMBL sets `molecule_pref_name` only for compounds
it considers notable, and DrugSim only reads its **own hERG and CYP3A4 assay
files**. A drug that appears in neither assay is absent regardless of matching
quality.

**Worked example — doxorubicin.** A very widely used chemotherapy agent, and
currently **unidentified** by DrugSim. Not a resolution bug: it simply is not
a hERG or CYP3A4 assay compound in the ingested raw files. This is pinned by
`test_doxorubicin_documents_a_real_coverage_gap`, which is written to fail
loudly *if coverage is later broadened*, prompting an update to this document
rather than silent drift.

---

## 5. What would actually move coverage

Ranked by effect on the measured gap, not by ease:

1. **Broaden the reference seed beyond DrugSim's two assay files.** This is
   the only change that addresses a ~96% gap. It is a *reference-data* task:
   a licensed, named-compound dictionary, ingested offline through the
   existing build script, which already fetches verified PubChem data rather
   than accepting hand-written identities. Licensing must be assessed per
   source before ingestion (see `data-gap-analysis.md`).
2. Skeleton tier — **done**, worth +0.16–0.32%.
3. Better matching algorithms generally — **not worth pursuing.** The
   unresolved compounds are absent from the reference set, not mis-matched
   within it. No matching improvement can find a record that does not exist.

**This must not be described as improving prediction quality.** Naming more
compounds makes DrugSim more useful to read; it does not make the hERG or
CYP3A4 models more accurate by even one compound.
