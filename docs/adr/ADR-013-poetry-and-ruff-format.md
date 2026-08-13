# ADR-013 — Poetry over uv; ruff format instead of Black

**Status:** Accepted
**Date:** 2026-08-06
**Amends:** TDS §3.12 (dependency management row)
**Deciders:** Tech Lead

## Context

TDS §3.12 specifies `uv` with a committed lockfile for dependency management. The
Sprint 2.1 specification instead names Poetry, and also lists both Black and Ruff as
required tooling.

Two conflicts had to be resolved before writing `pyproject.toml`.

### Poetry vs uv

Both produce a committed lockfile with hash-pinned, fully-resolved dependencies,
which is the property TDS §7.10 actually depends on for supply-chain integrity. The
difference is resolution speed and ecosystem maturity, not reproducibility.

`uv` is substantially faster. Poetry is more widely known, has broader CI and IDE
support, and is more likely to be familiar to a new engineer joining the project —
which matters for a codebase intended to be maintained over several years by people
who did not write it (risk R19).

### Black vs ruff format

These conflict operationally. Both are formatters; configuring both means two tools
competing over the same files in pre-commit, producing churn on every commit.

`ruff format` is a Black-compatible reimplementation: it produces the same output for
the overwhelming majority of code, and is already a required dependency for linting.

## Decision

1. **Use Poetry**, as directed by the Sprint 2.1 specification. The reproducibility
   guarantee is carried by `poetry.lock`, which is committed.
2. **Use `ruff format` and drop Black.** One formatter, no per-file overrides
   (TDS §8.2). Black is not installed.

## Consequences

**Positive**
- Poetry's familiarity lowers onboarding cost, which is the mitigation for R19.
- A single formatter eliminates a class of pre-commit churn.
- No behavioural difference in formatted output versus the specified Black.

**Negative**
- Slower dependency resolution than `uv`, most visible in CI cold builds. Mitigated
  by Poetry's cache in the CI setup action.
- TDS §3.12 is now inaccurate on this row until amended.

**Follow-up**
- Amend TDS §3.12 to record Poetry and reference this ADR.
- Revisit if CI dependency-resolution time becomes a measured bottleneck; migration
  is contained because both consume `pyproject.toml`.

## Alternatives considered

| Option | Rejected because |
|---|---|
| Follow the TDS and use `uv` | Contradicts the explicit Sprint 2.1 directive; the reproducibility property is equivalent |
| Run Black and Ruff together | Two formatters competing over the same files |
| Use Black and disable `ruff format` | Adds a dependency for behaviour Ruff already provides |
