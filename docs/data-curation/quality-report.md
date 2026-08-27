# Curation report schema

Every curation run writes `datasets/curated/{endpoint}_curation_report.json`.
This document is the schema reference, plus a real worked example from the
hERG run that produced the numbers in `README.md`.

## Report JSON schema

```json
{
  "report_version": "1.0",
  "endpoint": "herg_inhibition",
  "generated_at": "<ISO-8601 timestamp>",
  "curation_pipeline_version": "v1",
  "source": {
    "raw_csv": "datasets/raw/chembl_herg_ic50_raw.csv",
    "raw_manifest_sha256": "<sha256 of the raw dataset's own manifest checksum>",
    "retrieval_date": "<from the raw manifest>"
  },
  "funnel": {
    "raw_records": 0,
    "valid_structures": 0,
    "invalid_structures_quarantined": 0,
    "mixtures_excluded": 0,
    "standardized_entities": 0,
    "unit_resolved_records": 0,
    "unit_unresolved_records": 0,
    "license_resolved_records": 0,
    "license_unresolved_records": 0,
    "exact_duplicate_records_collapsed": 0,
    "conflict_consistent_compounds": 0,
    "conflict_discordant_compounds": 0,
    "training_eligible_compounds": 0,
    "training_ineligible_compounds": 0
  },
  "exclusion_reasons": {
    "measurement_level": { "<reason>": 0 },
    "compound_level": { "<reason>": 0 }
  },
  "quality_score_distribution": { "mean": 0.0, "median": 0.0, "min": 0.0, "max": 0.0 },
  "assay_context_coverage": {
    "fraction_with_organism_or_paradigm": 0.0,
    "unavailable_dimensions": ["concentration", "temperature", "pH", "exposure_duration", "method"]
  },
  "outputs": {
    "ledger_csv": { "path": "...", "sha256": "..." },
    "curated_compounds_csv": { "path": "...", "sha256": "..." }
  }
}
```

## Funnel definition

`raw_records` is the total row count in the raw CSV — every one gets a
ledger row, none are excluded before that point. From there:

```
raw_records
  = valid_structures + invalid_structures_quarantined + mixtures_excluded
```

`standardized_entities` is the number of distinct compounds among the
valid-structure rows (many raw rows collapse onto one compound). Each
entity becomes exactly one row of `curated_compounds`, so:

```
standardized_entities
  = conflict_consistent_compounds + conflict_discordant_compounds
    + (compounds with conflict_status == "insufficient_data")
```

and

```
training_eligible_compounds + training_ineligible_compounds
  = standardized_entities
```

## Reading the exclusion reasons

`exclusion_reasons.measurement_level` counts ledger rows by why they were
excluded from aggregation — `invalid_structure`, `mixture`,
`censored_measurement`, `bad_validity_comment`, `unresolved_unit`,
`unresolved_license` — each row gets exactly one, chosen by the priority
order in `rules.md`, so these counts never double-count a row.

`exclusion_reasons.compound_level` counts curated compounds by why they
are `training_eligible=false`: `discordant_gt_10x`, `no_usable_measurements`,
or `unresolved_license`.

A censored or bad-validity-flagged row that also belongs to a mixture-
flagged molecule is counted once, under `mixture` (the more fundamental
reason) — this is why `measurement_level.censored_measurement` can be
*less* than the true count of censored rows in the raw file. See the
worked example below for the exact real numbers this produced.

## Example report walkthrough (real hERG numbers, 2026-08-26 run)

```json
{
  "funnel": {
    "raw_records": 17097,
    "valid_structures": 17034,
    "invalid_structures_quarantined": 0,
    "mixtures_excluded": 63,
    "standardized_entities": 14107,
    "unit_resolved_records": 17096,
    "unit_unresolved_records": 1,
    "license_resolved_records": 17097,
    "license_unresolved_records": 0,
    "exact_duplicate_records_collapsed": 48,
    "conflict_consistent_compounds": 9589,
    "conflict_discordant_compounds": 148,
    "training_eligible_compounds": 9589,
    "training_ineligible_compounds": 4518
  },
  "exclusion_reasons": {
    "measurement_level": { "bad_validity_comment": 8, "censored_measurement": 5060, "mixture": 63 },
    "compound_level": { "discordant_gt_10x": 148, "no_usable_measurements": 4370 }
  },
  "quality_score_distribution": { "mean": 0.7965, "median": 1.0, "min": 0.35, "max": 1.0 }
}
```

Reconciling this by hand:

- `17034 + 0 + 63 = 17097` ✓ (every raw record accounted for)
- `9589 + 148 + 4370 = 14107` ✓ (every standardised entity accounted for:
  training-eligible + discordant + insufficient-data)
- The raw CSV actually has 5,089 censored rows and 8 bad-validity-flagged
  rows, not 5,060 — the difference (29) is rows that are *also* part of a
  mixture-flagged molecule, counted once under `mixture` instead. Confirmed
  directly: of the 63 mixture-excluded rows, 29 are censored.
- **Cross-checked independently against `build_dataset.py`'s own manifest**:
  `conflict_discordant_compounds` (148) matches
  `herg_inhibition_dataset_manifest.json`'s `discordant_entities_excluded_count`
  exactly. `training_eligible_compounds` (9589) matches its
  `final_compound_count` exactly. `mixtures_excluded` (63) does **not**
  match its `mixtures_excluded_count` (27) — explained in `README.md`'s
  known limitations: this pipeline finds 27 *more* mixture-flagged
  molecules that `build_dataset.py` structurally never sees (every one of
  their measurements is censored, so `build_dataset.py` filters them out
  before it ever checks their structure).

`tests/integration/test_curation_real_data.py` runs this reconciliation
automatically, on the real committed raw data, so it can't silently drift.
