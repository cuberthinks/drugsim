# DrugSim Focus Decision

**This is a strategic decision, not a validated market or scientific claim.**
It records which existing, evidenced capability DrugSim should lead with —
it does not assert that focus is commercially proven, and it changes
nothing about the running application, the API, or any model.

## Decision Record

- **Decision date**: 2026-08-27
- **Repository state**: `origin/main` at commit `2bd39f5` (post Phase 12 /
  changelog update)
- **Models considered**: `models/admet/herg_inhibition` (registry
  `herg_inhibition_v1`), `models/admet/cyp3a4_inhibition` (registry
  `cyp3a4_inhibition_v1`) — the only two trained, registered models in the
  repository
- **Datasets considered**: `datasets/processed/{herg,cyp3a4}_inhibition_*`
  (live training data), `datasets/curated/*` (Phase 11 output),
  `docs/phase9/endpoint-selection.md`'s candidate-sizing table (AMES, BBB,
  Pgp, CYP2D6, CYP2C9, DILI, bioavailability, solubility/Caco-2/VDss/
  half-life/clearance — sized but never built)
- **Evidence used**: `docs/phase1/step1-dataset-survey.md`,
  `docs/phase1/step12-scientific-roadmap.md`,
  `docs/phase9/endpoint-selection.md`,
  `docs/phase9/phase9-admet-expansion-report.md`,
  `docs/phase3/phase3-model-validation-report.md`, both endpoints'
  `models/admet/*/reliability.py`/`evaluate.py`/`external_validation*`
  reports, hERG's `phase4/` validation suite (9 scripts + reports),
  `docs/benchmarks/README.md` and `dataset-registry.md`, `docs/tds/
  01-overview-and-principles.md` and `10-risk-register.md`,
  `docs/README.md`, `docs/phase10/final-scientific-audit.md`. All figures
  below are quoted from these files; none are estimated or invented.

## Executive Summary

DrugSim has two live, independently validated endpoints — **hERG
inhibition** (cardiac safety) and **CYP3A4 inhibition** (metabolic
drug-drug-interaction risk) — and no real evidence (data, model, or
validation) for any other ADMET area. Between the two, **hERG has
materially deeper, more adversarial validation** (leakage checks,
y-scrambling, seed/bootstrap robustness, an independently-sourced
external validation set with its own calibration re-test, interpretability)
and the single strongest, most independently-corroborated number in the
repository (external ROC-AUC 0.8696, n=4,030, a source disjoint from
training). CYP3A4 is real and competitive but has not yet been put
through that same gauntlet. Every other candidate area (BBB, DILI, AMES,
solubility, oral absorption, etc.) was already evaluated for feasibility
in Phase 9 and either deferred (real data exists, nothing built yet) or
rejected (too small, or units unresolved) — none has a trained model or
validation evidence today.

**Recommended primary focus: early-stage cardiac liability (hERG-mediated
cardiotoxicity) screening for candidate small molecules**, because it is
where DrugSim's evidence is deepest and most convincing, not because
cardiac safety is inherently more important than metabolic safety.
CYP3A4 is the recommended secondary focus, on a clear path to parity once
its validation gap is closed.

## Current DrugSim Position

Per `docs/README.md` (the current authoritative positioning document,
which explicitly supersedes the stale `docs/index.md`): *"DrugSim v1.0 is
a computational ADMET research and prioritisation platform... Two
validated endpoints, each independently built, audited, and promoted on
its own evidence."* Both endpoints carry the same internal status:
`"VALIDATED FOR INTERNAL RESEARCH"` — real enough to serve predictions,
not yet through any formal "champion" promotion process (that process is
designed in `docs/tds/06-ml-architecture.md` but not implemented; see
[[project_drugsim_overview]]-adjacent findings from Phase 11/12 work).

TDS `01-overview-and-principles.md` §1.1 states DrugSim's positioning in
its own words: *"DrugSim is an AI-assisted preclinical prioritisation
platform... Its purpose is to help researchers decide which molecules to
make and test first."* §1.1.1: *"DrugSim is therefore not a replacement
for laboratory or animal testing, and must never be positioned as
one... The honest and commercially defensible claim is triage."* Target
users (§1.3): medicinal chemist (primary), DMPK/PK scientist,
toxicologist, computational chemist, regulatory/QA reviewer — explicitly
a preclinical research tool, explicitly **not** clinical decision support
(§1.5).

## Candidate Focus Areas

Evaluated using only what the repository itself has already tested for
feasibility (`docs/phase9/endpoint-selection.md`), not a fresh survey:

- **hERG / cardiac safety** — built, live, most deeply validated.
- **CYP3A4 / metabolic DDI risk** — built, live, competitive, lighter
  validation.
- **AMES mutagenicity** — real data sized (~7,278, TDC), explicitly
  deferred, not rejected — "a strong candidate for Phase 10."
- **BBB / CNS permeability** — real data sized (~2,030, TDC Martins et
  al.), explicitly deferred — "a good Phase 10 candidate for Distribution-
  category breadth."
- **Pgp (ABCB1) inhibition, CYP2D6, CYP2C9** — real ChEMBL data sized
  (2,654 / 1,394 / 2,609), deferred or rejected on sample size relative to
  CYP3A4.
- **Hepatotoxicity / DILI** — rejected outright: 475 compounds, "too
  small on its own for a robust scaffold-split train/calibration/test
  protocol matching hERG's methodology (hERG's training-split alone was
  6,792)."
- **Human bioavailability** — rejected: 640 compounds, and its units are
  flagged unverified in the project's own data registry.
- **Solubility, Caco-2, VDss, half-life, clearance** — rejected as a
  class: the registry already flags these as needing units "confirmed
  empirically... before model training," a defect that was never
  resolved, not something this decision resolves either.

## Evidence Comparison

| Focus | Dataset Size | Data Quality | Model Performance | External Validation | Applicability Domain | Uncertainty | Scientific Importance | Competition | Differentiation | Technical Feasibility | Overall Opportunity |
|---|---|---|---|---|---|---|---|---|---|---|---|
| **hERG** | 9,589 training-eligible (ChEMBL) | High — leakage-checked, y-scrambled (0.8394 real vs. 0.489±0.043 scrambled) | ROC-AUC 0.7875 (0.7843 as deployed, 200-tree memory truncation) | ROC-AUC 0.8696, n=4,030, independent source (PubChem) | 4-tier Tanimoto, tested under real distribution shift | Conformal 89.88% (nom. 90%); calibration degrades under shift (ECE 0.0597→0.3634) — disclosed, not hidden | High — QT prolongation/Torsades is a classic, well-understood late-stage attrition cause | Beats Claude (0.654) and ADMETlab2.0 (0.728) on full real test sets | Deepest audit trail of anything in the repo | Built, live | **Strongest today** |
| **CYP3A4** | 5,344 (ChEMBL) | Good — one real bug found and fixed (0 nM value); no leakage/y-scrambling audit | ROC-AUC 0.7995 | ROC-AUC 0.7758, n=12,152, independent source (TDC) | 2-signal Tanimoto/k-NN, internal test set only | Conformal 89.76% (nom. 90%); calibration untested under distribution shift | High — CYP3A4 metabolizes roughly half of marketed drugs; real specificity weakness noted (over-predicts inhibition) | Beats Claude (0.560) and ADMETlab2.0 (0.627) on full real test sets | Same infrastructure as hERG, validation depth not yet matched | Built, live | **Strong, not yet at hERG's bar** |
| **AMES (mutagenicity)** | ~7,278 (TDC) | Not evaluated | Not evaluated | Not evaluated | Not evaluated | Not evaluated | High — regulatory-standard genotoxicity screen | Not evaluated | Not evaluated | Data sized, nothing built | Deferred — real candidate |
| **BBB / CNS** | ~2,030 (TDC Martins et al.) | Not evaluated | Not evaluated | Not evaluated | Not evaluated | Not evaluated | High for CNS programs specifically, narrower than hERG/CYP3A4's cross-cutting relevance | Not evaluated | Not evaluated | Data sized, nothing built | Deferred — real, narrower candidate |
| **DILI (hepatotoxicity)** | 475 (TDC) | Insufficient — repo's own conclusion, not this decision's | Not evaluated | Not evaluated | Not evaluated | Not evaluated | High in principle | Not evaluated | Not evaluated | Rejected on sample size | Not viable without new data |
| **Solubility / absorption class** (Caco-2, VDss, half-life, clearance, bioavailability) | 475–~9,982 (TDC, size varies) | Insufficient — units unresolved across the class | Not evaluated | Not evaluated | Not evaluated | Not evaluated | Moderate–high, developability-relevant | Not evaluated | Not evaluated | Rejected as a class pending unit-verification work | Not viable until units are fixed |

## Primary Focus

**Early-stage cardiac liability screening for candidate small molecules
(hERG-mediated cardiotoxicity).**

Defined as:

- **Target user**: medicinal chemists and DMPK/toxicology scientists
  screening candidate structures before committing to synthesis or
  in-vitro cardiac assays.
- **Scientific problem**: hERG potassium-channel blockade, the
  best-characterized, most consequential single cause of drug-induced
  cardiac arrhythmia (QT prolongation / Torsades de Pointes) and a
  recurring cause of late-stage attrition and market withdrawal.
- **Drug discovery stage**: early hit-to-lead / lead optimization —
  before a compound reaches an animal or clinical study.
- **Core predictions**: hERG blocker/non-blocker classification with an
  applicability-domain verdict and a conformal prediction interval, not a
  bare probability.
- **User decision it informs**: whether to advance, deprioritize, or
  flag a candidate structure for early cardiac-safety triage, and how
  much to trust that call given where the compound sits relative to the
  training distribution.

**Why it wins**: it is not that cardiac safety is scientifically more
important than metabolic safety — the repository doesn't support that
claim. It wins because DrugSim's own evidence is deepest here: this is
the only endpoint with a leakage audit, a y-scrambling permutation test,
seed/bootstrap robustness testing, a feature-ablation study, an
external validation set from a genuinely independent source with its own
re-tested calibration (which honestly shows degradation under
distribution shift rather than hiding it), and a golden regression panel
that has caught a real decision-boundary flip (an earlier 35-tree
candidate silently flipped dofetilide — a known Class III antiarrhythmic
— from blocker to non-blocker, invisible to aggregate ROC-AUC). That is
the concrete, falsifiable trust story a preclinical triage tool needs,
and it exists today only for hERG.

## Secondary Focus

**CYP3A4-mediated metabolic drug-drug-interaction risk.** Real, live,
and competitive (beats both comparison baselines on its own full test
set), but has not been through hERG's validation gauntlet: no leakage or
y-scrambling audit, no seed/bootstrap robustness study, no
interpretability analysis, and no test of whether its calibration holds
up under real distribution shift the way hERG's was (and was found not
to). Phase 9's own report frames this correctly: a second endpoint
reaching parity with the first "on genuinely independent evidence"
supports a third; that parity, specifically on validation depth, is not
yet demonstrated.

## Supporting Capabilities

- The underlying platform infrastructure — the curation/provenance
  pipeline (Phase 11), the conformal-prediction and applicability-domain
  machinery, the transparent dual-split (scaffold vs. random) reporting,
  and the real head-to-head benchmarking methodology against Claude and
  ADMETlab 2.0 — should remain available to both endpoints and any future
  one. It is infrastructure that supports the focus; it is not itself the
  product identity.
- CYP3A4 remains a fully supported, served endpoint. Nothing about this
  decision removes it or deprioritizes its availability to users — it is
  secondary in evidence depth, not in availability.

## Differentiation

**Current differentiators** (real, evidenced in this repository today):

- Two endpoints independently built, audited, and promoted on their own
  documented evidence trail, rather than a single undifferentiated "AI
  quality score."
- Real, disclosed head-to-head benchmarking against both an LLM (Claude)
  and a purpose-built competitor tool (ADMETlab 2.0), on full real
  held-out test sets — not a cherry-picked spot check, and with honest
  disclosure of methodology mismatches (e.g., Claude's self-reported
  confidence is not the same kind of number as a calibrated
  `predict_proba`).
- Explicit dual-split reporting (scaffold-split vs. random-split proxy)
  that discloses the leakage-optimism gap most comparable tools do not
  surface at all.
- For hERG specifically: uncertainty that is reported honestly, including
  where it breaks — calibration degrading under real distribution shift
  is disclosed, not hidden, and applicability domain is reported as a
  measured accuracy gradient (in-domain vs. borderline vs. out-of-domain),
  not a binary trust/don't-trust flag.
- Per-record provenance and curation infrastructure (Phase 11) that can
  answer "where did this training value come from" for any compound —
  not yet a competitive moat on its own (both endpoints are still
  single-source ChEMBL), but real, working infrastructure most comparable
  tools don't expose.

**Future differentiators** (not yet proven — explicitly aspirational):

- Bringing CYP3A4, and any future endpoint, up to hERG's validation depth,
  so the trust story is uniform across the platform rather than
  concentrated in one endpoint.
- The curation pipeline eventually ingesting a second, non-ChEMBL data
  source — only then does per-record provenance become a real
  differentiator against single-source competitors rather than
  documented-but-unexercised infrastructure.
- A genuinely broad "why should you trust this number" surface built for
  the end user (chemist/toxicologist), not just internal audit reports.

**Not claimed**: superiority over general-purpose AI as a category (only
over Claude specifically, on these two endpoints, on this evaluation
methodology), and public datasets themselves are not treated as a moat —
the moat claim here is the validation and provenance work done on top of
them.

## Biggest Risks

- **CYP3A4's shallower validation** is a real gap, not a stylistic
  difference — if CYP3A4 were promoted to co-flagship status without
  closing it, that would be an overclaim relative to the evidence.
- **hERG's deployed model is not the model most of its own evaluation
  numbers describe.** The deployed artifact is a 200-tree truncation of
  the trained 500-tree ensemble (a disclosed Render memory-limit
  workaround), so "current production" and "most-validated" numbers
  differ slightly (0.7843 vs. 0.7875) — small in this case, but worth
  resolving so the flagship endpoint's story is unambiguous.
- **Both endpoints are single-source (ChEMBL).** No cross-source
  duplicate resolution or license diversity has actually been exercised
  yet, so today's provenance infrastructure is real but not yet
  differentiating in practice.
- **Only two endpoints exist.** A "platform" claim broader than "two
  well-validated screens" is not yet supported by evidence.
- **CYP3A4's documented specificity weakness** (it over-predicts
  inhibition, consistent with the actives-biased-literature risk named in
  `docs/tds/10-risk-register.md`) means a secondary-focus framing should
  come with that limitation stated plainly, not glossed over.

## Evidence Still Missing

- CYP3A4's behavior under real-world distribution shift (the specific
  calibration/coverage re-test that revealed a real weakness for hERG)
  has never been run.
- No leakage audit, y-scrambling test, robustness/seed-stability study, or
  interpretability analysis exists for CYP3A4.
- No real-world usage evidence exists for either endpoint — no case study
  or user feedback demonstrating that the "user decision" this document
  defines is actually being made differently because of DrugSim's output.
- Every deferred/rejected candidate (AMES, BBB, Pgp, CYP2D6, CYP2C9, DILI,
  solubility/absorption class) has at most a dataset-sizing estimate —
  zero model, validation, or competitive-comparison evidence exists for
  any of them.

## Recommended Next Steps

| Priority | Reason | Expected Value | Required Data | Required Validation | Difficulty |
|---|---|---|---|---|---|
| **1. Close CYP3A4's validation gap** (leakage/y-scrambling/robustness/interpretability/external-calibration-under-shift) | Brings the secondary focus to the same evidence bar as the primary one, removing the biggest asymmetry this decision found | Makes a real "two validated endpoints" claim instead of "one validated, one competitive" | None new — reuse existing internal + external (TDC) test sets | Adapt hERG's existing `phase4/` scripts (already-built templates) to CYP3A4 | Low–Medium |
| **2. Resolve the hERG deployed-vs-evaluated model discrepancy** | The flagship endpoint's own served artifact doesn't match most of its own validation numbers | Removes a documented but unresolved inconsistency in the strongest endpoint's story | None new | Re-run the golden regression panel and key phase4 checks against the actual 200-tree deployed artifact, or resolve the memory constraint so the evaluated model is the served one | Low |
| **3. Pilot a third endpoint on the strongest deferred candidate (BBB or AMES)** | Tests whether Phase 9's "twice-proven framework" genuinely generalizes to a third endpoint, expanding platform breadth deliberately rather than by default | Real evidence for or against broader platform claims | Real, already-sized TDC data (BBB ~2,030 or AMES ~7,278) | Full build-and-validate cycle mirroring CYP3A4's Phase 9 process, ideally including the Priority 1 validation depth from the start | Medium |

## Website Impact (Future Work — Not Implemented Now)

No redesign is proposed or performed as part of this decision. For a
later, separate implementation phase to consider:

- **Pages that may eventually need updating**: the homepage/landing
  copy and `/benchmarks` if hERG is foregrounded as the lead story rather
  than presenting both endpoints as equally weighted.
- **Terminology that may eventually change**: leading with "cardiac
  safety screening" as the primary framing, with "metabolic/DDI risk"
  positioned explicitly as a second, actively-maturing capability rather
  than co-equal.
- **Features that may become primary**: hERG's applicability-domain and
  conformal-interval reporting, and the dofetilide-style golden-panel
  trust story, as user-facing narrative — currently these exist only in
  internal reports.
- **Features that should remain available and unchanged**: CYP3A4
  prediction itself, the existing `/benchmarks` comparison against Claude
  and ADMETlab 2.0 for both endpoints, and the API surface — nothing here
  proposes removing or gating any existing endpoint.

## Validation Check

- **Does this focus have enough data?** Yes for hERG (9,589 compounds,
  independently externally validated); yes for CYP3A4 as secondary, with
  a known validation-depth gap disclosed above.
- **Does DrugSim currently have enough evidence to support it?** Yes for
  hERG as primary; CYP3A4 as secondary is evidenced but intentionally not
  claimed as co-equal until its gap closes.
- **Can DrugSim realistically differentiate here?** Yes, on validation
  transparency and honest uncertainty reporting specifically — evidenced
  today, not aspirational — though not yet on data-source diversity.
- **Can the focus expand into a larger platform later?** Yes — Phase 9
  already identified real, sized, deferred candidates (AMES, BBB, Pgp,
  CYP2D6, CYP2C9) as a concrete expansion path, not a vague aspiration.
- **Would a researcher understand why DrugSim exists?** Yes: "an early
  cardiac-safety and metabolic-risk triage tool for candidate molecules,
  validated transparently enough to know when to trust it less" is a
  claim this repository's own evidence actually supports.

None of these answers came back weak enough to require reconsidering the
recommendation.
