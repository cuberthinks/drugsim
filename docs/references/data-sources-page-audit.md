# Data Sources & References Page — Audit

Read-only audit conducted before building `frontend/src/pages/SourcesPage.tsx`,
verifying exactly which external datasets genuinely produced the two live
models' training or validation data, versus which are merely catalogued in
the project's internal source registry (`datasets/registry.yaml`) or
identified as ideas in planning documents. This distinction is the whole
point of the audit: registry membership is not the same as usage.

## 1. Sources verified as active

Only two datasets genuinely produced data behind a live model — one for
training, one for external validation of both endpoints combined:

- **ChEMBL** — both models' training data.
  - `models/admet/herg_inhibition/fetch_chembl_data.py:1-2,39-40` fetches
    CHEMBL240 IC50 activities directly from ChEMBL's public REST API
    (`https://www.ebi.ac.uk/chembl/api/data/activity.json`).
  - `models/admet/cyp3a4_inhibition/fetch_chembl_data.py:1-2,39-40` does the
    same for CHEMBL340.
  - `models/registry/herg_inhibition_v1.json:39` and
    `models/registry/cyp3a4_inhibition_v1.json` `dataset.source` fields
    state this in the shipped model registry itself, not just a build script.
  - `docs/methodology/index.md:5` already states this publicly (in the
    engineering docs, not yet on the frontend before this change).

- **PubChem** — hERG external validation, direct; CYP3A4 external
  validation, indirect (via TDC, see below).
  - `models/admet/herg_inhibition/phase4/04_external_validation.py:87`
    fetches PubChem AID 588834 directly from PubChem's own PUG REST API
    (`https://pubchem.ncbi.nlm.nih.gov/rest/pug/assay/aid/588834/CSV`).
  - `models/admet/herg_inhibition/phase4/04_external_validation_report.json`
    is a real, generated result (2026-08-09): 4,030 compounds after quality
    filtering, ROC-AUC 0.8664–0.8696 depending on overlap handling.
  - `models/admet/cyp3a4_inhibition/external_validation.py:4-31` and
    `models/admet/cyp3a4_inhibition/external_validation_report.json`
    confirm the CYP3A4 model's own external validation set (TDC's
    `CYP3A4_Veith`) is itself a republication of a PubChem screen (AID
    1851, Veith et al. 2009) — so PubChem is the ultimate origin of that
    data too, even though DrugSim's own code reaches it through TDC, not
    PubChem directly, for that one endpoint.

- **Therapeutics Data Commons (TDC)** — CYP3A4 external validation only,
  never training.
  - `models/admet/cyp3a4_inhibition/external_validation.py:4-8` fetches the
    `CYP3A4_Veith` dataset via a direct HTTP fetch of its Harvard Dataverse
    file (PyTDC's own Python wrapper reportedly failed in this
    environment) — confirmed also by the absence of any `PyTDC`/`tdc`
    dependency in `pyproject.toml` or `requirements-lock.txt`.
  - `docs/phase9/phase9-admet-expansion-report.md:126,138` and
    `docs/phase4/phase4-reliability-report.md` corroborate this.
  - TDC was never used for hERG at all: `docs/phase3/phase3-model-validation-report.md:11`
    documents that TDC's own download endpoint was blocked in this
    environment during hERG's development, which is why ChEMBL was used
    directly for training and PubChem directly (not via TDC) for hERG's
    external validation.

**Important correction made as part of this audit**: the live
`frontend/src/pages/LimitationsPage.tsx` stated, before this change, "hERG
model: no independent external validation... an external validation
attempt was blocked by an unreachable data source during training." This
was stale — `docs/phase4/phase4-reliability-report.md:41` and the report
JSON above show a real, completed, successful external validation exists
(the *blocked* endpoint referenced was TDC specifically for training-set
comparability, not PubChem for validation, which succeeded independently
and later). Publishing an honest Data Sources page while leaving this
contradiction live would have undermined the exact credibility this page
exists to build, so `LimitationsPage.tsx`'s hERG entry was corrected to
describe what the evidence actually shows: strong ROC-AUC transfer (0.87)
but a real precision drop under the external set's much lower positive
prevalence (~10% vs. ~66% in training) — a more specific and more useful
limitation than the previous blanket claim.

## 2. Sources verified as unused

Confirmed via `datasets/registry.yaml`'s own `excluded_sources:` block,
each independently corroborated against a second doc or code comment:

| Source | Real reason (verbatim from the registry) | Corroboration |
|---|---|---|
| DrugBank | `commercial_license_required` — "Free for academic non-commercial use only; commercial use requires a paid license." | `docs/phase1/step10-technology-stack.md:99` |
| FreeSolv | `non_commercial_license` — CC BY-NC-SA 4.0, ships inside TDC, "MUST be hard-gated in code, not merely documented." | `README.md:167-169` |
| PDBbind | `license_unverified_restrictive` — "licensing appears to carry academic restrictions. Blocked pending verification." | `docs/phase1/step10-technology-stack.md:99` |
| SIDER | `stale_superseded` — **not a licensing reason**: frozen at v4.1 (Oct 2015), maintainers report funding ended, misses every drug approved since. Replacement noted as `openfda_faers`. | `datasets/registry.yaml:485-507` |

The SIDER case is the one place a generic template answer would have been
actively wrong: the task brief's own suggested placeholder text ("Not
currently used") and a guessed licensing reason would both have
misrepresented the real, documented reason (staleness), which the page
now states correctly.

Additionally confirmed **not used, and not even catalogued for future
use with any license review done** — genuinely just names identified as
candidates in `datasets/registry.yaml`'s `deferred_sources:` block, with
no fetch code anywhere in `models/`, `src/`, or `scripts/` (verified by
repo-wide grep for each name): PharmGKB, ChEBI, DSSTox, Reactome, Gene
Ontology, ClinicalTrials.gov, AlphaFold DB, LINCS/L1000, ZINC22.

And confirmed **catalogued in the registry with real license/verification
work already done, but never actually ingested or used by any live
prediction** (repo-wide grep for each name in `models/`, `src/`,
`scripts/` found no fetch/ingestion code for any of them; several are
explicitly disclaimed as not-yet-real in
`docs/phase2/phase2-completion-report.md:111-116`, e.g. "No large-scale
external source (ChEMBL/BindingDB/PDB bulk) was ingested end-to-end in
this environment"): BindingDB, ToxCast/Tox21, UniProt, RCSB PDB,
DrugCentral, Open Targets, openFDA/FAERS, DailyMed.

## 3. Sources requiring further verification

- **PubChem's own aggregate statistics** (compound/substance/bioassay
  counts) are marked `verification.status: secondary` in
  `datasets/registry.yaml:100-104` — "primary source DNS-blocked at
  compile time," with an explicit `action_required` to re-verify. This
  does **not** affect the AID 588834 hERG validation result itself, which
  was fetched and checked directly and independently of this general
  registry entry.
- **DailyMed**'s registry entry is marked `verification.status:
  unverified` (`datasets/registry.yaml:431-435`) — not used by DrugSim
  today regardless, so this doesn't affect the page's claims, only the
  registry's own internal completeness.
- **`README.md`'s own "Data licensing" tier table lists SIDER and
  PharmGKB** as if they were live, ingested sources, which conflicts with
  `datasets/registry.yaml`'s authoritative classification of SIDER as
  excluded and PharmGKB as merely deferred. This is a pre-existing
  inconsistency in an internal engineering document (not user-facing) —
  flagged here, not corrected, since it's outside this task's scope
  (building the public page); the new `SourcesPage.tsx` follows the
  registry's authoritative classification, not `README.md`'s.

## 4. Licence information

Drawn directly from `datasets/registry.yaml`'s per-source `license` block
for the three active sources (the only ones where a licence claim is made
on the public page):

| Source | SPDX | Attribution string (verbatim) |
|---|---|---|
| ChEMBL | CC-BY-SA-3.0 | "ChEMBL (EMBL-EBI), release 37, CC BY-SA 3.0" |
| PubChem | US-PD | "PubChem, National Library of Medicine (NCBI/NIH)" — aggregator caveat: some depositor records carry their own terms |
| TDC | Mixed (default CC-BY-4.0) | "Therapeutics Data Commons, Harvard (Zitnik Lab)"; FreeSolv sub-dataset is CC-BY-NC-SA-4.0 and hard-excluded |

Licence tiers for the future/catalogued sources are also fully specified
in the registry (all sourced from the same file, not invented for this
page) and shown on the page's "Potential future sources" section without
implying any of them are used.

## 5. Attribution requirements

The page names each active source's institutional provider using only
the `attribution` string already present in `datasets/registry.yaml` —
no institution name was inferred or guessed. Eleven institutions are
named in the "Key institutions & providers" section, each tied to a
registry entry with an explicit `attribution` field: EMBL-EBI, National
Library of Medicine (NCBI/NIH), Harvard University (Zitnik Lab), UC San
Diego, U.S. EPA, UniProt Consortium, RCSB, University of New Mexico, Open
Targets Platform, U.S. Food and Drug Administration, and U.S. National
Library of Medicine. The nine `deferred_sources` (PharmGKB, ChEBI, etc.)
have **no** `attribution` field in the registry, so no institution is
named for them anywhere on the page — this is deliberate, not an
oversight, per the instruction not to invent affiliations.

## 6. Remaining uncertainties

- Whether ShareAlike terms (ChEMBL, and the ChEMBL-derived portion of any
  future BindingDB ingestion) would extend to a trained model's weights is
  explicitly tracked as an open legal question in `README.md`'s own "Data
  licensing" section (its own words: "legally unsettled... tracked as risk
  R1"). This audit does not resolve that question; the new page does not
  make any claim about it either way.
- The `README.md` SIDER/PharmGKB tier-table inconsistency (§3 above)
  remains uncorrected — flagged as a documentation-accuracy risk for a
  future pass, consistent with how a similar internal-doc-vs-reality gap
  was handled in the 2026-08-22 confidentiality audit (documented, not
  silently fixed, when out of the current task's direct scope).
- This page describes the *current* state of two specific model artifacts.
  If either model is retrained on updated ChEMBL data, or a new endpoint is
  added, this page and `frontend/src/lib/dataSources.ts` will need a
  corresponding update — nothing here is automatically kept in sync with
  future model registry changes.
