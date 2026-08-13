# DrugSim

**AI-assisted preclinical prioritisation platform.** Predicts ADMET properties,
drug-likeness, target hypotheses and toxicity flags for designed molecules — each
with calibrated confidence and an explicit applicability-domain assessment.

> **Positioning.** DrugSim improves the *ordering* of an experimental queue. It is
> not a replacement for laboratory or animal testing, and must not be presented as
> one. Phase 1 verified that the public corpus behind the headline endpoints is small
> — human bioavailability 640 compounds, half-life 667, DILI 475, carcinogenicity 278
> — so applicability-domain estimation is a required output, not a nicety.

---

## Status

**Phase 2, Sprint 2.1 — Project Foundation.** No API, no models, no frontend. This
repository currently contains the scientific data foundation and the engineering
scaffolding it will be built on.

| Phase | Scope | State |
|---|---|---|
| 1 | Scientific data foundation (12 steps) | Complete |
| TDS | Technical Design Specification (12 sections) | Final |
| 2.1 | Project foundation | **Complete** |
| 2.2 | Database foundation | **Complete** — constraint tests written but unexecuted (needs Docker) |
| 2.3 – 2.10 | Registry, ingestion, ETL, golden set, population, quality, knowledge, validation | Not started |

---

## Quick start

Requires Python 3.12, Poetry, and Docker.

```bash
poetry install --with dev        # dependencies and pre-commit hooks
make install

make up                          # PostgreSQL + RDKit and MinIO
make db-upgrade                  # apply migrations 0001-0011
make db-verify-rdkit             # assert the cartridge is present

make test                        # unit and security tests (no Docker needed)
make test-constraints            # database constraint tests (needs Docker)
make audit                       # dataset licence audit
```

`make help` lists all targets.

---

## Repository layout

```
config/          Non-secret configuration; base + per-environment overlays
database/
  ddl/             Canonical schema, 10 files by domain (see its README)
  migrations/      Alembic, forward-only, revisions 0001-0011
datasets/        registry.yaml (Z0 source registry) and the golden set
deployment/      Dockerfiles, Compose stack, CI configuration
docs/            TDS, Phase 1 design corpus, ADRs, runbooks
etl/             Dagster assets, pipeline gates, source adapters  (Sprint 2.4+)
src/
  drugsim_core/    Configuration, logging, identifiers, errors, versioning
  drugsim_chem/    THE chemistry library — imported by ETL, training and serving
  drugsim_db/      Engine, sessions, audit context, cartridge verification
  drugsim_features/Feature store                          (Sprint 2.5)
  drugsim_quality/ Licence audit, unit determination, quality scoring
tests/           unit · integration · constraints · security · golden
```

---

## Engineering principles

Twelve principles govern this codebase (TDS §12). Each has an enforcement mechanism —
a principle without one is an aspiration.

1. Scientific reproducibility over speed
2. Every prediction is traceable
3. Never overwrite raw experimental data
4. Every dataset retains provenance — **per record, not per dataset**
5. Every model is reproducible
6. Every prediction carries confidence and applicability
7. Every release passes scientific validation
8. Nothing is deleted or silently altered
9. Every architectural decision is documented
10. Prefer boring, inspectable technology
11. **Customer structures are confidential IP**
12. Honest failure over confident error

### Three that shape the code most

**Customer structures never reach logs.** A molecular structure uploaded by a
customer is pre-patent trade secret; a SMILES string in an exception message is an IP
disclosure. `drugsim_core.redaction` provides a wrapper type redacted in every string
representation plus a structlog processor scrubbing by key, type and pattern. The
control that actually holds is `tests/security/test_no_structure_in_logs.py`, which
asserts that a request carrying a known structure produces no log line containing it.

**One chemistry implementation.** `src/drugsim_chem/` is imported unchanged by the
ETL pipeline, model training and inference. Importing `rdkit` anywhere else is a lint
error. This is the structural prevention of training/serving skew.

**RDKit is pinned exactly.** Descriptor values change between RDKit releases. The
version participates in `toolchain_id` and therefore in `feature_set_id`; a silent
minor upgrade would make features computed before and after non-interchangeable while
appearing identical.

---

## Testing

```bash
make test            # unit + security
make test-security   # structure-disclosure controls only
make test-all        # including integration (needs Docker)
make cov             # coverage report
```

Five test categories, three of them DrugSim-specific:

| Category | Purpose |
|---|---|
| `unit` | Pure logic |
| `security` | Asserts structures never reach logs |
| `constraints` | Asserts each database constraint **rejects** invalid data |
| `golden` | Scientific regression against ~500 reference compounds |
| `integration` | Real Postgres + RDKit via testcontainers |

Constraint tests exist because a migration that drops a `CHECK` passes every
functional test — the system works, it simply no longer prevents what the constraint
prevented. Only a test asserting that a violating insert *fails* detects this.

---

## Documentation

| Document | Contents |
|---|---|
| [`docs/tds/`](docs/tds/README.md) | Technical Design Specification — architecture, contracts, API, ML, security, deployment, risks |
| [`docs/phase1/`](docs/phase1/step1-dataset-survey.md) | Scientific foundation — dataset survey, schema design, ETL, knowledge graph, roadmap |
| [`docs/adr/`](docs/adr/) | Architecture Decision Records |
| [`docs/legal/`](docs/legal/) | Attribution manifest (generated), licence analysis |

`make docs` serves them locally.

---

## Data licensing

DrugSim ingests eleven public sources under four licence tiers. **Tier is enforced
architecturally**, not by policy: it partitions the data lake, it is a column on every
fact row, and `make audit` fails the build on any violation.

| Tier | Meaning | Sources |
|---|---|---|
| green | CC0 / public domain | PDB, Open Targets, Tox21/ToxCast, openFDA, DailyMed |
| amber | CC BY — attribution only | UniProt, TDC (majority), BindingDB-curated portion |
| red | **CC BY-SA — ShareAlike** | ChEMBL, DrugCentral, SIDER, PharmGKB, BindingDB ChEMBL-derived portion |
| black | **Prohibited** | FreeSolv, DrugBank, PDBbind |

Two facts worth knowing before touching ingestion:

- **BindingDB is split-licensed internally** — its own curation is CC BY 3.0, its
  ChEMBL-derived records CC BY-SA 3.0. This is why licence provenance is per-record.
- **FreeSolv is CC BY-NC-SA 4.0 and ships inside TDC** behind the same uniform
  interface as every permissive dataset, which makes accidental ingestion easy. It is
  hard-gated, not merely documented.

Whether ShareAlike reaches trained model weights is legally unsettled and is tracked
as risk R1. The architecture is deliberately outcome-agnostic.

---

## Contributing

Trunk-based development, short-lived branches, Conventional Commits, forward-only
migrations. Review requirements are in TDS §8.5 and `CODEOWNERS`.

A pull request touching data or predictions should be able to answer: is a prediction
from this code traceable to its inputs? Does it alter existing stored values? Is
provenance preserved? Could it cause a prediction to render without its uncertainty?
Does it log a customer structure anywhere new?

If a reviewer cannot answer these, the PR is not ready — evidence of correctness is
part of the deliverable.

## Licence

Proprietary. Ingested datasets retain their own licences; see the attribution
manifest in `docs/legal/`.
