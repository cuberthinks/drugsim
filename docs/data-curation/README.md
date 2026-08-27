# Data curation

What `drugsim_curation` produces, where its outputs live, and — most
importantly — what it does **not** touch. See `docs/data-curation/current-
state.md` for the audit this phase started from, and `rules.md` for every
rule the pipeline implements.

## What this phase produces

For each of the two live endpoints (hERG, CYP3A4), reading the same
committed raw ChEMBL pull `build_dataset.py` already reads:

- `datasets/curated/{endpoint}_measurements_ledger.csv` — one row per raw
  measurement, including every row `build_dataset.py` currently drops
  (censored relations, flagged records, unresolved units, invalid or
  mixture structures), each with an explicit `curation_status` and
  `exclusion_reason`.
- `datasets/curated/{endpoint}_curated_compounds.csv` — the resolved,
  aggregated view. Discordant compounds are **retained** with
  `training_eligible=false` and a reason, not dropped the way
  `build_dataset.py` drops them today.
- `datasets/curated/{endpoint}_curation_report.json` — the funnel (raw →
  valid → standardised → resolved → training-eligible) and every
  exclusion reason, counted. Schema documented in `quality-report.md`.
- `datasets/curated/{endpoint}_curation_manifest.json` — checksum-chained
  back to the raw dataset's own manifest, same pattern as
  `datasets/processed/*_dataset_manifest.json`.

## Pipeline stages

1. **Structure standardisation** — one call to `drugsim_chem.process_structure`
   per distinct molecule, exactly as `build_dataset.py` does. Not
   reimplemented; this phase adds nothing here.
2. **Unit resolution** — `drugsim_curation.units.resolve_unit`. Molar units
   (nM/uM/mM/M/pM) convert on a fixed factor; mass-concentration units
   (ug/mL etc.) need a molecular weight or are marked `unresolved`.
   Nothing is guessed.
3. **Assay-context enrichment** — `drugsim_curation.assay_context`, a
   cached, generic-over-target ChEMBL `assay.json` lookup, re-deriving the
   pattern `audit_assay_heterogeneity.py` (Phase 3.5) already proved out.
4. **Licence resolution** — `drugsim_curation.provenance.resolve_license`
   against `datasets/registry.yaml`, failing closed on anything
   unresolved.
5. **Ledger construction** — `drugsim_curation.ledger.build_ledger_row`, one
   row per raw measurement, deciding `curation_status`/`exclusion_reason`
   from a documented priority order (invalid structure > mixture >
   censored > bad-validity-flagged > unresolved unit > unresolved
   licence).
6. **Exact-duplicate tagging** — `find_exact_duplicate_measurements`,
   identical value+unit+relation+assay+document within one compound.
7. **Aggregation** — reuses `drugsim_quality.aggregation.aggregate_continuous`
   unchanged (geometric mean for potency, >10x spread is discordant). The
   only behavioural change from `build_dataset.py` is what happens
   *after*: a discordant compound is kept, not dropped.
8. **Quality scoring** — `drugsim_curation.quality_score`, a weighted sum
   of named, inspectable components (see `rules.md`).
9. **Reporting** — `drugsim_curation.report.build_curation_report`.

All of this is orchestrated by one shared function,
`drugsim_curation.pipeline.curate_raw_rows` — the two per-endpoint driver
scripts (`models/admet/{herg,cyp3a4}_inhibition/curate_measurements.py`)
and the golden-fixture generator/test all call it, so the sequence exists
in exactly one place.

## Where outputs live

```
datasets/
  raw/                  <- unchanged, pre-existing, immutable
  processed/             <- unchanged, pre-existing -- the live models' actual training data
  curated/               <- NEW, this phase's output
  golden/
    compounds.csv         <- unchanged, pre-existing (chemistry-only golden set)
    measurements.csv       <- NEW, this phase's own self-contained golden set
    expected_curation_output.json  <- NEW
```

## How to run it

```bash
python models/admet/herg_inhibition/curate_measurements.py
python models/admet/cyp3a4_inhibition/curate_measurements.py
```

Pass `--no-network` to skip the live ChEMBL assay-metadata fetch and use
only the local cache at `datasets/reference/chembl_{herg,cyp3a4}_assay_metadata_cache.json`
(already populated from the first real run of each).

To regenerate the golden fixture after a deliberate, reviewed change to
curation logic:

```bash
python scripts/generate_curation_golden_fixtures.py
```

## Relationship to the live models

**This phase changes nothing about what the live models train on or how
they behave.** Verified directly, not just asserted: `datasets/processed/*.csv`,
`datasets/processed/*.npz`, `build_dataset.py`, `fetch_chembl_data.py`, and
`prepare_features.py` are all byte-identical before and after this
phase's entire implementation — checked via SHA-256 at the start of this
work and re-checked after every run of the new pipeline.

Every curated output is a **new, additive artifact**. A future modelling
phase would explicitly choose to consume `datasets/curated/` instead of
`datasets/processed/` — that decision is out of scope here, deliberately
(see the original phase brief's "STOP after completing the curation
pipeline, do not retrain").

## Two real numbers that prove this works, not just compiles

Running the curation pipeline against the real, committed raw data and
comparing to `build_dataset.py`'s own manifest, independently:

| | hERG | CYP3A4 |
|---|---|---|
| Discordant compounds (>10x spread) | 148 = 148 | 97 = 97 |
| Training-eligible / final compound count | 9,589 = 9,589 | 5,344 = 5,344 |

Both match exactly. `tests/integration/test_curation_real_data.py` codifies
this reconciliation so it can't silently drift.

## Known limitations

- **Assay context beyond organism/cell-type/tissue/paradigm is not
  extracted.** Concentration, temperature, pH, exposure duration, and
  detailed method are not top-level ChEMBL assay fields for these targets
  (verified against all 4,829 hERG-target assays) — a rarely-populated
  (0.7%) nested `assay_parameters` array can occasionally carry one of
  these, but parsing that heterogeneous structure is not attempted in this
  version. See `rules.md`.
- **Duplicate resolution is trivially satisfied today.** Both live
  endpoints are single-source ChEMBL, so `drugsim_quality.dedup.find_measurement_duplicates`
  (built for cross-source dedup) has nothing to do yet — the
  `duplicate_resolution` quality-score component is always 1.0 in
  practice until a second source is added.
- **Per-record licence tracking is likewise trivially satisfied today**,
  for the same single-source reason — every record resolves against the
  one `chembl` registry entry.
- **The mixture-count difference from `build_dataset.py` is real and
  explained, not a bug**: this pipeline checks every molecule's structure
  regardless of whether its measurements pass other filters;
  `build_dataset.py` only ever sees a molecule if at least one of its raw
  rows survives its own censored/bad-validity filter first. For hERG, 54
  distinct molecules are mixture-flagged here vs. 27 in
  `build_dataset.py`'s manifest — the extra 27 have zero uncensored,
  non-flagged measurements, so `build_dataset.py` structurally never sees
  them at all.
