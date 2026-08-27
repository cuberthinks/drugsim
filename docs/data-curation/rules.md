# Curation rules

Every rule `drugsim_curation` applies, and exactly what each one does and
does not do. Where a rule reuses existing, already-correct policy
(`drugsim_quality.aggregation`, the license registry), this document
cross-references rather than restates the algorithm.

## Unit resolution

`drugsim_curation.units.resolve_unit`.

- **Molar concentration units** (`nM`, `uM`/`µM`, `mM`, `M`, `pM`) convert
  to nanomolar on a fixed, unambiguous multiplicative factor. Always
  `unit_status="resolved"`.
- **Mass-concentration units** (`ug/mL`, `mg/mL`, `ng/mL` and their
  `X.mL-1` spellings) require the compound's molecular weight to convert
  to a molar basis. If a molecular weight is available (from
  `drugsim_chem`'s computed descriptors), the conversion is applied and
  resolved; if not, `unit_status="unresolved"`.
- **Any other unit string, or an unparseable value**, resolves as
  `unresolved` with `conversion_status="unresolved_unknown_unit"`.
- **A measurement whose unit is unresolved is excluded from aggregation**
  (`exclusion_reason="unresolved_unit"` at the measurement level) — it is
  never guessed at, and never silently coerced.

Today, both live endpoints' ChEMBL queries filter to `standard_units=nM`
at the API level, so unit resolution is a no-op in practice
(`conversion_method="identity_nm_passthrough"` for every real record).
This module exists for the day a second, non-pre-filtered source is added
— see `current-state.md` §5 for why that's a real, if currently dormant,
gap this closes.

## Duplicate resolution

Two distinct mechanisms, at two distinct scopes:

- **Exact-duplicate measurements** (identical value + unit + relation +
  assay + document, within one compound):
  `drugsim_curation.ledger.find_exact_duplicate_measurements`. Both rows
  are kept — one tagged `duplicate_role="representative"`, the other
  `"duplicate"` — never merged into a single row and never deleted.
- **Structural and salt-equivalent duplicates** (different raw
  `molecule_chembl_id`s that standardise to the same `inchikey_full`):
  handled implicitly by grouping ledger rows on the *standardised*
  compound identity before aggregation — the same approach
  `build_dataset.py` already uses correctly. Not re-decided here.
- **Cross-source duplicates** (the same measurement reported by two
  different data sources): `drugsim_quality.dedup.find_measurement_duplicates`
  already implements this (matching on parent InChIKey + target/endpoint
  + literature reference), but neither live endpoint has a second source
  to exercise it against yet.

No duplicate is ever automatically merged into a single value just
because two structures look similar — see `current-state.md`'s original
audit for why that would be scientifically wrong (a salt form and its
free base are legitimately the same measurement target, but that is a
structural-identity decision, not a duplicate-detection heuristic).

## Conflict / discordance handling

Reuses `drugsim_quality.aggregation.aggregate_continuous` completely
unchanged: geometric mean for potency values, `value_spread_log10 > 1.0`
(>10x spread) is discordant. This is correct, existing policy — this
phase does not modify it.

**What this phase changes is what happens to a discordant result.**
`build_dataset.py` drops it (`if agg.is_discordant: continue`) — the
compound never appears in `datasets/processed/*.csv` at all, only counted
in a manifest field. `drugsim_curation.curated_view.build_curated_compound`
instead **retains** it: `training_eligible=False`,
`exclusion_reason="discordant_gt_10x"`, but with a real, inspectable
`aggregated_ic50_nm`, `value_spread_log10`, and `data_quality_score` —
visible for review, not silently absent.

A compound with **zero** usable measurements (every one excluded for some
other reason — censored, bad-validity-flagged, unresolved unit) gets
`conflict_status="insufficient_data"`, distinct from `"discordant"` — the
absence of usable data is a different finding from disagreement between
usable data.

## Training-eligibility gate

A compound is `training_eligible=True` only if:

1. It has a valid, non-mixture structure (implicit — only valid-structure
   compounds get a curated-compound row at all).
2. At least one measurement was usable (`n_source_measurements_used >= 1`).
3. The aggregate is not discordant.
4. The source's licence is resolved.

Note this is **narrower** than the original phase plan's draft, which also
required 100% of a compound's *candidate* measurements to have a resolved
unit. That would make a compound with 9 clean measurements and 1
unrelated bad-unit measurement ineligible for a reason unconnected to its
own aggregate — the unit-resolution shortfall is instead reflected
continuously in the quality score's `unit_resolution_rate` component
(below), not as a hard gate. This is a deliberate refinement made during
implementation, documented here rather than silently applied.

## Data-quality score

`drugsim_curation.quality_score.compute_quality_score` — a weighted sum,
every component real and inspectable:

| Component | Weight | What it measures |
|---|---|---|
| `structure_validity` | 0.25 | 1.0 if standardisation succeeded and it's not a mixture |
| `unit_resolution_rate` | 0.15 | Fraction of measurement *candidates* (valid structure, uncensored, not validity-flagged) with a resolved unit |
| `license_resolution` | 0.15 | Same candidate population, fraction with a resolved licence |
| `measurement_consistency` | 0.20 | 1.0 unless the aggregate is discordant (mirrors `aggregate_continuous`'s own >10x boundary) |
| `duplicate_resolution` | 0.10 | 1.0 today for both single-source live endpoints — see `README.md`'s known limitations |
| `assay_context_coverage` | 0.10 | Fraction of *used* measurements with a non-null organism or paradigm classification |
| `provenance_completeness` | 0.05 | 1.0 if at least one contributing measurement has a known publication year |

This is reported for **every** curated compound, including
training-ineligible ones — a discordant compound's score drops (mainly
via `measurement_consistency`) but is never omitted. "Don't hide discarded
data" applies to the score as much as to the row itself.

## Assay context

See `current-state.md` §7 and `README.md`'s known limitations for exactly
what's extracted (`assay_organism`, `assay_cell_type`, a genuine but
sparse `assay_tissue`, ChEMBL's own `assay_type` code, and this module's
own paradigm classification) versus genuinely unavailable
(`concentration`, `temperature`, `pH`, `exposure_duration`, `method`).

One correction made during implementation, worth flagging explicitly: an
earlier draft of this phase assumed `tissue` was structurally absent from
ChEMBL's assay records for these targets. Checking the real API directly
(not assuming) found `assay_tissue` populated for 4 of 4,829 hERG-target
assays — real, if rare. It is captured when present, and removed from the
"unavailable" list accordingly (`drugsim_curation.assay_context.ASSAY_CONTEXT_UNAVAILABLE_FIELDS`).

## Licence policy

`drugsim_curation.provenance.resolve_license` wraps
`drugsim_quality.license_audit.load_registry` and **fails closed**: a
source missing from `datasets/registry.yaml`, or missing `spdx`/`tier`/
`commercial_ok`, resolves as `license_status="unresolved"` — never
treated as permitted by default. Only entries under the registry's
`sources` (active) section can resolve; `excluded_sources` and
`deferred_sources` never do, even if they happen to have a well-formed
licence block.

## Provenance

Every curated compound carries `measurement_ids` — a semicolon-joined list
of every contributing raw measurement's deterministic `measurement_id`
(`"{source_dataset_id}:{activity_id}"`) — the per-record link back to raw
data that does not exist in today's `datasets/processed/*.csv` (see
`current-state.md` §10). `measurement_id` and `compound_id` are always
deterministic, never a random ID — the same raw input always produces the
same identifiers, a precondition for the golden-regression test actually
meaning anything.
