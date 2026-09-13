# Changelog

All notable changes to DrugSim are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows SemVer.

Core DB releases are versioned separately as `core-db-vN.N.N` (Phase 1 Step 2 §7.2).

## [Unreleased]

### Deployed — Scientific Coverage upgrade live in production

- Commit `830fe7a` (identity skeleton-tier resolution, external
  generalisation + AD analysis for both endpoints, prediction-history
  statistics, compound-level error record, benchmark dataset transparency)
  deployed to `drugsim-predict-api` and `drugsim-frontend` on Render.
  Verified after deploy: clean single-boot startup (no restart signature),
  a real `/predict` request against the new instance resolved caffeine's
  identity via the skeleton/exact snapshot path and returned a complete
  reliability block, and memory settled at the known-safe ~403MB baseline
  (well under the 512MB Starter limit) — no Dockerfile, dependency, or
  model-artifact changes were part of this deploy, so this carries none of
  the OOM risk the psychiatric-screening attempts did.

### Improved — Scientific Coverage, Generalisation & Compound Intelligence

- Improved known-compound identity resolution: added an **unambiguous
  InChIKey-skeleton fallback tier** after exact full-InChIKey matching.
  Ambiguous skeletons (one connectivity block, several stereoisomers) resolve
  as `unidentified` rather than guessing between them, and skeleton matches
  are reported with a distinct `match_type` plus a fixed caveat that
  stereochemistry, isotopic labelling and protonation were not confirmed.
  **Measured gain: +0.16pp (hERG) / +0.32pp (CYP3A4) exact-match coverage.**
  This is explicitly *not* a fix for the coverage gap — see below.
- Added deeper external generalisation and failure-mode reporting for hERG:
  precision / specificity / recall / MCC / **PR-AUC** stratified by
  applicability-domain tier on 3,956 independent PubChem compounds, plus a
  threshold-sensitivity sweep. This metric family had not previously been
  reported per tier.
- Improved prediction-history transparency: history now retains and displays
  the conformal prediction set, singleton status, nominal confidence, both
  conformal p-values, the named uncertainty method and the predicted
  probability, with plain-language text stating a low p-value is evidence
  *against* a label and is not a significance test. History remains
  client-side `localStorage` only; no server-side per-user storage was added.
- New documentation set under `docs/scientific-coverage/` and reproducible
  read-only analyses under `scripts/scientific_coverage/`.

### Findings (no code change; recorded because they alter interpretation)

- **The hERG external "precision problem" is a base-rate effect, not model
  degradation.** On 3,956 independent compounds the model scores ROC-AUC
  0.865 (vs 0.784 internal), specificity 0.682 (vs 0.373 internal) and
  essentially unchanged MCC (0.327 vs 0.335). Precision falls to 0.218 only
  because prevalence falls from 61% to 9.4%.
- **The applicability domain is better validated than Phase 4.5 concluded.**
  That phase judged it "partially supported, not cleanly monotonic" using
  ROC-AUC, which is prevalence-insensitive across tiers ranging 44%→1%
  positive. By PR-AUC the gradient is monotonic (0.825 → 0.663 → 0.404 →
  0.131) and MCC collapses to 0.085 out-of-domain. Phase 4.5's stated
  conclusion should be updated.
- **Identity coverage is bounded by reference-set scope, not matching
  quality.** ~96% of independent public ChEMBL compounds cannot be named
  because the snapshot is seeded from compounds named in DrugSim's own
  hERG/CYP3A4 assay files. Doxorubicin is unidentifiable for this reason.

### Confirmed — CYP3A4 independently reproduces the base-rate finding

- Ran the same tier-stratified analysis on CYP3A4 against 12,161 genuinely
  external TDC `CYP3A4_Veith` compounds. **MCC is higher externally than
  internally (0.401 vs 0.356)** and specificity is again higher (0.612 vs
  0.405).
- The decisive comparison: precision loss scales with prevalence loss. hERG's
  base rate falls 85% (0.611 → 0.094) and precision falls 69%; CYP3A4's falls
  37% (0.667 → 0.419) and precision falls 21%. A degrading model would not
  scale its precision loss to each dataset's prevalence shift -- this is the
  signature of a base-rate effect.
- The applicability domain is monotonic here too (PR-AUC 0.956 → 0.767 →
  0.719 → 0.285; MCC 0.574 → 0.416 → 0.399 → 0.180), so the mechanism is now
  validated on **both** production endpoints.

### Verified — database constraint tests finally executed

- **The database constraint suite has been run for the first time: 75 tests,
  all passing**, against real PostgreSQL 16 + RDKit via testcontainers
  (63.2s). Phase 8, Phase 10 and the v1.0 blocker audit each recorded this
  suite as written-but-unexecuted for want of a Docker daemon; that gap is now
  closed and the guarantees are evidenced rather than asserted -- including
  scaffold-leakage prevention (ADR-009), `ck_not_predicted`, feature-set
  mismatch and ICH M7 methodology pairing.
- Two environment notes, recorded so the next runner does not lose time:
  the suite must currently be invoked with `-W ignore::DeprecationWarning`,
  because the installed `testcontainers` emits a deprecation at import that
  the project's warnings-as-errors policy escalates to a collection failure;
  and a `PytestUnraisableExceptionWarning` appears at teardown from a
  connection `__del__`. Neither is a DrugSim defect and neither failed a test,
  but both should be resolved rather than tolerated.
- Earlier documents refer to this suite as 63 or 67 tests; the current count
  is **75**.

### Improved — benchmark reproducibility metadata (Section 18)

- `Benchmark` entries now carry `randomSeed` (42, read from each endpoint's
  `train_manifest.json`) and a `preprocessing` block recording
  `standardizationPipelineVersion`, `descriptorSpecVersion` and
  `rdkitVersion` (2025.03.3) -- the toolchain identity a re-run must match for
  features to be comparable. `benchmarkId`, `datasetVersion`, `splitMethod`,
  `modelVersion`, `evaluationDate` and `sourceFile` already existed.

### Audited — no unsupported "more data" claims found (Section 17)

- Swept user-facing copy for claims that more data improves accuracy. **None
  found.** The Benchmark page already states the required distinction
  explicitly: *"a model trained on a few thousand labelled compounds is not
  the same claim as a database of millions of unlabelled bioactivity
  records."* No copy change was needed, so none was made.

### Improved — compound-level error record, dataset transparency, report reconciliation

- **Section 9 (model error analysis), completed.** Added
  `scripts/scientific_coverage/04_compound_level_errors.py`: a fixed-seed
  random sample (not a curated "worst offenders" list) of 15 false positives
  and 15 false negatives per endpoint (hERG, CYP3A4), each tagged with its
  real applicability-domain tier, chemical distance (max Tanimoto), dataset
  source, model version, and the single systematic explanation the earlier
  analysis found (base-rate/operating-point mismatch). Every row carries the
  same explanation deliberately — assigning different ones per compound
  without new evidence would itself be a fabrication.
  `03_cyp3a4_external_generalisation.py`'s cached pool was extended with each
  external compound's InChIKey (purely additive; re-ran and confirmed every
  aggregate metric is unchanged) so a compound could actually be identified
  in the sample — it previously had no identifier at all.
- **Section 15 (dataset transparency), completed.** `BenchmarkPage.tsx` and
  `lib/benchmarks.ts` now show, per endpoint: training/calibration/
  validation/test-set sizes (real counts from each `train_manifest.json`,
  summing exactly to the dataset total), a labelled primary metric and
  external metric, and the applicability-domain method summary — the exact
  field set Section 15 asks for. Explicit copy distinguishes the
  endpoint's own dataset size from DrugSim's overall reference-database size.
- **Section 11 tie-in documented, not newly built.** `data-gap-analysis.md`
  now cites the pre-existing `drugsim_curation`/curated-retraining pipeline
  as a real, working example of the ingest→curate→evaluate→benchmark
  protocol Section 11 requires — scoped separately from this brief, not
  claimed as satisfying it, cited only as evidence the mechanism exists.
- **`docs/scientific-coverage/final-report.md` reconciled.** It previously
  listed Sections 15–17, CYP3A4 external-generalisation, and the constraint
  tests as incomplete after a later same-day commit had already completed
  them; the report now reflects the actual current state and links the two
  commits, rather than leaving a stale self-contradiction across two sibling
  docs.
- **New tests:** `tests/unit/test_build_compound_identity_snapshot.py` — a
  PubChem timeout/outage mid-batch is logged and skipped, never fatal to the
  rest of the batch or corrupting of already-resolved entries (extracted the
  build script's resolution loop into `_resolve_compounds()`, a pure
  refactor, to make this testable without live network calls).
  `HistoryPage.test.tsx` gained coverage for the conformal-statistics
  disclosure (open it, read the p-values, read the non-singleton caveat) and
  for a pre-migration history row rendering correctly without it — this
  block previously had zero test coverage.

### Explicitly not claimed

- **No model was changed** — no training, retraining, re-thresholding, weight
  edit or registry promotion. The 0.5 decision threshold is unchanged, and is
  now documented as a deliberate recall-favouring choice appropriate to a
  cardiac-safety endpoint. A 0.70 threshold would maximise MCC but triples
  false negatives (52 → 158); recommended against.
- **No measurable model-performance improvement was demonstrated**, and none
  was attempted. Identity coverage improved by a measured but small margin;
  model accuracy did not change.
- The earlier claim below that the constraint tests "have not been executed"
  is now **superseded**: they were executed in this pass (75 passed). The
  historical Sprint 2.2 note is left in place as a record of what was true
  then, not corrected in retrospect.


### Added — Psychiatric Compound Screening Pipeline (offline research tool)

- New multi-objective screening pipeline covering DRD2 (therapeutic
  target), HRH1 (off-target/weight-gain liability), CYP2D6 (metabolic
  liability), BBB (CNS exposure), and hERG (cardiac liability, reused
  unchanged from the existing validated model) — combined via a
  direction-correct DRD2/HRH1 selectivity index
  (`selectivity_index_log10 = pki_drd2 - pki_hrh1`), replacing the
  originally-proposed `SI = H1/D2` ratio, which was ambiguous about
  potency-vs-inverted-value direction.
- Real datasets built and evaluated for all four new endpoints: DRD2
  (8,204 compounds, R²=0.498), HRH1 (1,395 compounds, R²=0.767),
  CYP2D6 (2,915 compounds, ROC-AUC=0.825), BBB (1,909 compounds,
  ROC-AUC=0.951) — each with split-conformal uncertainty and an
  exclude-self-corrected Tanimoto/k-NN applicability domain check.
- Found and corrected a real error inherited from Phase 9: CYP2D6 had
  been rejected for insufficient data using the wrong ChEMBL target ID
  (CHEMBL2035, actually the muscarinic M5 receptor). The real target
  (CHEMBL289) has 3,349 usable records — reopened and built. See
  `docs/phase9/endpoint-selection.md`'s erratum.
- CYP2D6 and BBB are registered (`models/registry/`) into the same
  generic model-loading/applicability-domain/conformal machinery hERG
  and CYP3A4 already use in production, as `EXPERIMENTAL` — loadable,
  checksum-verified, but correctly refused by the live promotion gate
  (`run_inference`) until an explicit promotion review happens.
- `models/psychiatric/screening_profile.py` combines all six signals
  into one structured, per-endpoint-honest report — every result
  carries its own real `reliability_tier` (`"validated"` for hERG,
  `"experimental"` for DRD2/HRH1/CYP2D6/BBB) rather than presenting
  all six as equally trustworthy. Verified end-to-end on Haloperidol
  and Diphenhydramine — all six signals for both compounds
  independently matched their well-documented, opposite real-world
  pharmacology (including haloperidol's known hERG/QT liability and
  CYP2D6 interaction).
- Every new model benchmarked against real majority-class and
  descriptor-only baselines (`models/psychiatric/benchmarking.py`) —
  all four clear their baseline; BBB's descriptor-only model comes
  close to its champion (consistent with lipophilicity/TPSA already
  carrying most of the real BBB-permeability signal).
- **Two real production incidents, found the hard way.** A live
  `POST /v1/psychiatric-screening` endpoint was attempted twice and
  crashed the live service both times (confirmed OOM kills in Render's
  own logs) — the existing 2-model service was already near its 512MB
  plan limit. DRD2 was retrained smaller before the first attempt
  (248MB→41MB); CYP2D6 and BBB were also retrained before the second
  (41MB→9MB, 13MB→7MB) — a real, disclosed accuracy cost on each, for
  a ~14x reduction in the four new models' combined incremental memory
  footprint. Still crashed the second time. Reverted both times; this
  pipeline is currently offline-only. See `docs/psychiatric-pipeline/
  api-integration.md` for the full two-incident story and what an
  actual fix would need.
- Full documentation set: `docs/psychiatric-pipeline/{README,
  scientific-foundation, data-sources, selectivity-methodology,
  benchmarking, api-integration, validation, limitations}.md`. 26
  unit tests, all passing.

### Added — Compound Identity Coverage Expansion

- Expanded the compound-identity snapshot from 6 to 904 real, named
  compounds by additionally sourcing every named compound already in
  DrugSim's own raw ChEMBL training data (956 candidates identified, 904
  resolved to a real PubChem entry) — no new external dependency, purely
  additive to already-ingested, already-licensed data.

### Added — Dynamic Compound Identification

- `/predict` responses now include a `compound_identity` block (name,
  synonyms, database identifiers, a verified description, source,
  retrieval date) resolved from the submitted structure's InChIKey — no
  more hardcoded per-compound metadata.
- Identity data is fetched from PubChem (already licensed in
  `datasets/registry.yaml` as the "identity spine") entirely **offline**,
  by a new `scripts/build_compound_identity_snapshot.py`, and committed
  as `src/drugsim_identity/data/compound_identity_snapshot.json`. The
  live service only does a local dictionary lookup — this preserves the
  existing, tested guarantee that no third-party service ever receives a
  submitted structure.
- A compound outside the snapshot is honestly reported as
  `identity_status: "unidentified"` and prediction proceeds unaffected —
  a novel molecule was never treated as invalid.
- Also exposes `molecular_weight` on the molecule response (RDKit-computed,
  previously internal-only).
- New frontend `CompoundIdentity` panel shown alongside the molecule
  preview, distinct from the user's own free-text compound-name label.
- Docs: `docs/compound-identification/README.md`.

### Strategy

- Evaluated DrugSim's potential scientific focus areas using only the
  repository's own existing data, models, validation reports, and
  benchmarks — no new data or models introduced.
- Selected **early-stage cardiac liability (hERG-mediated cardiotoxicity)
  screening** as the recommended initial focus, based on it having the
  deepest validation of anything in the repository (leakage checks,
  y-scrambling, external validation, distribution-shift calibration
  testing) and the strongest independently-corroborated performance
  number (external ROC-AUC 0.8696).
- Documented **CYP3A4-mediated metabolic drug-drug-interaction risk** as
  the secondary option — real and competitive, but not yet validated to
  the same depth.
- Existing non-focus capabilities (CYP3A4 prediction, the benchmarks
  page, the full API surface) remain available as supporting
  functionality; nothing was removed or gated.
- This is a strategic decision, not a validated market or scientific
  claim. See `docs/strategy/drugsim-focus-decision.md`.

### Added — Phase 12: Curated-Data Retraining Comparison

- Retrained hERG/CYP3A4 on Phase 11's curated dataset using the exact
  production training/evaluation procedure, then cross-evaluated against
  the live models.
- Result: curated training population, labels, and split assignment are
  identical to production for both endpoints; retrained models match
  production on every metric. No deployment — nothing different to
  promote yet.
- Surfaced and documented a pre-existing detail along the way: hERG's
  deployed model is a 200-tree truncation of the original 500-tree
  ensemble (a memory-limit workaround); added an equal-tree-count
  comparison so that isn't conflated with a data-quality effect.
- Docs: `docs/model-retraining/`.

### Added — Phase 11: Scientific Data Curation Engine

- New `drugsim_curation` package: a per-measurement ledger and
  curated-compound view that retains and tags discordant, excluded,
  unit-unresolved, and licence-unresolved measurements instead of
  silently dropping them, with full provenance back to raw ChEMBL
  records.
- Purely additive — `datasets/processed/`, `build_dataset.py`, and
  `prepare_features.py` verified byte-identical before/after; new output
  lives under `datasets/curated/`.
- Golden fixture and regression suite covering duplicates, discordance,
  invalid structures, mixtures, and known toxic/safe controls.
- Docs: `docs/data-curation/`.

### Added — Benchmarks Page & Real ADMET Tool Comparison

- Removed the permanently-stuck GPT column from `/benchmarks` and
  redesigned the page for scannability.
- Ran a real evaluation against ADMETlab 2.0 (full held-out test sets) and
  pkCSM (spot check) — established ADMET tools, distinct from the
  general-purpose AI comparison already on the page.
- Disclosed a methodology gap directly on the page: Claude's ROC-AUC
  comes from self-reported confidence, not a calibrated `predict_proba`.
- Moved provenance (model identifier, evaluation date) into the source
  JSON reports.

### Added — Sprint 2.2: Database Foundation

- **Canonical DDL** (`database/ddl/`, 10 files, 64 CREATE statements) implementing
  Phase 1 Step 3's schema across seven domains: governance, chemistry, biology,
  evidence, models/predictions, relations, views, triggers.
- **Alembic migrations** 0001–0011, forward-only (`downgrade()` raises), linear
  single-head chain validated by Alembic's own graph resolution.
- **RDKit cartridge** as a hard requirement: created in migration 0001, asserted
  at image-build time and again by `drugsim db verify-rdkit`.
- **`measurement` LIST-partitioned by `license_tier`** (green/amber/red/black), so
  the LC-03 licence audit is a partition scan and black-tier data can be isolated
  wholesale.
- **Three triggers** implementing the cross-table rules Phase 1 Step 3 §10 named
  but could not express as CHECK constraints: generic audit capture, feature-set
  consistency (PR-01), and ICH M7 dual-methodology pairing.
- **`drugsim_db`** package: engine/session management, RDKit cartridge
  verification, and `audit_context` — the one place session-local audit
  attribution is set.
- **67 constraint tests** across four files, each proving a violating insert
  *fails*. Highest-value: scaffold leakage prevention (ADR-009), `ck_not_predicted`
  (P4), feature-set mismatch (risk R5), and ICH M7 methodology pairing.
- `drugsim db` CLI subcommands (`upgrade`, `current`, `verify-rdkit`,
  `ensure-partitions`) and `scripts/ensure_audit_partitions.py`.
- CI `constraints` job; `make test-constraints`, `make db-*` targets.

### Decisions recorded during Sprint 2.2

- **`audit_log.audit_uid` is `UUID`, not the `ulid` domain.** Audit rows are the
  one entity created by the database itself (by trigger), with no application call
  site to mint a ULID from. Hand-rolling Crockford base32 bit-packing in PL/pgSQL
  was rejected as untestable in this environment and a poor place to hide a bug.
- **The audit trigger covers named interactively-mutated tables**, not all tables.
  Bulk scientific data carries per-row ETL provenance, which is its audit trail.
- **`database/ddl/` and migrations are byte-identical by construction for the
  initial schema only.** From migration 0012 onward, migrations are written
  directly and the DDL becomes a regenerated post-migration snapshot — a migration
  must never depend on a file that can change after it ships.

### Known gaps — Sprint 2.2

- **The 67 constraint tests have not been executed.** They require Docker
  (PostgreSQL 16 + RDKit via testcontainers), unavailable in the authoring
  environment. Verified statically: Python compilation, pytest collection (all 67
  discovered, fixtures resolve), DDL forward-reference and paren-balance checking,
  and Alembic graph validation. **Sprint 2.3 must begin by running them.**
- No ORM model layer yet — deliberate, see `src/drugsim_db/engine.py`.
- Step 4/6/7 extension tables deferred with rationale in `database/ddl/README.md`.

### Added — Sprint 2.1: Project Foundation

- Repository structure per Phase 1 Step 11.
- Poetry project targeting Python 3.12, with RDKit pinned exactly (ADR-013).
- `drugsim_core.config` — layered configuration (defaults < base YAML < environment
  YAML < environment variables < explicit overrides) with production safety
  invariants that reject `debug` and console logging in staging and production.
- `drugsim_core.redaction` — customer structure protection: a `SensitiveStructure`
  wrapper redacted in every string representation, plus a structlog processor
  scrubbing by key name, by type, and by pattern.
- `drugsim_core.logging` — structlog with a shared stdlib bridge; redaction runs last
  before rendering so it sees formatted exception text.
- `drugsim_core.ids` — ULID generation and prefixed public identifiers (ADR-008).
- `drugsim_core.version` — `toolchain_id` construction, the reproducibility anchor.
- `drugsim_core.errors` — exception hierarchy with stable codes and structured
  context rather than interpolated messages.
- `drugsim_quality.license_audit` — rules LC-01 … LC-06 with attribution manifest
  generation; wired as a required CI gate.
- `Dockerfile.postgres-rdkit` — custom PostgreSQL 16 + RDKit cartridge image, a
  first-class artefact because the cartridge is unavailable on managed Postgres.
- Docker Compose stack: Postgres + RDKit, MinIO, bucket initialisation with
  versioning enabled on the Z1 landing bucket.
- CI pipeline with six jobs, including a separately-run structure-disclosure check
  and the dataset licence audit.
- Pre-commit hooks, mkdocs documentation framework, Makefile, CODEOWNERS.
- 190 automated tests covering configuration, identifiers, redaction, versioning and
  licence auditing.

### Fixed during Sprint 2.1

- **Configuration precedence inversion.** YAML values were passed as constructor
  arguments, which pydantic-settings ranks above environment variables — so a
  committed default silently overrode an operator's environment variable. YAML keys
  shadowed by `DRUGSIM_*` variables are now dropped before construction.
- **Logger factory mismatch.** `structlog.stdlib.add_logger_name` was paired with
  `PrintLoggerFactory`, which has no `.name`. Replaced with the canonical
  stdlib + `ProcessorFormatter` integration, which also gives one redaction path
  for both structlog and third-party logging.
- **Structure disclosure via embedded text.** Redaction only tested whole strings, so
  a structure reached logs through `%`-style stdlib formatting and through exception
  messages. Added token-level scanning with guards for digests, paths, ULIDs and
  `key=value` pairs.
- **Registry defects found by the new audit.** BindingDB's split-licence portions
  declared SPDX without attribution text; the audit rule recognised only one of the
  two legitimate mixed-licensing shapes.

### Notes

- ADR-013 records the deviation from TDS §3.12 (Poetry rather than `uv`; `ruff
  format` rather than Black).
