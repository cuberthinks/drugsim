# TDS §8 & §9 — Engineering Standards and Quality Assurance

**Repository layout:** defined in Phase 1 Step 11 and not restated. This section covers conventions, process and the QA regime.

---

## 8.1 Naming Conventions

| Artefact | Convention | Example |
|---|---|---|
| Python module / package | `snake_case` | `drugsim_chem`, `standardize.py` |
| Class | `PascalCase` | `PredictionEnvelope` |
| Function / variable | `snake_case` | `compute_descriptors` |
| Constant | `UPPER_SNAKE_CASE` | `DEFAULT_COVERAGE` |
| Database table | singular `snake_case` | `compound`, not `compounds` |
| Database column | `snake_case`; unit suffix where ambiguous | `mw_g_mol`, `tpsa_a2` |
| Foreign key | `{referenced_table}_uid` | `compound_uid` |
| Boolean | `is_` / `has_` prefix | `is_deleted`, `has_sharealike` |
| API field | `snake_case` | `applicability_domain` |
| Public ID | `{prefix}_{ulid}` | `cmp_01J8XK…` |
| Branch | `{type}/{ticket}-{slug}` | `feat/DS-142-conformal-intervals` |
| Container image | `drugsim/{service}:{git-sha}` | — |

**Units in column and field names are mandatory where a quantity could plausibly carry more than one unit.** `mw` is ambiguous; `mw_g_mol` is not. Phase 1 established unit confusion as the highest-risk silent failure in the system, and naming is the cheapest available defence.

---

## 8.2 Code Style

| Concern | Standard |
|---|---|
| Formatter | `ruff format` — non-negotiable, no per-file overrides |
| Linter | `ruff` with a shared ruleset |
| Type checking | `mypy --strict` on `src/`; **CI-blocking** |
| Docstrings | Google style; required on all public functions |
| Line length | 100 |
| Imports | Absolute within `src/`; no wildcard imports |
| SQL | Uppercase keywords; one clause per line; **parameterised always** |

**Three DrugSim-specific rules**, each enforced by a lint check because each protects a guarantee that a code review will eventually miss:

1. **No bare `float` for a measured or predicted quantity in a public interface.** Use a typed value-with-unit. A bare float is how units get lost.
2. **No logging call may interpolate a variable typed as a structure** (`Smiles`, `Mol`, `InChI`). Enforced by a custom lint rule (§7.2.3).
3. **No direct RDKit import outside `src/drugsim_chem`.** All chemistry goes through the shared library; a direct import elsewhere is how training/serving skew returns (R6).

Rule 3 is backed by CODEOWNERS on `src/drugsim_chem/`, requiring cheminformatics review for any change.

---

## 8.3 Documentation Standards

| Level | Requirement |
|---|---|
| Function | Docstring: purpose, args with units, returns, raises |
| Module | Header explaining role and its place in the pipeline |
| Package | `README.md` with responsibilities and boundaries |
| Decision | **ADR** — required for any architectural choice (P9) |
| Schema | DDL comments; the Phase 1 data dictionary is authoritative |
| API | OpenAPI generated from code; contract documented in TDS §4–§5 |
| Runbook | One per operational procedure in `docs/runbooks/` |

**A function computing or converting a scientific quantity must document its units in the docstring**, even when the parameter name carries them. Redundant by design: this is the layer a reviewer actually reads.

**ADRs are never edited after acceptance.** A reversal is a new ADR marked `Supersedes ADR-NNN`, and the original is marked `Superseded by`. The history of a reversed decision is more valuable than a tidy document.

---

## 8.4 Commit and Branching

**Conventional Commits**, driving the changelog:

```
feat(chem): add tautomer canonicalisation to standardisation pipeline

Adds RDKit TautomerEnumerator as step 6. Canonical tautomer is stored in
a separate column; source tautomer is preserved (Phase 1 Step 8 §S4).

Refs: DS-142
BREAKING-CHANGE: descriptor_spec_version bumps to v2; existing feature
sets remain valid and are not recomputed.
```

Types: `feat` · `fix` · `refactor` · `perf` · `test` · `docs` · `chore` · `data` (pipeline/registry changes) · `schema` (DDL changes).

**Trunk-based development.** Short-lived branches (< 3 days), merged to `main` via PR, squash-merged. `main` is always deployable. Long-lived feature branches are prohibited — they hide integration risk and, in a system with this many cross-cutting invariants, integration is where the invariants break.

**Migrations are forward-only.** No down-migrations: under a regulatory path a rollback is a new forward migration with a recorded reason, because a silent reversal leaves no audit trace. Schema changes use the expand-contract pattern (§9.6).

---

## 8.5 Review Process

| Change class | Reviewers |
|---|---|
| Routine | 1 |
| Public API contract | 2, incl. tech lead |
| Database schema | 2, incl. data owner |
| `src/drugsim_chem` | 2, incl. cheminformatician (CODEOWNERS) |
| ETL gates / validation logic | 2, incl. data owner |
| Model promotion | Tech lead + scientific reviewer |
| Security-relevant | 2, incl. security owner |
| Anything under regulatory validation | Above + QA sign-off |

**Reviewer checklist for anything touching data or predictions** — the P1–P12 questions from §12.1: traceability, value mutation, provenance preservation, uncertainty rendering, structure logging.

**Reviews block on unanswerable questions, not just on defects.** If a reviewer cannot determine whether provenance is preserved, the PR is not ready — evidence of correctness is part of the deliverable.

---

## 9. Quality Assurance

### 9.1 Test Strategy

| Layer | Scope | Tooling | Target |
|---|---|---|---|
| Unit | Pure functions, business logic | pytest | ~70% of tests; > 85% line coverage on `src/` |
| **Property-based** | Chemistry invariants | Hypothesis | All of `drugsim_chem` |
| Integration | Service + real Postgres+RDKit | testcontainers | Critical paths |
| **Constraint** | Every DB constraint and trigger | testcontainers | 100% of constraints |
| Contract | API vs OpenAPI | Schemathesis | All endpoints |
| **Scientific** | Golden set, benchmarks | pytest + fixtures | Every release |
| Performance | Latency, throughput | pytest-benchmark, k6 | Key paths |
| Security | SAST, dependency, container | ruff-sec, osv-scanner, Trivy | Every build |
| E2E | User journeys | Playwright | Smoke set only |

Coverage percentage is a floor, not a goal. **A 95%-covered codebase with no constraint tests is less safe than an 80%-covered one with them**, because the constraints are where the scientific invariants live.

### 9.2 Property-Based Testing — Chemistry Invariants

Example-based tests cover the molecules a developer thought of; Hypothesis generates the ones they did not.

| Invariant | Property |
|---|---|
| Standardisation idempotency | `f(f(m)) == f(m)` |
| SMILES round-trip | `parse(canonical(parse(s))) ≡ parse(s)` |
| Identity consistency | `inchikey_skeleton == inchikey_full[:14]` |
| Descriptor monotonicity | Adding a heavy atom never decreases `heavy_atom_count` |
| Unit conversion | `to_canonical(to_source(v)) ≈ v` within tolerance |
| Mass consistency | `abs(exact_mass − mw) < 0.5` |
| Rule consistency | `lipinski_pass == (lipinski_violations <= 1)` |

Idempotency is the most important. Non-idempotent standardisation causes structures to drift across releases — slowly, invisibly, irreversibly — and no example-based test reliably catches it.

### 9.3 Database Testing

**Against real Postgres with the real cartridge**, via testcontainers. SQLite and mocks cannot exercise cartridge types, partitioning, RLS, or `CONSTRAINT TRIGGER`s.

Required assertions — each a violating insert that **must fail**:

| Constraint | Test |
|---|---|
| `ck_not_predicted` | Inserting `evidence_type='predicted'` into `measurement` fails |
| `uq_scaffold_single_group` | One scaffold in two split groups fails |
| `ck_commercial_tiers` | `is_commercial_ok=true` with a black tier fails |
| `ck_skeleton_prefix` | Mismatched skeleton fails |
| `ck_review_when_required` | ICH M7 assessment requiring review without one fails |
| PR-01 trigger | Feature-set mismatch on `prediction` fails |
| ICH M7 pairing trigger | Two same-methodology predictions fail |
| RLS | Cross-tenant select returns zero rows |

**Rationale:** a migration that drops a CHECK passes every functional test. The system works; it simply no longer prevents what the constraint prevented. Only a test asserting failure detects this.

### 9.4 Scientific Validation

Distinct from software testing and blocking on release (P7).

| Check | Criterion |
|---|---|
| Golden set | ~500 reference compounds reproduce **exactly**: identity, descriptors, rules |
| Benchmark regression | Model metrics within tolerance of the recorded baseline |
| Conformal coverage | Empirical coverage within tolerance of nominal |
| Cross-source consistency | ChEMBL ↔ BindingDB agreement rate stable |
| Unit assertions | All G4 checks pass; no `unit_verified_method='unverified'` published |
| Distribution drift | Descriptor distributions vs prior release (KS test) |
| Leakage audit | No `split_group` in both train and test across any dataset pair |

A golden-set difference is either explained with the expectation updated and a recorded reason, or it is a regression. There is no third option.

### 9.5 Performance Targets

Initial, to be revised against real usage:

| Operation | Target (p95) |
|---|---|
| `GET /v1/compounds/{id}` | < 100 ms |
| `POST /v1/predictions` (enqueue) | < 300 ms |
| Single-compound, single-endpoint prediction (job) | < 5 s |
| Single compound, 20 endpoints | < 30 s |
| Similarity search (threshold 0.7, 3M compounds) | < 2 s |
| Substructure search (specific query) | < 5 s |
| Batch, 1,000 compounds × 5 endpoints | < 30 min |
| Full ETL rebuild | < 12 h |

Performance is the last selection criterion (§3.1), but regressions still matter: a 10× slowdown usually signals a correctness problem — a missing index, an accidental full scan, a cartridge index not being used.

### 9.6 Acceptance Criteria

A release ships only when **all** hold:

**Software** — all tests pass · coverage floors met · `mypy --strict` clean · no high/critical vulnerabilities · SBOM generated · contract tests pass · `must_display` conformance passes.

**Scientific** — golden set reproduces · benchmark regression within tolerance · conformal coverage valid · no unverified units published · leakage audit clean · G1–G6 pass.

**Governance** — licence audit clean (LC-01…LC-06) · attribution manifest current · no black-tier data on a commercial path · ADRs written for architectural changes · changelog updated.

**Regulatory (when applicable)** — G7 passes · OECD records complete for every deployed model · QMRFs present · audit-trail continuity verified · deployment approval signed.

**Any single failure blocks the release.** There is no override path in the tooling. A release that needs to ship despite a failure requires an explicit, recorded, signed exception — which is deliberately more effort than fixing the problem.

---

*End §8 & §9.*
