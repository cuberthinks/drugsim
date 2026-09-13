# Data Gap Analysis

**Date:** 2026-09-09
**Method:** start from measured failure modes, then ask what data would fix
them. Sources are proposed only where a specific, measured gap justifies one.

The brief's instruction is explicit: do **not** answer this with "add UniProt,
PDB and AlphaFold." Nothing below is recommended because it is well known.

---

## 0. The central finding, stated first

**The hERG model's external failure mode is not a missing-data problem.**

From `external-generalisation.md`: on 3,956 independent PubChem compounds the
model achieves ROC-AUC **0.865** — *higher* than its own internal test set
(0.784) — with MCC essentially unchanged (0.327 vs 0.335) and specificity
nearly double (0.682 vs 0.373). The low precision (0.218) is a base-rate
consequence of screening a 9.4%-positive population with a threshold chosen
for a 61%-positive one.

**More hERG training data would not fix an operating-point mismatch.** Any
proposal to ingest more data to "improve external precision" should be
rejected on this evidence.

This is where the reference-vs-training distinction (Section 12) does real
work: the **identity** gap is genuinely a data gap, and the **model** gap is
not.

---

## 1. Gaps that are real, ranked by measured impact

### G1 — Reference-identity scope *(reference data; does NOT affect model accuracy)*

| | |
|---|---|
| **Problem it solves** | ~96% of independent public compounds cannot be named (3.57% hERG / 4.21% CYP3A4 exact-match coverage). Doxorubicin, a very common drug, is unidentifiable. |
| **Why it exists** | The snapshot is seeded from compounds carrying `molecule_pref_name` in DrugSim's *own hERG/CYP3A4 assay files*. A drug in neither assay is structurally absent. |
| **Labels or context?** | **Context only.** Names, synonyms, formulae, identifiers. Contributes zero training signal. |
| **Expected relevance** | High for reviewer point (1); **exactly zero** for model performance. |
| **Candidate source** | A named-compound dictionary broader than DrugSim's two assay files, ingested offline through the existing `build_compound_identity_snapshot.py`, which already fetches verified PubChem data rather than accepting hand-written identities. |
| **Licence** | Must be assessed per source before ingestion. PubChem content is largely public-domain, but a bulk name dictionary is a *new source* and needs a `datasets/registry.yaml` entry, a tier, and `make audit` clearance — it does not inherit the existing PubChem clearance automatically. |
| **Integration difficulty** | **Low.** No new runtime dependency, no live lookup, no change to the request path. The build script and snapshot format already exist; only the seed scope changes. |
| **Risk** | Snapshot size. 960 records load fine as an in-memory dict; a 100k-record snapshot needs a load-time and memory check before it ships, given the service already runs against a 512MB ceiling. |

### G2 — External-validation breadth at high similarity *(measurement confidence)*

| | |
|---|---|
| **Problem it solves** | The `highly_similar` external tier has only **48 compounds**. Tier-level precision (0.607) rests on a very small n, so the top of the AD gradient is the least precisely estimated part of it. |
| **Labels or context?** | Labels — but for **evaluation, not training**. |
| **Expected relevance** | Moderate. Tightens confidence in the AD gradient; changes no prediction. |
| **Candidate source** | A second independent hERG assay, treated exactly as AID 588834 was: held out, never trained on, exact-overlap excluded. |
| **Licence** | Per source; PubChem BioAssay is generally permissive. |
| **Integration difficulty** | Low–moderate; the external-validation harness already exists and is parameterised by CSV. |
| **Caveat** | Adding this to *training* would destroy its value as an independent test. It is only useful while it stays out. |

---

## 2. Gaps considered and rejected

| Proposal | Why rejected |
|---|---|
| More hERG training data to raise external precision | The model already ranks external compounds *better* than internal ones. Precision is prevalence-bound at a fixed threshold; more data does not move a base rate. |
| Target/structural context (UniProt, PDB, AlphaFold) | No measured failure mode points to missing target-structure information. The observed error is one systematic base-rate effect, not a chemistry-knowledge deficit. Recommending these would be exactly the reflex the brief warns against. |
| Transporter / PK datasets | Would support *new endpoints*, which this task explicitly excludes. Not a fix for any measured hERG or CYP3A4 failure. |
| Re-thresholding to 0.70 to "fix precision" | Not a data proposal, and rejected on safety grounds: it triples false negatives (52 → 158) on a cardiac-liability endpoint. See `external-generalisation.md` §2. |

---

## 3. Controlled augmentation protocol (Section 11)

Neither G1 nor G2 is a merge-and-retrain. If any dataset is later proposed for
**model training**, the brief's sequence is mandatory and unchanged: ingest
separately → curate → evaluate overlap → check endpoint compatibility →
measure label quality → assess licensing → build an *experimental* dataset
version → benchmark against the current model → promote only on evidence.

G1 does not enter this protocol at all: it is reference data, and it must
never be added to a training set. Doing so would convert an identity
improvement into silent training-set contamination.

**This protocol is not hypothetical — it already exists and has been
exercised**, though not for either gap above. `src/drugsim_curation/`
(`docs/data-curation/README.md`) implements exactly this sequence for hERG
and CYP3A4: `curate_measurements.py` → `prepare_features_curated.py` →
`train_curated.py` → `evaluate_curated.py` writes an
`experiments/curated_v1/cross_evaluation_report.json` that is compared
against, never substituted for, the production model — and neither curated
model has been promoted. That work was scoped separately from this brief and
is not claimed as satisfying it; it is cited here only as evidence the
protocol above is a real, working mechanism in this codebase, not a proposal.

## 4. Why there is no "external cache" identity tier

The brief's suggested resolution order includes a live "approved external
reference source/cache" tier between the internal snapshot and
"unidentified." **DrugSim's implementation does not have one, by design, not
by omission.** `src/drugsim_identity/snapshot.py::resolve_identity` only ever
reads the committed, offline `compound_identity_snapshot.json` — PubChem is
called exclusively by `scripts/build_compound_identity_snapshot.py`, an
operator-run batch job, never from the live `/predict` request path (see
`current-state-audit.md` §1.1). Adding a live external-lookup tier would
mean a customer's submitted structure could be transmitted to a third party
during prediction, which is exactly what DrugSim's existing, tested privacy
guarantee (`docs/privacy/confidentiality-audit.md` §8) forbids. The gap this
leaves — a structurally novel compound that PubChem *would* resolve but the
offline snapshot does not yet contain — is real, and is what G1 (above)
proposes to narrow through the existing offline build path, not a live
lookup.
