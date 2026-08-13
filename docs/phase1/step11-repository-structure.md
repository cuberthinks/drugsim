# DrugSim — Phase 1, Step 11
## Repository Structure

**Document status:** Draft for approval
**Date:** 2026-08-05
**Depends on:** Steps 1–10 (approved)

---

## 1. Structural Decisions

Three choices shape the layout, each with a reason.

**Monorepo.** Data foundation, models, and eventual services share the descriptor library, the schema, and the provenance contract. Splitting them would mean versioning that contract across repositories — the surest way to get training/serving skew back after Step 2 designed it out.

**`src/` layout, installable packages.** Not flat scripts. `drugsim_chem` must be importable identically by ETL, training and serving; a flat layout makes import behaviour depend on the working directory, which is a reproducibility hazard.

**Data directories are tracked but empty.** `datasets/raw/` and `datasets/processed/` hold `.gitkeep` and README files only. Actual data lives in object storage; git holds the *definitions* — `registry.yaml`, schema DDL, pipeline code. Committing data would break provenance (the lake is authoritative) and bloat the repository irrecoverably.

---

## 2. Tree

```
drugsim/
├── README.md
├── LICENSE
├── CHANGELOG.md
├── pyproject.toml                 # deps + tool config; pinned
├── uv.lock                        # exact resolution — reproducibility
├── .pre-commit-config.yaml
│
├── config/
│   ├── base.yaml                  # non-secret defaults
│   ├── environments/              # local · staging · production
│   ├── toolchain.yaml             # RDKit/Python pins → toolchain_id
│   ├── descriptor_specs/          # versioned descriptor definitions
│   │   ├── v1.yaml
│   │   └── v2.yaml
│   ├── endpoints/                 # endpoint registry seed (Steps 5, 7)
│   │   ├── absorption.yaml   ├── distribution.yaml
│   │   ├── metabolism.yaml   ├── excretion.yaml
│   │   └── toxicity.yaml
│   └── quality/
│       ├── measurement_quality_v1.yaml
│       └── aggregation_policy_v1.yaml
│
├── datasets/
│   ├── registry.yaml              # ★ Z0 source registry — authoritative
│   ├── raw/.gitkeep               # → object storage Z1
│   ├── processed/.gitkeep         # → object storage Z3
│   ├── golden/                    # ★ committed: ~500 reference compounds
│   │   ├── compounds.csv
│   │   ├── expected_descriptors.csv
│   │   ├── expected_identity.csv
│   │   └── README.md
│   └── reference/                 # small committed lookups
│       ├── salts.txt              # salt-stripping list
│       ├── structural_alerts/     # PAINS · Brenk · genotoxic SMARTS
│       └── unit_conversions.yaml
│
├── etl/
│   ├── definitions.py             # Dagster entrypoint
│   ├── assets/                    # one module per zone
│   │   ├── z1_landing/  ├── z2_conformed/
│   │   ├── z3_curated/  └── z4_serving/
│   ├── gates/                     # G1–G7, one module each
│   │   ├── g1_acquisition.py ... g7_regulatory.py
│   ├── sources/                   # one adapter per source
│   │   ├── chembl.py    ├── pubchem.py   ├── bindingdb.py
│   │   ├── tdc.py       ├── toxcast.py   ├── uniprot.py
│   │   ├── pdb.py       ├── drugcentral.py
│   │   ├── opentargets.py ├── openfda.py └── dailymed.py
│   └── quarantine/                # failed-record handling
│
├── database/
│   ├── migrations/                # Alembic — forward-only
│   ├── ddl/                       # canonical schema, mirrors Step 3
│   │   ├── 00_domains_types.sql
│   │   ├── 10_governance.sql      # audit · signatures · users
│   │   ├── 20_chemistry.sql
│   │   ├── 30_biology.sql
│   │   ├── 40_evidence.sql        # endpoints · assays · measurements
│   │   ├── 50_toxicology.sql
│   │   ├── 60_models_predictions.sql
│   │   ├── 70_relations.sql
│   │   ├── 80_views.sql
│   │   └── 90_triggers.sql        # ★ Step 3 §10 cross-table rules
│   ├── seeds/                     # endpoints · alerts · vocabularies
│   └── policies/                  # row-level security
│
├── src/
│   ├── drugsim_core/              # config · provenance · IDs · logging
│   ├── drugsim_chem/              # ★ standardisation · descriptors · identity
│   │   ├── standardize.py         #   THE shared library — ETL and serving
│   │   ├── descriptors.py         #   both import this, never reimplement
│   │   ├── identity.py
│   │   ├── alerts.py
│   │   └── drug_likeness.py
│   ├── drugsim_features/          # feature store read/write, content addressing
│   ├── drugsim_db/                # SQLAlchemy models, repositories
│   ├── drugsim_quality/           # quality scoring · unit determination
│   └── drugsim_graph/             # Phase 3 — KG projection
│
├── models/                        # Phase 3+ — training code, NOT artefacts
│   ├── admet/  ├── toxicity/  ├── target_prediction/
│   ├── uncertainty/               # conformal · calibration
│   ├── applicability_domain/
│   └── registry/                  # model cards · QMRF templates
│
├── api/                           # Phase 7 — placeholder
├── backend/                       # Phase 7 — placeholder
├── frontend/                      # Phase 8 — placeholder
│
├── experiments/                   # tracked, reproducible; one dir per experiment
│   └── README.md                  # naming + provenance conventions
│
├── notebooks/
│   ├── exploratory/               # ★ output-stripped on commit
│   └── reports/
│
├── scripts/                       # operational one-offs
│   ├── bootstrap_db.py  ├── verify_golden_set.py
│   ├── audit_licenses.py  └── rebuild_ontology_closure.py
│
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── golden/                    # ★ regression vs datasets/golden/
│   ├── constraints/               # ★ asserts every DB constraint fires
│   ├── gates/                     # G1–G7 behaviour
│   └── fixtures/
│
├── deployment/
│   ├── docker/                    # postgres+rdkit image lives here
│   ├── compose/  ├── terraform/  └── ci/
│
└── docs/
    ├── phase1/                    # Steps 1–12 (this series)
    ├── adr/                       # ADR-001 … ADR-012
    ├── legal/
    │   ├── attribution-manifest.md   # ★ auto-generated, LC-05
    │   └── license-analysis.md
    ├── validation/                # ★ regulatory: QMRF · OECD records · SOPs
    └── runbooks/
```

★ = directories whose absence would break a guarantee established in Steps 1–10.

---

## 3. Notes on Non-Obvious Choices

**`src/drugsim_chem/` is the anti-skew mechanism.** Step 2 §6.2 promised that training and serving compute descriptors identically. That promise is only kept if there is exactly one implementation. This package is imported by ETL and by the eventual prediction service; reimplementing standardisation in a service is the specific failure it prevents. Worth a CODEOWNERS entry.

**`datasets/golden/` is committed data — deliberately.** It contradicts the rule that data lives in object storage, and should: the golden set is *test fixture*, not data. It must be versioned with the code it validates, and it is the primary defence against silent pipeline breakage (Step 8 §10.1).

**`tests/constraints/` exists because constraints can be silently dropped.** A migration that omits a CHECK will pass every functional test — the system works, it just no longer prevents the thing the constraint prevented. Given how much integrity Steps 3–7 pushed into constraints and triggers (`ck_not_predicted`, `uq_scaffold_single_group`, `ck_commercial_tiers`, the ICH M7 pairing trigger), each needs a test that asserts a violating insert *fails*.

**`docs/validation/` is empty in Phase 1 and that is correct.** It exists so the regulatory artefacts have a home from the start. Populating it before there are models to validate would consume runway (Step 2 addendum §5).

**`models/` holds code, never artefacts.** Trained models go to object storage, referenced by `model_version.artifact_uri` + `artifact_sha256`. Committing binaries breaks the content-addressing contract and bloats the repository.

**Notebook outputs are stripped on commit** (`nbstripout` in pre-commit). Committed outputs create phantom diffs and, worse, embed stale results that read as current.

---

## 4. Conventions

| Concern | Convention |
|---|---|
| Branching | Trunk-based, short-lived branches, PR review required |
| Commits | Conventional Commits — drives CHANGELOG |
| Versioning | SemVer for Core DB releases (Step 2 §7.2); calendar tags for deployments |
| Migrations | **Forward-only.** No down-migrations in a validated system — a rollback is a new forward migration with a recorded reason |
| Dependencies | `uv` with committed lockfile; RDKit pinned exactly (descriptor values are version-sensitive) |
| Secrets | Never in repo; env vars / secret manager. `config/` holds non-secret defaults only |
| CI required checks | lint · type-check · unit · constraints · golden-set · licence audit |

**The licence audit as a required CI check** is the mechanism that makes Step 1 §5 durable. `scripts/audit_licenses.py` verifies every `registry.yaml` entry has a valid tier, no black-tier source is referenced by a commercial-path artefact (LC-03), and the attribution manifest is current. Without it, licence discipline decays to a document nobody reads.

---

*End Step 11.*
