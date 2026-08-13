# TDS §3 — Technology Stack

**Extends:** Phase 1 Step 10 (data-layer selection, licence audit, comparison matrix)

Phase 1 Step 10 selected and justified the data layer: PostgreSQL 16 + RDKit cartridge, DuckDB, MinIO/S3, Parquet, Dagster, Python/RDKit/Polars. Those decisions stand and are not re-argued here. This section covers the **application-layer technologies Step 10 did not address** — backend framework, message queue, authentication, containerisation, deployment, CI/CD, monitoring, logging, testing — with the same rigour.

---

## 3.1 Selection Criteria

Unchanged from Step 10 and worth restating because they invert the usual ordering: reproducibility → correctness guarantees → licence compatibility → operational simplicity → regulatory fit → **performance last**. The largest artefact is ~5.4 GB and the ADMET training sets are ≤13,130 rows. Choosing for scale we do not have would cost us on the criteria where the real risk lives.

---

## 3.2 Data Layer — Decided in Phase 1

| Component | Choice | ADR |
|---|---|---|
| System of record | **PostgreSQL 16 + RDKit cartridge** | ADR-003 |
| Analytical engine | **DuckDB** | ADR-002 |
| Object storage | **MinIO (dev) / S3-compatible (prod)** | ADR-011 |
| Lake format | **Parquet** + manifest versioning | ADR-010 |
| Workflow engine | **Dagster** | ADR-006 |
| Feature store | **Content-addressed Parquet** | ADR-005 |
| Knowledge graph | **Neo4j, Phase 6, conditional** | ADR-004 |
| Chemistry toolkit | **RDKit** (BSD-3) | — |

**Operational constraint to plan around:** the RDKit cartridge is unavailable on managed Postgres (RDS, Cloud SQL, Aurora). DrugSim runs self-managed Postgres or a container. Accepted in ADR-003 because the capability is central, but it shapes §9 (deployment) and the backup strategy materially.

---

## 3.3 Backend Framework — **FastAPI**

**Chosen because** the scientific stack is Python and the alternative is a language boundary between the API and the code that computes descriptors. That boundary is exactly where training/serving skew is reintroduced (P6, R6). FastAPI additionally gives Pydantic validation — which maps directly onto the data contracts in §4 — and generates OpenAPI, making the API specification executable rather than aspirational.

| Alternative | Assessment |
|---|---|
| **Django + DRF** | Batteries-included, mature admin, strong ORM. Heavier than needed; async support retrofitted; the ORM would compete with the hand-designed schema |
| **Flask** | Minimal and familiar. No native async, no built-in validation or schema generation — we would rebuild what FastAPI provides |
| **Litestar** | Technically comparable, arguably cleaner DI. Smaller ecosystem and hiring pool; not enough advantage to offset that |
| **Go / Rust service** | Better raw throughput and lower memory. **Rejected: introduces a language boundary to the chemistry code.** Performance is not the constraint |

**Advantages:** one language end to end; Pydantic contracts shared between API and workers; async I/O suits a job-dispatch API; OpenAPI generation supports contract testing.
**Disadvantages:** Python throughput ceiling (irrelevant here — work happens in workers); async/sync discipline required around blocking RDKit calls, which must run in a thread pool or subprocess.
**Long-term:** stable, widely adopted, actively maintained. If a specific endpoint ever becomes throughput-bound, it can be extracted without moving the chemistry code.

---

## 3.4 Message Queue — **PostgreSQL-backed job queue**

This is the least conventional choice in the stack and the one most likely to be questioned, so the reasoning is given in full.

Prediction is asynchronous (§5.4). That needs a queue. The conventional answer is Redis or RabbitMQ with Celery.

**Chosen: a Postgres-backed queue** using `SELECT ... FOR UPDATE SKIP LOCKED` (via `procrastinate`, or a thin in-house implementation).

**The decisive argument is transactional enqueue.** With an external broker, creating a prediction job means writing to Postgres *and* enqueuing to the broker — two systems, no shared transaction. If one succeeds and the other fails, the system has either a job with no record or a record with no job. Handling that requires the outbox pattern or accepting silent inconsistency. With a Postgres-backed queue, the compound upsert and the job enqueue commit **in the same transaction**. The failure mode disappears rather than being managed.

Secondary: it is one fewer system to operate, secure, back up and audit (P10), and job history is queryable with the same audit guarantees as everything else — which matters under Part 11.

| Alternative | Assessment |
|---|---|
| **Celery + Redis/Valkey** | Industry standard, mature, good tooling. Dual-write problem; another system; Redis persistence semantics require care for job durability |
| **RabbitMQ** | Strong delivery guarantees, mature routing. Substantial operational surface for our throughput; still a dual-write |
| **Dagster for user jobs** | Already present. **Rejected:** Dagster is for scheduled data assets, not per-request user jobs; conflating them couples user latency to pipeline runs |
| **AWS SQS / managed queue** | Zero ops. Cloud lock-in and dual-write; also unavailable in self-hosted deployments, which §9 keeps open |

**Advantages:** transactional correctness; one fewer system; auditable job history; trivially backed up with the database.
**Disadvantages:** lower maximum throughput than a dedicated broker; queue load competes with query load on the primary; fewer off-the-shelf features (priority routing, dead-letter exchanges) — though `SKIP LOCKED` with a retry column covers what we need.
**Long-term / migration trigger:** move to a dedicated broker when sustained job rate exceeds ~100/s or queue contention appears in Postgres metrics. Neither is remotely near expected load, and the queue interface is abstracted so the swap is contained.

---

## 3.5 Authentication — **OIDC via Keycloak**

**Do not build authentication.** Under Part 11 the identity layer carries regulatory requirements — unique individual accounts, password policy and ageing, account lockout, and controls binding an electronic signature to a specific person (§11.100, §11.300). A homegrown implementation would need to satisfy all of that and be validated.

**Chosen: Keycloak**, self-hosted, OIDC/OAuth 2.0.

| Alternative | Assessment |
|---|---|
| **Auth0 / Okta** | Excellent, lower ops. Per-user cost; **customer identity data leaves our control**, which complicates the confidentiality posture in §7 for pharma customers |
| **AWS Cognito** | Cheap, integrated. Cloud lock-in; weaker on the Part 11 control set |
| **Homegrown** | **Rejected.** Regulatory burden and security risk with no upside |
| **Ory Kratos/Hydra** | Good, composable, Apache-2.0. More assembly required; Keycloak covers the Part 11 controls out of the box |

**Advantages:** Apache-2.0; self-hostable (no customer identity leaves the deployment); supports MFA, password policy, ageing, lockout, session control, and fine-grained roles mapping onto `system_user.role`; SAML/LDAP federation for enterprise customers, which pharma will ask for.
**Disadvantages:** heavyweight; a real operational component to run and upgrade; configuration is intricate.
**Long-term:** widely deployed in regulated environments; federation support is what makes enterprise sales feasible without rework.

---

## 3.6 Containerisation — **Docker / OCI**

All services containerised; images built in CI, tagged by git SHA, digest-pinned in deployment.

**The custom image that matters: `postgres-rdkit`.** Because the cartridge is unavailable in managed Postgres, DrugSim maintains its own Postgres+RDKit image. This is a first-class artefact, not a convenience — the RDKit version inside it participates in `toolchain_id` and therefore in reproducibility. It is version-pinned, digest-referenced, scanned, and changed only through change control.

Base images: `python:3.12-slim` for services; distroless considered for production but deferred — RDKit's system dependencies make it awkward, and the security gain is modest relative to the debugging cost.

---

## 3.7 Deployment & Orchestration — **Docker Compose → Kubernetes when justified**

**Chosen: Docker Compose for development and initial single-node production; Kubernetes only when a named requirement demands it.**

This is P10 applied honestly. DrugSim's Phase 2 topology is one Postgres, one object store, an API, and a handful of workers. Kubernetes for that is substantial operational complexity — cluster upgrades, networking, RBAC, storage classes — for capabilities not yet needed.

| Alternative | Assessment |
|---|---|
| **Kubernetes now** | Right answer eventually; premature for Phase 2. Would consume weeks that Phase 2 needs for the Core DB build |
| **Nomad** | Simpler than K8s, genuinely good fit. Smaller ecosystem and hiring pool |
| **Managed container service** (ECS, Cloud Run) | Low ops, good fit for stateless services. Awkward for self-managed Postgres+RDKit; some cloud lock-in |
| **Bare VMs + systemd** | Simplest. Loses reproducible deployment and easy rollback |

**Migration triggers to Kubernetes:** multi-region requirement, customer-mandated on-prem with existing K8s, sustained need for autoscaling workers, or a team large enough that deploy contention becomes a bottleneck.

**Infrastructure as code from day one** (Terraform), regardless of orchestrator. Manually configured infrastructure cannot be reproduced, and under a regulatory path an unreproducible environment is a validation gap.

---

## 3.8 CI/CD — **GitHub Actions**

Assumes GitHub hosting; GitLab CI is an equivalent substitute if hosting differs.

**Required checks on every PR** (§8): lint (`ruff`) · format (`ruff format`) · type-check (`mypy --strict` on `src/`) · unit tests · **constraint tests** · **golden-set regression** · **licence audit** · dependency vulnerability scan · SBOM generation.

Three of these are DrugSim-specific and are the ones that protect Phase 1's guarantees:

- **Constraint tests** — a migration that drops a CHECK passes every functional test; the system works, it simply no longer prevents what the constraint prevented. Each constraint needs a test asserting a violating insert *fails*.
- **Golden-set regression** — catches the failure where a standardisation change silently alters hundreds of thousands of structures.
- **Licence audit** — verifies tier mapping, that no black-tier source reaches a commercial artefact (LC-03), and that the attribution manifest is current. Without it, licence discipline decays into a document nobody reads.

**Deployment:** tagged releases → staging automatically → production on manual approval. Under the regulatory path, production deployment requires a recorded approval with an electronic signature, which is why it is never fully automatic.

---

## 3.9 Monitoring — **Prometheus + Grafana + OpenTelemetry**

Instrumentation via OpenTelemetry (vendor-neutral, avoids lock-in); metrics to Prometheus; dashboards in Grafana; traces to Tempo/Jaeger.

**Scientific metrics matter as much as system metrics**, and this is where a conventional monitoring setup falls short. Alongside latency and error rate, DrugSim monitors:

| Metric | Why |
|---|---|
| **OOD prediction rate by endpoint** | A rising rate means users are querying chemistry the models do not cover — the earliest signal of applicability drift |
| **Interval width distribution** | Widening intervals indicate degrading confidence |
| **PK consistency failure rate** | Physically incoherent prediction sets (Phase 1 Step 5 §5) |
| **Feature-set mismatch attempts** | Should be zero; non-zero means a deployment error |
| **Prediction-vs-outcome agreement** | Where experimental results later arrive — the only true accuracy signal |
| **Source freshness vs registry cadence** | Detects upstream decay (DrugCentral already slowed; SIDER already dead) |

Alerting: latency/error/saturation page immediately; scientific metrics raise tickets and appear in a weekly review rather than paging. A rising OOD rate is a signal to investigate, not an incident.

---

## 3.10 Logging — **Structured JSON + OpenTelemetry**

Structured JSON to stdout; collected by the platform log stack (Loki or equivalent); correlated with traces by `trace_id`. Every log line carries `request_id`, `user_id`, `tenant_id` and — where applicable — `prediction_uid`.

**Mandatory redaction: customer molecular structures must never appear in logs.**

A pharma customer uploading a novel structure is sharing their most commercially sensitive asset. A SMILES string in a log line — an exception message, a debug statement, a validation error — is an IP disclosure into a system with different access controls and retention than the database, and log aggregation typically fans out further still.

Enforcement is layered, because a policy alone will not hold:
1. A logging filter that redacts anything matching SMILES/InChI patterns
2. Structures referenced in logs by `compound_uid` only, never by structure
3. Exception handlers that scrub payloads before logging
4. A lint rule flagging interpolation of structure-bearing variables into log calls
5. A CI test asserting that a request carrying a known structure produces no log line containing it

Item 5 is the one that actually holds the line; the rest are defence in depth.

**Retention:** application logs 90 days; audit log retained per the Part 11 record retention policy (a compliance decision, §7).

---

## 3.11 Testing — **pytest + Hypothesis + testcontainers + Schemathesis**

| Tool | Role |
|---|---|
| **pytest** | Test runner; fixtures |
| **Hypothesis** | **Property-based testing for chemistry invariants** |
| **testcontainers** | Real Postgres+RDKit for integration and constraint tests |
| **Schemathesis** | Contract testing generated from the OpenAPI schema |
| **pytest-benchmark** | Performance regression |

**Hypothesis deserves specific mention** because chemistry has genuine invariants that example-based tests cover poorly, and property-based generation finds the pathological molecules a human would not think to write:

- Standardisation is idempotent: `f(f(m)) == f(m)`
- SMILES round-trip: `parse(canonical(parse(s))) ≡ parse(s)`
- `inchikey_skeleton == inchikey_full[:14]` for every valid molecule
- Descriptor monotonicity: adding a heavy atom never decreases `heavy_atom_count`
- Unit conversion round-trips within tolerance

**testcontainers is required, not optional**, because the schema pushes integrity into database constraints and triggers (`ck_not_predicted`, `uq_scaffold_single_group`, the ICH M7 pairing trigger). Those cannot be tested against SQLite or a mock; they need real Postgres with the real cartridge.

---

## 3.12 Stack Summary

| Layer | Technology | Licence | Phase |
|---|---|---|---|
| Backend | FastAPI + Pydantic | MIT / MIT | 2 |
| Database | PostgreSQL 16 + RDKit cartridge | PostgreSQL / BSD-3 | 2 |
| Analytics | DuckDB | MIT | 2 |
| Object storage | MinIO / S3-compatible | AGPLv3 / — | 2 |
| Lake format | Parquet | Apache-2.0 | 2 |
| Workflow | Dagster | Apache-2.0 | 2 |
| Job queue | Postgres-backed (`procrastinate`) | MIT | 2 |
| Auth | Keycloak (OIDC) | Apache-2.0 | 7 |
| Containers | Docker / OCI | Apache-2.0 | 2 |
| Orchestration | Compose → K8s (conditional) | — | 2 / TBD |
| CI/CD | GitHub Actions | — | 2 |
| Monitoring | Prometheus + Grafana + OTel | Apache-2.0 | 2 |
| Logging | Structured JSON + Loki | AGPLv3 | 2 |
| Testing | pytest · Hypothesis · testcontainers · Schemathesis | MIT-family | 2 |
| Knowledge graph | Neo4j Community | GPLv3 | 6 (conditional) |
| Vector search | pgvector | PostgreSQL | 8 |
| Experiment tracking | MLflow | Apache-2.0 | 3 |

**Licence flags carried from Step 10:** use **Valkey** rather than Redis and **OpenSearch** rather than Elasticsearch if either becomes necessary — both were relicensed in ways that complicate commercial use. MinIO's AGPL is fine for internal deployment but would matter for a distributed on-prem edition; cloud object storage sidesteps it. Neo4j Community is GPLv3 — acceptable for an internal read-only projection, verify before any distribution.

---

*End §3.*
