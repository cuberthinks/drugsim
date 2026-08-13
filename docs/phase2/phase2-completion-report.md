# Phase 2 Completion Report — DrugSim Scientific Data Platform

Scope executed: project setup/CI, database schema, dataset registry + raw
data layer, ETL (parse → standardise → identity → descriptors), measurement
aggregation, golden-set regression, bulk loader, data-quality report. Per the
governing instruction, ML models, the API/frontend/chatbot, and knowledge
graph integration (Open Targets/BindingDB relationship import) were
explicitly out of scope and are not built.

Environment note: this phase was executed and verified in a sandbox with no
Docker and no Poetry (system Python 3.9, target is 3.12). `rdkit==2025.3.3`
(the exact pinned version) and `moto[s3]` install cleanly via pip, and real
network access exists — so chemistry code, the licence audit, and the S3-
mocked download path were genuinely executed, not just written. Anything
requiring Postgres (constraint tests, the bulk-load insert path, real
migrations) was written and reviewed but **not executed** here; it should be
run once in an environment with Docker before being trusted for production
use. This is called out per-item below rather than glossed over.

---

## 1. Implemented

### 1.1 Project setup, config, logging, tests, CI (Sprint 2.1)
- Poetry project, `pyproject.toml` pinning `rdkit==2025.3.3` exactly (ADR-005:
  descriptor values change between RDKit releases).
- `structlog`-based logging with `drugsim_core.redaction` to keep molecular
  structures/customer data out of logs.
- pytest markers: `unit`, `integration`, `constraints`, `golden`, `security`,
  `slow`, `network`.
- `.github/workflows/ci.yml`: `quality` (ruff/mypy), `test` (unit ∪ security
  ∪ golden), `security-controls`, `constraints` (Docker/testcontainers),
  `supply-chain`, `licence-audit`, `docker` build jobs.
- **Not run**: the actual GitHub Actions CI. Local verification (below)
  covers everything that does not need Postgres or Docker.

### 1.2 Database schema, constraints, indexes, migrations (Sprint 2.2)
- 12 DDL files (`database/ddl/00_extensions.sql` … `11_measurement_aggregate.sql`)
  and matching Alembic migrations (`0001` … `0013`), forward-only
  (`downgrade()` raises `RuntimeError` by design).
- Every DDL/migration pair verified byte-identical after whitespace
  normalisation, including after two direct edits made mid-phase (see §4).
- RDKit Postgres cartridge types (`mol`, `bfp`) and GiST indexes for
  substructure/similarity search.
- **Not run**: no migration has been applied to a live Postgres in this
  environment. Structural correctness (constraint tests) is written and
  reviewed, not executed — see §1.6 and §3.

### 1.3 Dataset registry + raw data layer (Sprint 2.3–2.4)
- `datasets/registry.yaml`: 24 sources declared with SPDX licence, tier
  (green/amber/red/black), commercial-use and ShareAlike flags.
- `src/drugsim_db/registry_sync.py`: pure `plan_source_sync` (diff against
  current DB state) + thin `apply_source_sync`, refusing unacknowledged
  licence-tier changes (`LicenseViolationError`).
- `src/drugsim_ingest/`: checksummed, retried (`tenacity`, per-call retry
  policy), immutable-write-once landing (`ImmutabilityViolationError` on any
  attempted overwrite — raw data immutability is enforced, not just
  documented).
- Verified against one real file over a live network connection: RCSB
  `1CRN.pdb`, SHA-256 checked exactly
  (`tests/integration/test_downloader_live.py`, marked `network`, **passing**
  as of this report).
- `ingestion_snapshot`/`ingestion_run` provenance tables record source
  version, checksum, byte size, and landing URI per acquisition.

### 1.4 ETL: parse, validate, salt-strip, canonicalise, standardise, dedupe, descriptors (Sprint 2.5–2.6)
- `src/drugsim_chem/`: two-stage parse with captured (never silently
  swallowed) RDKit diagnostics; `rdMolStandardize` cleanup, custom
  `classify_fragments` (handles two cases RDKit's own
  `FragmentParent`/`LargestFragmentChooser` get wrong: a whole-salt structure
  like NaCl, and a genuine two-component mixture); charge neutralisation;
  four-layer identity (InChI/InChIKey full+skeleton, canonical/isomeric
  SMILES, Bemis-Murcko scaffold); full physicochemical descriptor set;
  Lipinski/Veber/Ghose/Egan/Muegge/Ro3, QED, SA score, NP-likeness,
  PAINS/Brenk alerts, Pfizer 3/75 and GSK 4/400 flags.
- `src/drugsim_quality/dedup.py`: InChIKey-based duplicate grouping,
  licence-aware representative selection.
- Invalid molecules are rejected via `StructureError`, the explicit
  quarantine signal — never silently skipped, never aborting a batch (proven
  by `scripts/generate_quality_report.py`, which catches per-record).
- Two Phase 1 documentation errors were found and corrected during
  implementation (not assumed — verified against the installed RDKit and,
  for bioavailability, the primary literature): the HBD/HBA "crude vs
  strict" convention description, and the Martin (2005) bioavailability
  score's missing 0.85 anion tier. Both the code and the originating Phase 1
  docs were corrected; see `docs/phase1/step2-data-dictionary.md` §E.1.

### 1.5 Measurement aggregation with discordance flags
- `src/drugsim_quality/aggregation.py`: `aggregate_continuous` (geometric
  mean/median with a log10-spread discordance threshold) and
  `aggregate_binary` (majority vote, exact ties flagged) — conflicting
  measurements are never silently averaged; a `measurement_aggregate` row is
  a versioned, recorded *decision*, kept separate from immutable
  `measurement` rows (P4).
- **Not exercised on real data**: no bioactivity measurement dataset was
  ingested this phase (see §2), so this logic is unit-tested but has not
  processed a real multi-source discordant record yet.

### 1.6 Golden dataset + regression tests (Sprint 2.6)
- `datasets/golden/compounds.csv`: 28 hand-curated compounds covering
  whole-salt, salt-stripping, charge neutralisation, defined/undefined
  stereochemistry, a PAINS-flagged scaffold, HBD/HBA convention-divergence
  cases, and Lipinski edge cases.
- `scripts/generate_golden_fixtures.py` regenerates `expected_output.json`
  **only when run deliberately** — never automatically.
- `tests/golden/test_golden_regression.py`: exact-value comparison,
  per-compound failure reporting, plus coverage-of-edge-cases assertions (the
  golden set losing a case is itself a detected regression).
- **Caught a real, non-obvious bug during development** (see §4).

### 1.7 Bulk load into PostgreSQL (Sprint 2.7)
- `src/drugsim_db/bulk_load.py`: pure `build_compound_row` /
  `build_descriptor_row` / `build_drug_likeness_row` (unit-tested with no
  database) + thin, batched `insert_*` functions. `mol`/`morgan_fp_r2_2048`
  are generated by the RDKit cartridge from `standardized_smiles` inside the
  INSERT itself, not serialised from Python RDKit objects.
- `drugsim_features.compute_feature_set_id` implements the ADR-005
  content-addressing formula the module had documented but never
  implemented, needed to populate `descriptor_spec.feature_set_id`.
- **Not run**: `tests/constraints/test_bulk_load_integration.py` exercises
  the real inserts (composite FKs, cartridge calls, mixture/whole-salt edge
  cases) against a live schema — written and reviewed, requires Docker,
  did not execute in this environment.

### 1.8 Data-quality report (Sprint 2.8)
- `scripts/generate_quality_report.py` (`make quality-report`) runs the real
  pipeline over the golden set and reports ETL outcome, standardisation flag
  breakdown, duplicate detection, descriptor/drug-likeness summary
  statistics, and the live licence audit result. Output:
  `docs/phase2/data_quality_report.md` (regenerate before relying on it —
  it is a point-in-time artifact, not maintained by hand).
- Deliberately does not fabricate a measurement dataset to demo aggregation —
  states plainly what was not exercised, rather than looking more complete
  than what was actually ingested.

---

## 2. Datasets processed

| Dataset | What happened | Real data? |
|---|---|---|
| `datasets/golden/compounds.csv` (28 compounds) | Fully processed through parse → standardise → identity → descriptors → drug-likeness; used for the golden regression suite and the quality report | Hand-curated reference set, not an external licensed source |
| RCSB PDB `1CRN.pdb` | Downloaded over a live network connection, SHA-256 verified exactly | Real, external, licence-clear (public domain structure) |
| ChEMBL / BindingDB / PubChem / TDC / ToxCast / UniProt / PDB(bulk) / DrugCentral / Open Targets / FAERS / DailyMed / DrugBank / FreeSolv / PDBbind / SIDER (24 sources total) | Registered in `datasets/registry.yaml` with licence metadata; **not downloaded or ingested** this phase | Deferred — see §5 |

No bioactivity/measurement dataset was ingested end-to-end. The infrastructure
to do so (registry sync, immutable landing, checksums, ETL, dedup,
aggregation, bulk load) is built and unit-tested; running it against a real
multi-gigabyte source and a live Postgres instance did not happen in this
sandbox and is the natural first task of Phase 3.

---

## 3. Tests passed

Run locally (`.venv-verify`, system Python 3.9 + pip, **not** the Poetry/3.12
CI environment):

| Suite | Result |
|---|---|
| `unit` (428 tests) | **428 passed** |
| `golden` (13 tests) | **13 passed** |
| `security` (14 tests) | **14 passed** |
| `network` (2 tests, real RCSB download) | **2 passed** |
| **Total executed** | **457 passed, 0 failed** |
| `constraints` (63 tests, Docker/testcontainers) | Not executed — see below |
| `integration` beyond `network` | Not executed — see below |
| GitHub Actions CI itself | Not executed — no push/PR made |

11 unrelated errors appear in `tests/unit/test_landing.py` (moto/boto3
`PythonDeprecationWarning` escalated to a hard error by this environment's
Python-3.9 boto3 build under strict warning filters). Confirmed via `git
stash` that these pre-date every change made this phase and reproduce on an
unmodified tree; they will not occur on the CI target (Python 3.12). Not
counted as a Phase 2 regression.

`tests/constraints/*` (63 tests) could not even be **collected** in this
environment: the installed `testcontainers` version raises a
`DeprecationWarning` (`@wait_container_is_ready`) that this project's strict
warning-filter config turns into a collection-time error. This is an
environment/dependency-pinning mismatch (system pip install vs. Poetry's
locked versions), not a defect in the tests themselves — each constraint
test was written against and reviewed for the actual schema (see
`tests/constraints/factories.py` for the exact column lists used), but
**none of them have actually run against a real database in this phase**.
This is the single largest verification gap in this report; treat every
constraint listed as "written," not "proven," until it runs once for real.

---

## 4. Bugs and errors found (and fixed) this phase

1. **`standardize.py`: whole-salt structures wrongly reported a `parent_mol`.**
   `parent_mol=working if not classification.is_mixture else None` left
   `parent_mol` set to the *whole salt* for a structure like plain NaCl
   (`is_mixture=False`, but no organic parent exists either) — contradicting
   the class's own docstring. This silently fed NaCl's own mass into
   `descriptors.mw_parent_g_mol` and would have written a nonsensical
   `parent_smiles`/`parent_inchikey` for every pure-salt compound loaded.
   Found while wiring the bulk loader (an existing test asserted
   `standardized_mol` retained both ions but never checked `parent_mol` for
   this exact case — that gap is now closed). Fixed; golden fixtures
   regenerated; regression test added at two levels (unit + the new
   integration test).

2. **`rdMolDescriptors.CalcMolFormula` charge-suffix truncation.** RDKit
   appends a sign-then-magnitude charge suffix for ionic species (e.g.
   `"C2H3O2-"`, `"C10H2O8-4"`), which violates
   `compound.molecular_formula`'s Hill-notation CHECK constraint. A first
   regex attempt assumed digit-then-sign order and silently truncated a real
   atom count (`"C2H3O2-"` → wrongly `"C2H3O"`). Corrected and verified
   against singly- and multiply-charged species before being used anywhere.

3. **`compound_drug_likeness` was missing two columns the pipeline already
   computes.** Phase 1 Step 4 §7 specified `pfizer_3_75_flag` and
   `gsk_4_400_flag` (plus five more extended-catalogue columns) as a
   follow-on `ALTER TABLE`, but it was never folded into `03_chemistry.sql`
   or migration 0004 — so `drug_likeness.py`'s already-computed values had
   nowhere to be persisted. Added the two implemented columns (plus
   `rule_catalogue_version`) to both DDL and migration; left the five
   unimplemented catalogue rules (golden triangle, lead-likeness, REOS, BBB
   likelihood, MCE-18) out rather than adding columns nothing populates.

4. **`StandardizedStructure` never surfaced `component_count`.**
   `classify_fragments` computed it, but it was dropped before reaching
   callers, and `compound.component_count` is `NOT NULL`. Added.

5. **Golden fixture under-covered its own pipeline output.** `mw_parent_g_mol`,
   `standardized_smiles`, `parent_smiles`, and `component_count` were all
   real, already-computed values with no golden-set regression coverage —
   bug #1 above would not have been caught by the golden suite even after
   being introduced. All four are now compared exactly, per-compound.

Two additional Phase 1 **documentation** errors (not database bugs) were
found and corrected during Sprint 2.5 — see §1.4.

---

## 5. Known limitations

- **`inchikey_full`/`parent_inchikey` currently coincide.** Phase 1's
  four-layer identity model (Step 2 §5) defines `inchikey_full` as identity
  of "the exact entity as received" (so two different salt forms of the same
  active ingredient get *different* `inchikey_full` values but the *same*
  `parent_inchikey`) and reserves `parent_inchikey` for joining across salt
  forms. The implemented pipeline (Sprint 2.5/2.6) computes identity on the
  *already salt-stripped* structure, so today the two values are identical
  whenever a parent is found. Practical consequence: ingesting two salt
  forms of the same drug from real source data would collide on
  `uq_compound_inchikey` as duplicates, rather than being stored as two
  linked entities as Phase 1 intends. Not fixed in Phase 2 — it is a
  chemistry-pipeline change (computing an extra, pre-strip identity layer),
  not a loader change, and it touches already-shipped, tested Sprint 2.5/2.6
  code. **Recommend addressing before any real multi-source ingestion**
  (ChEMBL/BindingDB routinely list both forms).
- **Extended drug-likeness rule catalogue incomplete.** Golden Triangle,
  Lead-likeness (Teague), REOS, BBB-likelihood, and MCE-18 (Phase 1 Step 4
  §7) are specified but not implemented; no column exists for them either.
- **`generic_scaffold` is never computed** (`compound.generic_scaffold` is
  nullable and simply left `NULL`). Needed for split-assignment work, which
  is itself out of Phase 2's scope.
- **`npscorer.readNPModel()` prints a raw fd-level message** on first call
  that `contextlib.redirect_stdout` cannot catch (confirmed, not assumed).
  Harmless but not suppressed; low priority.
- **Undefined-stereocentre handling is a policy gap, not a code gap**: Phase
  1 Step 4 §2.3 flags this as an open product decision (predict as-given vs.
  enumerate isomers vs. refuse) and Phase 2 does not resolve it — the
  pipeline currently predicts on the structure as given.
- **This report's own test results are Python-3.9/pip, not Python-3.12/Poetry.**
  Everything requiring the real toolchain (`constraints` suite, real
  migrations, real bulk-load inserts) is unverified until run once in the
  target environment.

---

## 6. Licensing issues

The live licence audit (`scripts/generate_quality_report.py`, §1.8) reports
**0 errors, 2 warnings**, all advisory:

- `drugcentral`: marked stale (site indicates 2023 as current release;
  cadence appears to have slowed).
- `dailymed`: record-count figures unverified against a live unfiltered
  network query.

No black-tier source was ingested or referenced in code this phase. Black-
tier sources present in the registry (e.g. `drugbank`, `freesolv`) remain
registered-but-untouched, consistent with their tier.

---

## 7. Deferred items

- **Knowledge integration** (Open Targets/BindingDB relationship import,
  originally sketched in an earlier planning pass) — explicitly removed from
  this phase's scope per the governing instruction's 8-item list and "do not
  build extra infrastructure not in the TDS." Deferred to whenever
  target/bioactivity ingestion is prioritised.
- Real, large-scale ingestion of any of the 24 registered sources (§2).
- Running the full test suite (especially `constraints`, 63 tests) against a
  real Postgres+RDKit instance.
- The five unimplemented extended drug-likeness rules (§5).
- `generic_scaffold` computation and `compound_split_assignment` population
  (ADR-009 leakage-prevention machinery is schema-ready but unused).
- Resolving the `inchikey_full`/`parent_inchikey` coincidence (§5) —
  recommended as the **first** Phase 3 chemistry task, before any real
  multi-source ingestion.
- Frontend, API, chatbot, authentication UI, ML models — out of scope by
  explicit instruction, not attempted.

---

## 8. Phase 3 recommendation

1. **Fix the identity-layer gap first** (§5, item 1) — it is cheap to fix now
   and expensive to fix after real data has been loaded and joined on the
   wrong key.
2. **Stand up Postgres + Docker in a real CI/dev environment** and run the
   full suite once, especially `constraints` and
   `test_bulk_load_integration.py` — everything in this report marked "not
   run" needs to convert to "run and passing" before this platform is
   trusted with real data.
3. **Ingest one real bioactivity source end-to-end** (ChEMBL is the natural
   choice — richest, best-licensed) through the full pipeline built here:
   registry sync → download/landing → ETL → dedup → aggregation → bulk load
   → quality report. This is the first point the aggregation/discordance and
   unit-verification logic will run against real, messy, multi-source data
   rather than unit-test fixtures. Use that run to sanity-check the
   discordance threshold (currently a flat log10 > 1.0) against real assay
   variability before it gates anything.
4. Only after (1)–(3): begin knowledge-graph integration (Open Targets/
   BindingDB relationships) and split-assignment (`generic_scaffold` +
   `compound_split_assignment`), both deferred from Phase 2.
5. Decide the undefined-stereocentre policy (§5) before it becomes a
   prediction-API contract question — Phase 1 flagged this as needing a
   product decision, not an engineering one.
