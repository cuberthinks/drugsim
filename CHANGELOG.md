# Changelog

All notable changes to DrugSim are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows SemVer.

Core DB releases are versioned separately as `core-db-vN.N.N` (Phase 1 Step 2 §7.2).

## [Unreleased]

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
