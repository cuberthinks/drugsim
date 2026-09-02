# Changelog

All notable changes to DrugSim are recorded here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versioning follows SemVer.

Core DB releases are versioned separately as `core-db-vN.N.N` (Phase 1 Step 2 §7.2).

## [Unreleased]

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
  CYP2D6 (2,915 compounds, ROC-AUC=0.833), BBB (1,909 compounds,
  ROC-AUC=0.962) — each with split-conformal uncertainty and an
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
- **A live endpoint was attempted and reverted the same day.**
  `POST /v1/psychiatric-screening` was built, deployed, and crashed
  the live service on a real test request (confirmed OOM restart in
  Render's own logs) — the existing 2-model service was already near
  its 512MB plan limit, and loading hERG + CYP2D6 together alone was
  enough to exceed it. DRD2 had already been retrained smaller (248MB
  → 41MB, R² 0.5994 → 0.498) specifically to reduce this risk, which
  wasn't sufficient on its own. Reverted the same day; see
  `docs/psychiatric-pipeline/api-integration.md` for the full incident
  and what a real fix would need (a bigger instance, or a smaller
  combined footprint).
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
