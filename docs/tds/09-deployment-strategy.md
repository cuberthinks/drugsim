# TDS §10 — Deployment Strategy

---

## 10.1 Environments

| Environment | Purpose | Data | Access | Lifecycle |
|---|---|---|---|---|
| **Local** | Developer workstation | Synthetic + golden set | Developer | Ephemeral, Compose |
| **Development** | Shared integration | Synthetic + public subset | Engineering | Continuous deploy from `main` |
| **Test / CI** | Automated verification | Fixtures + testcontainers | CI only | Per-run, ephemeral |
| **Staging** | Pre-production verification | **Full public data; no customer data** | Engineering + QA | Deploy on release tag |
| **Production** | Live | Public + customer data | Operations only | Manual approval |

**Staging never contains customer data.** Not anonymised, not sampled — none. Anonymising molecular structures is not meaningfully possible: a structure *is* the sensitive content, and any transformation preserving its usefulness for testing also preserves its identity. Staging therefore uses full public reference data plus synthetic tenant data.

This means some customer-data-specific bugs will only appear in production. Accepted, and mitigated by tenant isolation tests, canary deployment, and RLS as the enforcement layer rather than application logic.

**Staging must match production in configuration**, including the `postgres-rdkit` image digest. A staging environment that differs from production validates nothing — and under the regulatory path, an unrepresentative test environment is a validation gap.

---

## 10.2 Infrastructure as Code

Terraform for infrastructure; Compose or Kubernetes manifests for services; all in `deployment/`, all reviewed like application code.

**No manual infrastructure changes in any environment.** A hand-configured resource cannot be reproduced, and under the regulatory path an unreproducible environment cannot be validated. Emergency manual changes are permitted during an incident and must be codified within one working day, with the drift recorded.

Configuration is environment-specific and version-controlled; secrets are injected at runtime from the secret manager and never committed (§7.6).

---

## 10.3 Container Strategy

| Image | Base | Notes |
|---|---|---|
| `drugsim/api` | `python:3.12-slim` | Stateless, horizontally scaled |
| `drugsim/worker` | `python:3.12-slim` | Prediction and ETL workers |
| `drugsim/dagster` | `python:3.12-slim` | Orchestrator daemon |
| **`drugsim/postgres-rdkit`** | `postgres:16` + RDKit cartridge | **Custom; a first-class artefact** |
| `drugsim/web` | `node:22-slim` → static | Frontend |

**All images digest-pinned in deployment**, not tag-pinned. A tag is mutable; `:latest` or even `:1.2.3` can be repointed upstream. A digest cannot, and reproducible deployment requires that guarantee.

`postgres-rdkit` warrants repeating from §3.6: its RDKit version participates in `toolchain_id` and therefore in every reproducibility claim. It is built from a pinned in-repo Dockerfile, scanned, signed, and changed only through change control.

Containers run non-root with read-only root filesystems and dropped capabilities; the structure-parsing subprocess additionally runs under a seccomp profile and `rlimit` (§7.7).

---

## 10.4 Deployment Process

```
main ──► dev (auto)
  │
  └─ tag v* ──► staging (auto) ──► acceptance (§9.6) ──► production (manual approval + signature)
```

**Production deployment requires human approval with an electronic signature** under the regulatory path. Fully automated production deployment is deliberately not available: a deployment is a change-controlled event, and the approval is part of the record.

**Strategy: rolling for stateless services, blue/green for anything touching the database schema.** Rolling is sufficient for API and workers. A schema change needs both versions running against one database, which drives §10.6.

Canary: new versions receive a traffic percentage before full rollout, with automated rollback on error-rate or latency regression.

---

## 10.5 Backup and Recovery

| Asset | Method | Frequency | Retention | Notes |
|---|---|---|---|---|
| PostgreSQL | Physical (pgBackRest) + WAL archiving | Full weekly, incremental daily, WAL continuous | 90 days + monthly for 7 years | 7-year tail is a Part 11 record-retention decision |
| Z1 landing | Object-lock, versioned | Immutable on write | **Permanent** | The reproducibility guarantee (§P3) |
| Z2/Z3 lake | Versioned; rebuildable from Z1 | On release | 3 releases | Derived — rebuild is cheaper than storage |
| Model artefacts | Versioned object storage | On registration | **Permanent** | Rollback requires prior artefacts |
| Feature store | Versioned | On materialisation | Current + 2 prior | Recomputable |
| Secrets | Secret-manager native backup | Continuous | Per policy | Separate key custody |

**Z1 retention is permanent, and this is a scientific requirement, not a storage decision.** Upstream sources do not guarantee old releases remain available — ChEMBL removes them, PubChem is continuously mutable. Our Z1 snapshot *is* the reproducibility guarantee (Phase 1 Step 2 §7.4). Deleting it to save storage would silently void every reproducibility claim in the system.

**Restores are tested quarterly**, into an isolated environment, with the result recorded. An untested backup is a hypothesis.

---

## 10.6 Database Migrations

**Forward-only, expand-contract**, so that old and new application versions can run simultaneously during a rollout:

1. **Expand** — add the new column/table, nullable or defaulted. Deploy. Both versions work.
2. **Migrate** — backfill in batches, monitored.
3. **Dual-write** — new code writes both; old code still reads the old shape.
4. **Switch** — new code reads the new shape. Deploy. Verify.
5. **Contract** — drop the old column in a **later release**, once rollback to the pre-expand version is no longer required.

Contract is a separate release. Dropping in the same release removes the rollback path exactly when it is most likely to be needed.

**Long-running migrations run outside the deployment**, as a controlled operation with progress monitoring. A migration inside a deployment step turns a 40-minute backfill into a 40-minute outage.

**Every migration is tested against a production-sized dataset in staging** before production, with timing recorded. A migration that takes 8 seconds on dev data may take hours on 24.5M rows.

---

## 10.7 Rollback

| Failure | Action | Target |
|---|---|---|
| Bad application release | Redeploy prior image digest | < 5 min |
| Bad model | Re-point `champion` alias (§6.10) | < 1 min |
| Bad descriptor spec | Roll back `descriptor_spec_version`; flag affected predictions | < 15 min |
| Bad migration (expand phase) | Deploy prior version; new column unused | < 10 min |
| Bad migration (post-contract) | **Restore from backup** | Hours |
| Bad Core DB release | Repoint to prior release; models pinned to snapshots remain valid | < 1 h |
| Data corruption | PITR to before the event | Hours |

The gap between "expand phase" and "post-contract" is precisely why contract is deferred to a later release.

---

## 10.8 Disaster Recovery

| Metric | Target | Basis |
|---|---|---|
| **RPO** (max data loss) | 15 minutes | WAL archiving interval |
| **RTO** (max downtime) | 4 hours | Restore + verification time |
| Z1 durability | 11 nines | Object storage guarantee |

| Scenario | Response |
|---|---|
| Single service failure | Orchestrator restarts; redundant replicas absorb |
| Database primary failure | Promote replica; DNS/connection-string failover |
| Object storage unavailable | API degrades to read-only for existing data; ingestion pauses |
| Region failure | Restore into a secondary region from backup (RTO 4 h) |
| Ransomware / destructive compromise | Rebuild from IaC; restore from immutable, object-locked backups |

Object-lock on backups is the specific control against ransomware: an attacker with full production credentials still cannot delete or encrypt a locked backup within its retention window.

**DR is exercised annually** with a documented result. An untested DR plan is documentation, not a capability.

---

## 10.9 Health Checks

| Endpoint | Checks | Failure behaviour |
|---|---|---|
| `GET /health` | Process alive only | Orchestrator restarts the container |
| `GET /health/ready` | DB, object storage, queue reachable | Removed from load balancer; **not restarted** |
| Worker heartbeat | Job processed within window | Worker recycled |
| Dagster sensor | Asset materialisation freshness | Alert |

**Liveness must not check dependencies.** If it did, a brief database outage would cause every application container to be killed and restarted simultaneously — converting a recoverable dependency blip into a full cascading outage with a cold-start thundering herd. This distinction is frequently collapsed and the consequence is severe.

---

## 10.10 Observability in Production

Covered in §3.9–§3.10. Deployment-specific additions:

| Signal | Alert | Route |
|---|---|---|
| Error rate > 1% (5 min) | Page | On-call |
| p95 latency > 2× baseline | Page | On-call |
| Readiness failing > 2 min | Page | On-call |
| Queue depth growing 15 min | Page | On-call |
| **Audit write failure** | **Page** | On-call + compliance |
| **Cross-tenant access attempt** | **Page** | On-call + security |
| Feature-set mismatch (should be 0) | Page | On-call + ML owner |
| OOD rate rising vs baseline | Ticket | ML owner, weekly review |
| Conformal coverage degrading | Ticket | ML owner |
| Source staleness past cadence | Ticket | Data owner |

**Audit write failure and cross-tenant attempts page immediately**, ranking with availability incidents. Under Part 11 an unaudited change is a compliance failure, and a cross-tenant attempt is a potential IP disclosure — neither can wait for business hours.

Scientific signals raise tickets rather than pages: a rising OOD rate means users are querying novel chemistry, which is information to act on, not an outage.

---

*End §10.*
