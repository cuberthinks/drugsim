# Data-source audit: psychiatric compound screening

Per the brief's §2 instruction: identify and verify real data sources
for DRD2, HRH1, CYP2D6, and BBB before assuming any of them is
buildable, following the same methodology
`docs/phase9/endpoint-selection.md` already established for hERG/CYP3A4
(and rejected/deferred AMES, Pgp, CYP2D6, CYP2C9, BBB). **Do not assume
a dataset is usable simply because it is publicly available** — every
number below is either a live tool call made during this audit or an
exact quote from the existing Phase 9 audit, never invented.

## Summary verdict

| Endpoint | Source | Real size (raw) | Status |
|---|---|---|---|
| DRD2 | ChEMBL (CHEMBL217) | 14,842 Ki / 2,480 IC50 | **Strong candidate** — proceed to quality-gated dataset build |
| HRH1 | ChEMBL (CHEMBL231) | 2,893 Ki / 1,334 IC50 | **Moderate candidate** — proceed, but expect a noisier/smaller model than DRD2 |
| CYP2D6 | ChEMBL (CHEMBL289) | 8,684 IC50 raw / 3,349 after nM+pChEMBL filtering (live-verified 2026-08-30) | **Moderate candidate** — Phase 9's rejection was based on the wrong target ID; the real target has real, usable data |
| BBB | TDC (Martins et al.), via the already-registered `tdc` source | ~2,030 compounds (registry-cited, not yet independently downloaded) | **Deferred candidate, real** — usable, but needs an actual download + quality gate before a model can be built; not yet done |
| hERG | Existing DrugSim model (`herg_inhibition_v1`) | 9,589 training-eligible compounds (already validated) | **Reuse as-is** — no new data, no retraining |

## DRD2 — dopamine D2 receptor

- **ChEMBL target**: `CHEMBL217`, "D(2) dopamine receptor," SINGLE
  PROTEIN, Homo sapiens (UniProt P14416) — confirmed via live
  `target_search`, not assumed from memory.
- **Real record counts** (live `get_bioactivity` query, today): **14,842
  Ki records, 2,480 IC50 records, 32,602 total activity records across
  all types.** These are raw, unfiltered ChEMBL totals — not yet
  restricted to `confidence_score >= 8` and `standard_relation = '='`
  the way Phase 9's own CYP3A4 sizing was (that filtering typically
  removes a meaningful fraction; CYP3A4 went from 13,887 raw IC50
  records to 6,755 after real filtering). Even a substantial reduction
  from 14,842 would likely leave a dataset comfortably larger than
  CYP3A4's own final 6,755 — this is the strongest candidate found in
  this audit.
- **Endpoint definition, if built**: Ki is the dominant, and more
  scientifically appropriate, measurement type here (a true binding
  affinity, assay-independent) — IC50 is assay/substrate-concentration
  dependent and about 6x rarer for this target. **Ki and IC50 should
  not be pooled without justification** (the brief's own §4 instruction)
  — the real, large Ki population makes this an easy call: use Ki only,
  discard/report-separately the smaller IC50 set.
- **License**: ChEMBL is DrugSim's own already-registered, already-used
  primary source (same registry entry hERG/CYP3A4 use).
- **Suitability**: real, large, single well-defined measurement type
  available. No units-ambiguity risk (ChEMBL Ki values are consistently
  reported in nM with a documented `standard_units` field, the same
  field hERG/CYP3A4 already rely on).

## HRH1 — histamine H1 receptor

- **ChEMBL target**: `CHEMBL231`, "Histamine H1 receptor," SINGLE
  PROTEIN, Homo sapiens (UniProt P35367) — confirmed via live
  `target_search`.
- **Real record counts** (live, today): **2,893 Ki records, 1,334 IC50
  records, 8,251 total.** Raw, unfiltered. After the same confidence/
  relation filtering DRD2 will need, this will likely land somewhere in
  the 1,500–2,500 range — comparable to Phase 9's own "deferred, real
  candidate" tier (Pgp: 2,654 live-verified; BBB: ~2,030 registry-cited),
  clearly larger than its "rejected outright" tier (CYP2D6: 1,394;
  DILI: 475).
- **Endpoint definition, if built**: same reasoning as DRD2 — Ki
  dominant, use Ki only.
- **Suitability**: real and usable, but the smaller size than DRD2
  means a HRH1 model should be expected to have wider uncertainty
  intervals and a smaller, less diverse applicability domain — this
  should be stated plainly if/when a model is actually trained, not
  glossed over.

## CYP2D6 — Phase 9's rejection was based on the wrong target; corrected here

The cheap live re-check flagged as worthwhile "when this endpoint's
phase actually starts" turned up a real error, not just a size update.
Phase 9's `docs/phase9/endpoint-selection.md` cites CYP2D6's ChEMBL
target as `CHEMBL2035` with 1,394 IC50 records. **`CHEMBL2035` is not
CYP2D6** — live `target_search` confirms it is the **muscarinic
acetylcholine receptor M5 (CHRM5)**, an unrelated GPCR. The actual
CYP2D6 target is **`CHEMBL289`** ("Cytochrome P450 2D6," SINGLE
PROTEIN, Homo sapiens, UniProt P10635), confirmed live today
(2026-08-30).

**Real record counts for the correct target**: **8,684 raw IC50
records; 3,349 after restricting to `standard_units='nM'` with a
`pchembl_value` present** (the same style of filter CYP3A4 used, which
went from 13,887 raw to 6,755 filtered). 3,349 is larger than Pgp
(2,654, Phase 9's own "deferred, real candidate" tier) and CYP2C9
(2,609), and more than double HRH1's entire *final, already-built*
dataset (1,395 compounds). CYP2D6 was never actually the smallest CYP
isoform checked — the number that earned it a rejection belongs to a
different protein entirely.

**Corrected verdict**: CYP2D6 is a **moderate, real candidate**, not
insufficient data. Phase 9's own erratum note has been added at
`docs/phase9/endpoint-selection.md` rather than silently rewriting that
table. Per the brief's own §3 instruction (dataset-quality gate first),
this endpoint is now cleared to proceed to an actual quality-gated
dataset build, following the identical `fetch_chembl_data.py` →
`build_dataset.py` → `prepare_features.py` → `train.py` → `evaluate.py`
pipeline already used for DRD2 and HRH1 — subject to the usual
discordance/duplicate/quarantine filtering actually landing in a usable
final compound count once real curation is applied (3,349 is the raw
filtered ceiling, not the guaranteed final size).

**One remaining, separate concern this does not resolve**: even with
real binding data, a CYP2D6 *inhibition* model still cannot infer a
patient's CYP2D6 *genotype/phenotype* — that scientific distinction
(already classified in `scientific-foundation.md`) is about what the
model can claim, not about data availability, and stands regardless of
this correction.

## BBB — blood-brain-barrier permeability

The brief suggests B3DB. **B3DB does not exist anywhere in DrugSim's
registry or documented history** — confirmed absent from
`datasets/registry.yaml`'s full list of 15 registered sources (ChEMBL,
PubChem, BindingDB, TDC, ToxCast/Tox21, UniProt, RCSB PDB, DrugCentral,
Open Targets, openFDA, DailyMed, DrugBank, FreeSolv, PDBbind, SIDER) and
from every doc in the repo (`grep -ni b3db` across the whole tree: zero
hits). Per the brief's own instruction ("do not assume a dataset is
usable simply because it is publicly available"), onboarding B3DB fresh
would require a full registry-vetting pass — a real license/provenance/
verification step, not a quick download, following the exact discipline
Phase 11's `resolve_license`/`audit_registry` machinery already
enforces for every other source.

**Therapeutics Data Commons (`tdc`), however, is already a registered,
licensed source** (`datasets/registry.yaml`, `source_id: tdc`, `role:
admet_training`, license `MIXED`/`amber` default, `commercial_ok:
partial`, verified 2026-08-05). Phase 9 already identified TDC's own
Martins et al. BBB dataset as a real, deferred candidate (~2,030
compounds, binary BBB+/BBB- label). **Using TDC's existing BBB dataset
instead of onboarding B3DB is the properly-vetted path** — this is a
deliberate substitution from the brief's suggested source, made because
the suggested source has no governance trail in this project and an
equivalent, real, already-approved one does. Not a silent swap: stated
here explicitly.

One relevant, favorable detail found during registry verification: TDC's
own registry entry carries a `units_caveat` explicitly naming which of
its datasets have undocumented/ambiguous units — *"neither states units
for Caco-2, Lipophilicity, Solubility, VDss, Half Life, Clearance, or
LD50."* **BBB is not on that list** — it is a binary classification
label, not a continuous unit-bearing measurement, so it does not carry
the same units-ambiguity risk TDC's regression-style ADME endpoints do.

**Status**: real, identified, lower-risk-than-most-TDC-endpoints on the
units front — but **not yet downloaded or quality-gated**. Phase 9 only
sized it as a candidate; no dataset build has happened. This audit
does not claim BBB is ready to model today, only that it is the correct
source to build from once that work is actually undertaken.

## hERG — reuse, do not retrain

Per the brief's own §9 instruction. Already validated
(`models/registry/herg_inhibition_v1.json`, `final_report_status:
"VALIDATED FOR INTERNAL RESEARCH"`), already integrated into
`drugsim_predict`. This pipeline should call the existing model exactly
as `/predict` already does, carrying its own applicability-domain/
uncertainty/reliability output through unchanged — no new dataset, no
new training run.

## Architecture note (not a data-source finding, but load-bearing for what's buildable)

`src/drugsim_predict/schemas.py`/`pipeline.py` currently support only
binary classification output (`predicted_label`, `predicted_probability`,
a classification-shaped conformal p-value construct). Neither DRD2 nor
HRH1 can be reduced to that shape without losing the brief's own
selectivity requirement (§6: *"how much more strongly"* one target binds
vs. the other, which requires a genuine continuous predicted value, not
a binary label). Building DRD2/HRH1 for real will require new
regression-style schema/conformal/applicability-domain work in
`drugsim_predict` — a distinct, separately-scoped architecture step, not
something that falls out of "register a new model_id" the way adding
CYP3A4 did.

## What this audit recommends, and does not recommend

- **DRD2**: proceed to a real, quality-gated dataset build next — the
  strongest, best-supported candidate found.
- **HRH1**: proceed alongside DRD2, with its smaller size disclosed
  plainly in every downstream artifact (model card, applicability
  domain reporting, uncertainty).
- **CYP2D6**: proceed to a real, quality-gated dataset build — Phase 9's
  rejection was based on the wrong ChEMBL target and does not apply to
  the real one (`CHEMBL289`), which has real, usable data.
- **BBB**: real and viable via TDC, but requires an actual download and
  quality gate that has not happened yet — a separate, later step, not
  bundled into this audit.
- **hERG**: integrate the existing model as-is.
- **Before any DRD2/HRH1 model training begins**: the regression-support
  architecture gap above needs its own scoped design pass — attempting
  to skip it by force-fitting a classification threshold would silently
  break the brief's own selectivity requirement, which explicitly
  demands a continuous, direction-correct affinity comparison.
