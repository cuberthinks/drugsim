# Data curation — current state (audit)

This document is the required first step of the data-curation phase: an
honest account of what already exists before anything new is built. It is
read-only in spirit — nothing here was changed to produce it, and no
pipeline behaviour changes as a result of writing it.

**Headline finding: this is not a greenfield build.** The repository already
contains a substantial, partially-built curation platform. There are two
parallel systems:

1. A fully-specified relational lakehouse design (Postgres + RDKit cartridge,
   immutable landing zones, 13 ADRs, Alembic migrations, 60+ DB constraint
   tests) that is schema-complete but has **never been populated with real
   bioactivity data**.
2. The two actually-live ADMET pipelines (hERG, CYP3A4) — standalone
   flat-file Python scripts that reuse some of the lakehouse design's shared
   libraries (`drugsim_chem`, parts of `drugsim_quality`) but bypass the
   DB/lakehouse entirely, and duplicate some logic between the two
   endpoints.

Any new curation work has to say explicitly which of these two systems it's
extending, because the same request ("add duplicate detection") means
different things depending on which one is targeted.

**Naming note**: `docs/phase11/` already exists, containing an unrelated
session report (reliability fixes, SHAP explainability, 2026-08-21). This
document intentionally lives at `docs/data-curation/` rather than
`docs/phaseN/` to avoid colliding with that existing phase number.

## 1. Repo layout

Top level: `datasets/`, `models/`, `docs/`, `src/` (Poetry package), `scripts/`,
`database/` (DDL + Alembic migrations), `etl/`, `frontend/`, `tests/`.

`src/` contains seven packages: `drugsim_chem`, `drugsim_core`, `drugsim_db`,
`drugsim_features`, `drugsim_ingest`, `drugsim_predict`, `drugsim_quality`.

ADRs (ADR-001 through ADR-012) live as prose inside
`docs/phase1/step2-data-architecture.md` §10, not as separate files. Only
ADR-013 (`docs/adr/ADR-013-poetry-and-ruff-format.md`) is a standalone file.
The ones most relevant to data curation:

| ADR | Decision | Actually implemented in the live pipelines? |
|---|---|---|
| ADR-007 | License tier as physical partition + per-record tag | No — designed (`dedup.py`'s `license_tier` field exists) but both live endpoints are single-source ChEMBL, so per-record tracking is never exercised. |
| ADR-009 | Global, once-assigned scaffold split groups | Yes, but reimplemented identically in both endpoints rather than shared (see §8). |
| ADR-012 | Harmonise units at ingestion; retain source value+unit verbatim | No — see §5. |

`docs/etl/` and Dagster (ADR-006's chosen orchestrator) are unfulfilled
scaffolding: `dagster` is not a dependency in `pyproject.toml`, and
`etl/assets`, `etl/gates`, `etl/sources` are empty directories.

`docs/data-curation/` did not exist before this document. `docs/benchmarks/`
is the closest existing precedent for tone/structure (precise citation
tables, explicit "what has and hasn't been done" framing, every figure
traced to a checked-in source file) and this document follows that style.

## 2. Raw data immutability

**Already implemented, and matches the requested `raw/ → processed/`
separation.** `datasets/raw/` holds the untouched ChEMBL pulls plus a
manifest sidecar per file:

- `chembl_herg_ic50_raw.csv` (17,098 rows) + `chembl_herg_ic50_manifest.json`
- `chembl_cyp3a4_ic50_raw.csv` (12,358 rows) + `chembl_cyp3a4_ic50_manifest.json`
- `pubchem_aid588834_raw.csv`, `tdc_cyp3a4_veith_raw.tsv` — external-validation
  sources only, not used for training.

`models/admet/{herg_inhibition,cyp3a4_inhibition}/fetch_chembl_data.py` fetch
directly from ChEMBL's REST API and write raw CSV + manifest (query params,
retrieval date, output SHA-256) — a re-run overwrites the file wholesale,
it is never edited in place.

**Gap**: `src/drugsim_ingest/` implements a generic, unit-tested "immutable
landing zone" abstraction (S3/MinIO, write-once enforcement, snapshot IDs)
per ADR-001/ADR-011. Neither fetch script imports it — both write directly
to local `datasets/raw/*.csv` with plain file I/O. The generic
infrastructure exists but is unused.

There is also one stray artifact worth noting: `data/cyp3a4_veith.tab` at
the repo top level is a saved HTTP 403 error page from a failed download,
not real data, and is referenced by nothing.

## 3. Chemical standardisation

**Already implemented as a single canonical pipeline, used identically by
both endpoints — no duplication or inconsistency here.**

- `src/drugsim_chem/parsing.py::parse_molecule()` — two-stage parse (raw
  parse, then explicit `Chem.SanitizeMol`) so failures produce a real RDKit
  diagnostic rather than a bare `None`.
- `src/drugsim_chem/standardize.py::standardize()`
  (`STANDARDIZATION_PIPELINE_VERSION = "v1"`) — cleanup/normalize, then
  **custom** salt/fragment classification (`classify_fragments`), then
  charge neutralization, then canonical tautomer computed (kept alongside
  the original, never substituted in place). The salt-stripping logic is
  deliberately not RDKit's built-in `FragmentParent`/`LargestFragmentChooser`
  — the module's own docstring explains those pick an arbitrary parent for
  plain-salt and genuine-mixture cases; `classify_fragments()` instead:
  single organic parent → strip; all fragments are salts (e.g. plain
  NaCl) → keep the whole structure; ≥2 non-salt fragments → flag
  `is_mixture=True`, no further processing.
- `src/drugsim_chem/identity.py::compute_identity()` — canonical/isomeric
  SMILES, InChI, InChIKey (full + skeleton), Bemis-Murcko scaffold,
  stereocentre counts, Hill formula.
- `src/drugsim_chem/pipeline.py::process_structure()` — the single
  documented entry point tying parse → standardize → identity → descriptors
  together.

Both `models/admet/{herg,cyp3a4}_inhibition/build_dataset.py` and
`prepare_features.py` import from `drugsim_chem` directly — no
reimplementation. Idempotency is a tested property
(`tests/unit/test_chem_standardize.py::TestIdempotency`).

**Conclusion: do not rebuild this. It already satisfies the spec's
Section 3 requirements (salts, charges, stereochemistry, aromaticity,
explicit/implicit hydrogens, disconnected fragments, invalid structures,
versioned).**

## 4. Duplicate detection

`src/drugsim_quality/dedup.py` provides two functions:

- `find_compound_duplicates()` — exact `inchikey_full` match; duplicates are
  merged (all source IDs retained, a deterministic representative chosen),
  never deleted.
- `find_measurement_duplicates()` — cross-*source* dedup (designed for e.g.
  ChEMBL vs BindingDB overlap): matches on
  `parent_inchikey + target_or_endpoint [+ reference]`.

**Neither is called by the live build pipelines** — only by
`tests/unit/test_dedup.py` and `scripts/generate_quality_report.py` (run
against the small golden compound set, not real bioactivity data). This
makes sense for `find_measurement_duplicates` specifically: both live
endpoints have exactly one source (ChEMBL), so cross-source dedup has
nothing to do. But the live pipelines still need *intra-source* duplicate
handling for repeated measurements of the same compound, and they get it a
different way: `build_dataset.py` groups raw activity rows by
`inchikey_full` into an entity's `values_nm` list, which is then fed to
aggregation (§6) rather than to `dedup.py`. This is a real but narrower
gap than "no duplicate detection exists" — the exact-InChIKey case is
handled inline; the *fuzzy/structural* duplicate case (`find_compound_duplicates`,
salt-equivalent structures) exists as a library function but has never been
run against the real datasets.

## 5. Unit handling

Both ChEMBL fetch scripts constrain the API query itself to
`standard_units: "nM"` — so **no multi-unit data ever enters the live
pipelines**, and no conversion is exercised in practice. The processed CSVs
store one column, `aggregated_ic50_nm`; no per-record original-unit field
survives past the raw CSV (which does have a `standard_units` column, but
it has no diversity to preserve since the query already filtered it).

This is a real, direct gap against **ADR-012** ("harmonise units at
ingestion; retain source values verbatim" — every measurement should carry
both `source_value`/`source_unit` and a `canonical_value`/`canonical_unit`
plus the conversion method applied). The DB schema may express this at the
table level (`database/migrations/versions/0013_measurement_aggregate.py`),
but the live flat-file pipelines implement a single-unit passthrough, not
conversion-with-provenance.

A related but distinct piece already exists: `src/drugsim_quality/unit_verification.py`
— empirical *verification* that an assumed unit/scale is plausible
(`verify_range`: literature envelope check; `verify_skewness_consistent_with_log_scale`;
`verify_reference_compounds`: catches sign-inversion errors). This answers
"is this unit probably right?", not "what unit is this and how do I convert
it?" — and like `dedup.py`, it is unit-tested but not called by either live
pipeline.

**Conclusion: there is currently no live code path that would let a record
be marked `unit_status = unresolved` per the spec, because there is no
per-record unit field at all today.** This is a genuine, concrete gap to
fill — though a narrow one in practice today, since the ChEMBL-only sources
are pre-filtered to nM. It becomes load-bearing the moment a second,
non-ChEMBL source is added.

## 6. Conflict / aggregation handling

**Already implemented and wired into both live pipelines** —
`src/drugsim_quality/aggregation.py::aggregate_continuous()`, imported and
called directly (e.g. `cyp3a4_inhibition/build_dataset.py:152`,
`agg = aggregate_continuous(entity["values_nm"], is_potency=True)`).

- **Geometric mean** for potency values (`10 ** mean(log10(values))`) —
  documented rationale: potency is log-normally distributed, arithmetic mean
  overweights the high-value tail. (Median exists as a branch for
  `is_potency=False`, but neither live endpoint uses it — both are
  potency-based.)
- **Discordance**: `value_spread_log10 > 1.0` (>10x spread) →
  `is_discordant = True`.
- **What happens to discordant entities today**: they are **excluded from
  the processed dataset entirely** —
  `if agg.is_discordant: discordant_count += 1; continue`. Confirmed via the
  build manifests: hERG excluded 148 discordant entities, CYP3A4 excluded 97
  (`datasets/processed/{herg,cyp3a4}_inhibition_dataset_manifest.json`,
  key `discordant_entities_excluded_count`).

This is the single most important gap relative to the new spec's Section 6,
which asks that conflicting measurements be **flagged for a separate
resolution layer**, not silently dropped. Today's behaviour is disclosed
(the exclusion count is in the manifest) but not preserved — a discordant
entity's individual measurements are not written anywhere with a
`conflict_status` a person could later review and resolve; they are simply
absent from the output. The raw activity rows that produced a discordant
aggregate still exist in `datasets/raw/*.csv`, but nothing links a specific
discarded `local_compound_id` back to which raw `activity_id`s conflicted —
reconstructing that link today would require re-running `build_dataset.py`'s
own grouping logic by hand.

The processed CSV's `n_source_measurements` / `n_source_chembl_ids` columns
do carry forward *how many* measurements were aggregated (and how many
distinct ChEMBL molecule/salt-form records collapsed into one InChIKey), but
not their individual values, units, or sources.

## 7. Assay context

**Not preserved in the processed datasets.** Neither `herg_inhibition_dataset.csv`
nor `cyp3a4_inhibition_dataset.csv` carries organism, cell type, tissue,
assay type, temperature, pH, or exposure duration. The raw CSV does have
`assay_type` / `assay_chembl_id` / `data_validity_comment` columns, but only
`data_validity_comment` is used (as a build-time filter) — none of them
survive into the processed output.

One relevant investigation already happened:
`models/admet/herg_inhibition/audit_assay_heterogeneity.py` (Phase 3.5) is a
read-only, one-off script that bulk-fetches assay metadata
(`assay_organism`, `assay_cell_type`, `confidence_score`, `bao_label`) and
classifies binding-vs-functional assay paradigms, reporting whether the
pooled dataset mixes non-comparable assay types. Its own docstring states it
does not modify the dataset, model, or aggregation policy — the finding
lives only in `docs/phase3/phase3.5-scientific-audit.md` as a static report,
not as a structural safeguard.

## 8. Train/test splitting (ADR-009)

Implemented, but **duplicated rather than shared**: both
`models/admet/herg_inhibition/prepare_features.py` and
`.../cyp3a4_inhibition/prepare_features.py` contain a byte-for-byte
identical `_split_group()` function (SHA-256 of `scaffold_key||SPLIT_SALT`
mod 10), differing only in the per-endpoint salt string. Groups 0–6 train,
7 calibration (reserved, unused), 8 validation, 9 test. Split groups are
written into the `.npz` feature archives, not the processed CSVs.

The DB-level version of this (`compound_split_assignment` table,
`uq_scaffold_single_group` constraint) exists as schema but is unpopulated —
confirmed in `docs/phase2/phase2-completion-report.md` ("ADR-009
leakage-prevention machinery is schema-ready but unused").

This duplication is low-risk (the logic is simple and identical today) but
is exactly the kind of thing that silently diverges if one endpoint's copy
is ever edited without the other. Worth extracting to a shared utility as
part of curation-engine cleanup, though it isn't a correctness gap today.

## 9. License tracking

`datasets/registry.yaml` (523 lines) is the single normative registry.
Per-source schema: `source_id`, `name`, `homepage`, `role`,
`ingestion_wave`, upstream version/dates, `retrieval`, a `license` block
(`spdx`, `tier`, `commercial_ok`, `sharealike`, `attribution`, and for mixed
sources `split_licensing`/`exclusions`), `cadence` (staleness tracking),
`scale` (the count fields — this is where ChEMBL's `distinct_compounds`,
`activities`, `assays`, `targets` live), `verification` (status/date/method),
`notes`. Three sections: 9 active `sources`, 4 `excluded_sources` (DrugBank,
FreeSolv, PDBbind, SIDER, each with a reason), 9 terse `deferred_sources`.

License is tracked **per-source in the registry**, with an explicit
`MIXED`/`split_licensing` mechanism for internally-split sources (e.g.
BindingDB: CC BY 3.0 for its own curation vs CC BY-SA 3.0 for the
ChEMBL-derived portion — registry.yaml calls this out as "THE reason
per-record license tracking is mandatory," referencing ADR-007). **No
license column exists in either processed CSV** — both live endpoints are
single-source ChEMBL (one license, CC-BY-SA-3.0), so per-record tracking
isn't exercised in practice, even though `dedup.py`'s `MeasurementRecord`
already has a `license_tier` field designed for exactly this.

Audit tooling already exists and runs as a **required CI gate**:
`src/drugsim_quality/license_audit.py::audit_registry()` (rules LC-01…LC-06)
+ `build_attribution_manifest()`, invoked via `scripts/audit_licenses.py`,
producing the auto-generated `docs/legal/attribution-manifest.md`. It audits
the registry, not per-record data — there is nothing today that would flag
an individual curated record as licence-unresolved, because no pipeline
currently produces per-record licence fields to check.

## 10. Provenance tracking

`herg_inhibition_dataset.csv` and `cyp3a4_inhibition_dataset.csv` have
identical 14-column schemas:

```
local_compound_id, inchikey_full, canonical_smiles, standardized_smiles,
bemis_murcko_scaffold, molecular_formula, n_source_measurements,
n_source_chembl_ids, aggregated_ic50_nm, value_spread_log10, label,
source_chembl_ids, source_document_years, molecule_pref_names
```

No dataset-version, retrieval-date, or license-tier column lives inside the
CSV itself — those are one level up, in the build manifest sidecar
(`datasets/processed/{herg,cyp3a4}_inhibition_dataset_manifest.json`):
`dataset_id`, `dataset_version`, `endpoint`, `built_at`, `source_manifest`
(path + `output_sha256` + `retrieval_date`, pointing back to the raw
manifest), `filtering_rules`, `aggregation_method`,
`discordant_entities_excluded_count`, `final_compound_count`,
`label_distribution`, `output_sha256`.

So: provenance is real and checksum-chained from raw → processed at the
**file level**. What's missing is **record-level** traceability: nothing
says "this specific curated row came from these specific raw
`activity_id`s." `source_chembl_ids` records which ChEMBL *molecule* IDs
(salt-form variants) collapsed into this compound, but not which raw
*activity/measurement* rows fed the aggregate.

## 11. Existing quality checks / tests

Extensive unit-test coverage of the **library functions** in isolation:
`tests/unit/test_dedup.py`, `test_aggregation.py` (including
`TestDiscordanceIsNeverSilentlyResolved`), `test_unit_verification.py`,
`test_license_audit.py` (including one test against the real committed
registry), and thorough chemistry-pipeline tests
(`test_chem_standardize.py`, `test_chem_identity.py`, `test_chem_parsing.py`,
`test_chem_descriptors.py`, `test_chem_fingerprints.py`,
`test_chem_drug_likeness.py`, including idempotency/determinism checks).

`tests/golden/test_golden_regression.py` regression-tests the *chemistry*
pipeline against `datasets/golden/compounds.csv` — 28 compounds, columns
`name,smiles,category,note`, categories including salts, stereoisomers, and
invalid structures. This is a structure-standardization golden set, not a
measurement/label golden set — it has no compound-property labels,
conflicting-measurement examples, or unit edge cases.

`tests/constraints/*` (60+ DB-level tests) only run against a real
Postgres+RDKit instance, which per `docs/phase2/phase2-completion-report.md`
has never actually been exercised in CI.

Two standalone (non-pytest) ad hoc audit scripts check the real datasets:
`models/admet/cyp3a4_inhibition/data_quality_audit.py` (checks for
non-positive/NaN/absurd `aggregated_ic50_nm`, missing scaffold, duplicate
InChIKeys — writes a JSON report, not part of the test suite) and the
Phase 3.5 assay-heterogeneity script (§7).

**Confirmed gap: no test in the normal pytest suite runs against the live
processed datasets (`herg_inhibition_dataset.csv` /
`cyp3a4_inhibition_dataset.csv`) at all** — no schema-conformance check,
no duplicate-ID check, no valid-SMILES check runs as part of `make test` or
CI today. This is a genuine, clean gap the new phase should fill.

## 12. Summary: what genuinely needs building

Given the above, the remaining work is narrower than "build a curation
pipeline from scratch." What's missing, specifically:

1. **A per-record provenance/conflict ledger** — today's provenance and
   conflict handling both live at the file/manifest level; there is no
   artifact that records one row per raw measurement with
   `measurement_id, compound_id, source, value, unit, assay_context,
   conflict_status`.
2. **A resolution layer for discordant measurements** — today they are
   excluded and counted, not preserved for review.
3. **Per-record unit status** — no per-record unit field exists at all
   today; `unit_status` has nothing to attach to without one.
4. **A composite, explainable data-quality score** — components exist
   individually (valid structure, license tier, duplicate status,
   discordance) but nothing combines them into one transparent score today.
5. **An extended golden dataset** — the existing one covers chemistry edge
   cases well; it has no conflicting-measurement, unit-ambiguity, or
   known-toxic/non-toxic-control examples at the measurement level.
6. **A curation report generator** and **pytest-based data-quality tests
   against the live processed datasets** — both currently absent.

What should **not** be rebuilt: chemical standardisation (§3), the
geometric-mean/discordance aggregation policy itself (§6, correct as
designed — the gap is what happens *after* discordance is detected, not the
detection logic), the license registry and its audit gate (§9), or the
scaffold-split methodology (§8, works, just duplicated).

**Nothing in this document changes any pipeline's behaviour, any dataset
file, or any model.** It is investigation only.
