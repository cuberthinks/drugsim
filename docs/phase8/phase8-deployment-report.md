# Phase 8 — Deployment, Infrastructure & Controlled External Access

## Readiness classification: **CONTROLLED DEMONSTRATION READY**

Suitable for limited external demonstrations and research use by a small,
known audience, given the manual setup steps in "Known limitations" below
are completed first (principally: generate `poetry.lock`, provision model
artifacts onto the build host, and set a real domain/API keys). **Not**
LIMITED PUBLIC ACCESS READY — the gaps that block open public access
(no real multi-tenant auth, no distributed rate limiting, an unresolved
dependency-lock/model-artifact provisioning story) are architectural, not
cosmetic. Not clinically validated, not medically certified, not
regulatory approved, not production medical software — this deployment
makes no such claim.

No new prediction models were created or retrained. The validated
`herg_inhibition` v0.1.0 model's methodology is unchanged. Every addition
in this phase is infrastructure, configuration, security, or operational
tooling around the existing, already-validated system.

---

## 1. Architecture

```
User
 ↓ HTTPS (Caddy, automatic via Let's Encrypt once a real domain is set)
Frontend (static React build, served by Caddy)
 ↓ /api/* reverse-proxied, same-origin, path-stripped
Prediction API (FastAPI, src/drugsim_predict)
 ↓
Validated model (herg_inhibition v0.1.0, checksum-verified at load)
 ↓
SQLite audit log (var/predictions.sqlite3, its own volume)
```

**Deliberately not added**: Kubernetes, a message queue, Redis, or a
second database for the prediction service. This is a single-model,
single-endpoint, synchronous, low-QPS service — none of that
infrastructure is demonstrated to be necessary, and Phase 8's own brief
says not to introduce it without one.

**Two independent service groups**, wired together only by
`deployment/compose/docker-compose.yml`, not by any runtime dependency:

- `postgres` / `minio` / `minio-init` — the Phase 2 data platform (ETL,
  compound/measurement storage). Unchanged this phase.
- `predict-api` / `frontend` — the Phase 5/6 user-facing service, newly
  containerized this phase (`deployment/docker/Dockerfile.predict-api`,
  `Dockerfile.frontend`, `deployment/caddy/Caddyfile`).

**Why `predict-api` does not use PostgreSQL** (Phase 8 Sec 1's "where
required" PostgreSQL path): this was a deliberate Phase 5 decision,
unchanged here per "do not redesign the existing architecture unless a
deployment requirement makes it necessary." The prediction audit log is a
single table, single-writer-at-a-time, low-volume, and SQLite's own
online-backup API (used by `scripts/backup_predictions_db.py`) already
gives it consistent, verifiable backups without provisioning a database
server. Migrating it to Postgres would be a genuine architecture change,
not a deployment-hardening one, and nothing in this phase's requirements
demonstrated a need for it. The existing Postgres+RDKit image and its full
Alembic migration chain (Phase 2, `database/migrations/`) were verified
this phase (`alembic history` resolves to a single linear head, `0013`, no
gaps or branches) and remain available for the rest of the platform.

**Model storage**: model artifacts live under `models/admet/herg_inhibition/artifact/`
and are loaded from local disk, checksum-verified on every load
(`drugsim_predict.model_registry`). They are gitignored (correctly — large
binaries, not source) and copied into the `predict-api` image at build
time; see "Known limitations" for the resulting build-time prerequisite.

## 2. Security

- **Authentication/authorization** (Sec 6): `drugsim_predict.security.ApiKeyMiddleware`
  gates every route except `/health`, `/health/ready`, and API docs behind
  a shared `X-API-Key` when `DRUGSIM_PREDICT_API_KEYS` is configured. This
  is explicitly not a multi-tenant identity platform — there is no
  user/tenant model anywhere in this codebase, and building one is out of
  scope ("do not build a complex enterprise identity platform unless
  required"). `drugsim_predict.settings.assert_safe_to_start` refuses to
  start the service in a `staging`/`production` environment with no key
  configured — a misconfigured deployment fails to boot rather than
  silently serving the internet unauthenticated. A stronger, simpler
  alternative for the browser path — HTTP Basic Auth at the Caddy layer,
  covering the whole site with the browser's native prompt, no key baked
  into the JS bundle — is documented (commented out) in
  `deployment/caddy/Caddyfile` and recommended for a real controlled
  demonstration.
  - **Known limitation**: there is no per-user data isolation, because
    there is no per-user data model. `GET /predict/{id}` returns any
    prediction to any holder of a valid API key/prediction ID (IDs are
    unguessable ULIDs, but this is not the same guarantee as real
    authorization). Acceptable for "a small, known set of users share
    access to a demonstration," not acceptable for public multi-tenant use.
- **Rate limiting & abuse protection** (Sec 7): `RateLimitMiddleware`
  (per-API-key or per-IP sliding window, default 30 req/min),
  `BodySizeLimitMiddleware` (64 KiB cap, checked via `Content-Length` and
  by capping bytes actually read), `ConcurrencyLimitMiddleware` (bounded
  semaphore, default 10 concurrent, returns 503 rather than queuing
  indefinitely). All three are real, tested middleware (13 new tests,
  `tests/unit/test_predict_security.py`), verified live against a running
  server (health checks always exempt; 429/413 responses confirmed with
  correct `Retry-After`/problem+json bodies).
  - **Known limitation**: in-memory, single-process state — correct for
    this deployment's single-worker topology, not a distributed rate
    limiter. Documented in `security.py`'s module docstring.
- **Chemical input security** (Sec 8, TDS Sec 7.7): the TDS's full design
  (100 MB uploads, ≤10,000 records, subprocess isolation with
  `rlimit`/seccomp) targets a batch-upload workload this phase does not
  have — Phase 5 already scoped this service to single, small
  (≤6,000-char) inline structures, synchronous. What TDS Sec 7.7 asks for
  that DOES apply here — a hard timeout on a hanging parse — was
  previously entirely unenforced (`request_timeout_seconds` was declared
  but never used). **Fixed**: `/predict` now runs inference under
  `asyncio.wait_for` with a configurable wall-clock timeout, verified live
  (a simulated 2-second hang returned a clean 503 in ~0.2s). Honestly
  documented residual limitation: a timed-out Python thread cannot be
  forcibly killed, so a genuinely hung parse keeps consuming a thread-pool
  slot in the background — this bounds response time and protects the
  event loop, not memory/CPU consumption the way true subprocess isolation
  would. True process isolation is out of scope for this phase's minimal
  surface (see `api.py`'s `predict()` docstring for the full reasoning).
- **Secrets**: never hardcoded. `.env.example` (root) and
  `frontend/.env.example` document every variable with no real values.
  `.gitignore` covers `.env`, `.env.local`, `.env.*.local`, and (added this
  phase) `.env.development`/`.env.production`/`.env.staging`. API keys are
  read from `DRUGSIM_PREDICT_API_KEYS` only, never logged (verified: the
  settings field is never passed to any `log.*()` call).
- **Model change control** (Sec 14): every artifact in the model bundle
  (classifier, calibration data, descriptor scaler, and — closed in Phase
  7 — the inference-support manifest) is SHA-256 verified before load;
  mismatch or absence is a hard `IntegrityError`, never a silent
  substitution. New this phase: `scripts/verify_model_integrity.py` runs
  the same check as an explicit CI/deploy gate (verified live, both the
  pass and the fail-on-tamper path); `get_model_bundle()` now logs a
  `model.loaded` event with the full model identity exactly once per
  process, giving every deployment a permanent, searchable record of which
  model was active and when. No automatic retraining exists anywhere in
  this codebase.

## 3. Operations

- **Logging** (Sec 9): structured JSON via structlog, with the Phase 7
  redaction pipeline (verified this phase to actually be wired into the
  running process, not just built) now also carrying `duration_ms` on
  every `/predict` exit path (success, rejection, timeout, unexpected
  error) — latency is derivable from the log stream without a separate
  metrics system. Severity levels are used consistently: `info` for
  expected outcomes, `error` for actionable failures.
- **Monitoring**: request volume and API errors are derivable from the
  existing per-request log events (`predict.request`/`predict.complete`/
  `predict.rejected`/etc.) by whatever log pipeline ingests them.
  Resource usage (CPU/memory) is intentionally left to the deployment's
  own infrastructure layer (`docker stats`, a cloud provider's built-in
  container/VM metrics) rather than a custom in-app exporter — introducing
  a metrics-scraping stack (Prometheus, etc.) for a single-process service
  was judged unnecessary infrastructure per the brief's own instruction.
- **Health checks** (Sec 10): `/health` (liveness) unchanged.
  `/health/ready` rewritten to check all four required components —
  application, database (this service's real dependency, SQLite, not
  Postgres), model, and prediction engine (an actual end-to-end test
  inference on a fixed molecule, ethanol) — independently, so one failing
  component never masks another. Verified not to leak internal diagnostic
  detail (a checksum-mismatch message embedding a filesystem path was
  previously exposed on this public, unauthenticated endpoint — now only a
  safe `ok`/`unavailable` status per component is returned publicly, with
  the real exception logged server-side). 6 new tests.
- **Error tracking & recovery** (Sec 11): every route has a last-resort
  exception handler (Phase 7) that returns a safe, understandable
  `problem+json` error and never a fabricated prediction; the new
  `/predict` timeout path follows the same pattern. Internal logs carry
  exception *type* and a structure digest, never a raw exception message
  that could embed a structure (RDKit's own diagnostics sometimes do).
- **Backups** (Sec 12): `scripts/backup_predictions_db.py` (SQLite's own
  online-backup API, not a raw file copy, so a backup taken mid-write is
  still consistent) and `scripts/restore_predictions_db.py` (refuses an
  unverifiable or checksum-mismatched backup, preserves whatever was at
  the destination as a `.pre-restore` copy). **A full disaster-recovery
  cycle was actually performed, not just coded**: seed a database, back it
  up, delete the "live" file, restore, and verify both row count and exact
  row content matched the original — confirmed working, plus the
  corrupted-backup and missing-checksum-sidecar rejection paths, all
  pinned by 7 automated tests (`tests/unit/test_backup_restore.py`).
  Retention/storage-location policy: keep daily backups for 30 days,
  weekly for 6 months, stored off the application host (a mounted volume
  is the minimum; a cloud object store is recommended for a real
  deployment) — this script performs and verifies one backup; scheduling
  and off-host upload are deployment-time wiring, not implemented as new
  infrastructure here.

## 4. CI/CD

Extended `.github/workflows/ci.yml` (existing jobs: quality, test,
security-controls, constraints, supply-chain, licence-audit, docker) with:

- `frontend` — lint, unit test, build, Playwright E2E (including the new
  accessibility and responsive-layout suites) — all runnable standalone in
  CI since the E2E tests mock the API via `page.route`, needing no live
  backend.
- `model-integrity` — runs `scripts/verify_model_integrity.py` as an
  explicit gate before any image is built.
- `docker` — extended to also build `Dockerfile.predict-api` and
  `Dockerfile.frontend`, gated on `test` and `model-integrity` passing
  first.
- `deploy-and-smoke-test` — documents the intended final pipeline stage
  (manual `workflow_dispatch`, a GitHub `production` Environment for real
  secrets/URLs, `scripts/smoke_test_deployment.py` run against the live
  result). The deploy step itself is an explicit placeholder — there is no
  real deployment target in this environment to deploy to.

Pipeline shape now matches Sec 13's diagram: Commit → Lint → Unit →
Integration (constraints) → Security → Build → Deploy → Smoke tests. A
failing model-integrity or test job blocks the docker/deploy jobs via
`needs:`.

**Incidental fix found while building the new Docker image**: both
`Dockerfile.app` (pre-existing) and the new `Dockerfile.predict-api` had a
path mismatch between the builder and runtime stages that could break
under Poetry's default editable root-package install (source copied to
`/build/src` at build time, but only `/app/src` from the build *context*
in the runtime stage — a different physical location). Fixed in both by
keeping the source path identical (`/app/src`) across stages.

## 5. Scientific integrity

- **Model versioning/checksums**: unchanged from Phase 5/7 — every
  prediction's `provenance` block includes `model_id`, `model_version`,
  `model_checksum`, `dataset_version`, `feature_set_id`,
  `standardization_pipeline_version`, `descriptor_spec_version`,
  `rdkit_version`, and `input_hash`. Verified live against the running
  service this phase.
- **Prediction provenance**: unchanged — every request, success or
  failure, is recorded in the audit log with its input hash and (on
  success) canonical structure hash.
- **Model change control**: covered in "Security" above.
- **No automatic retraining, no new endpoints, no methodology change**:
  confirmed by inspection — this phase touched no file under
  `src/drugsim_chem/`, `models/admet/herg_inhibition/*.py` (training/
  export scripts), or the conformal/AD calculation logic itself.

## 6. External access

- **Domain**: no real domain is available in this environment. Placeholder
  used throughout: `drugsim.example` (the `.example` TLD, reserved by IANA
  under RFC 2606 specifically so documentation never accidentally
  references a domain someone actually owns) — see
  `deployment/caddy/Caddyfile`. **Manual setup required**: set
  `DRUGSIM_DOMAIN` to the real hostname; Caddy then obtains and renews a
  real Let's Encrypt certificate automatically.
- **HTTPS**: Caddy terminates TLS and sets `Strict-Transport-Security`,
  `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and a
  `Content-Security-Policy` scoped to what the app actually loads (self +
  Google Fonts). Validated: `caddy validate` runs as a Docker build step
  for the frontend image (not run live in this sandbox — no `caddy`
  binary available here; the Caddyfile syntax was reviewed carefully by
  hand against Caddy v2's documented directives).
- **Limitations**: no true multi-tenant authorization; a shared API key
  that is not a real secret once shipped to a browser (documented, with a
  stronger Basic Auth alternative provided); in-memory (non-distributed)
  rate limiting; no monitoring/alerting beyond structured logs.
- **Intended users**: researchers, collaborators, and reviewers evaluating
  the tool — stated explicitly on the new About page — not the general
  public, and not for clinical, diagnostic, or regulatory use (Privacy
  Policy, Terms of Use, and the pre-existing Limitations page all restate
  this consistently).

## 7. Frontend production readiness

- **Responsive layout — real bug found and fixed**: every single page had
  horizontal overflow on a mobile-width viewport (390px). Root causes: (1)
  the header nav didn't wrap when the wordmark + three nav links exceeded
  the available width; (2) `MoleculeStructure`'s SVG carried fixed pixel
  `width`/`height` attributes (set by the `smiles-drawer` library at draw
  time) that never shrank on a narrow screen. Both fixed with minimal CSS
  changes (flex-wrap on the header; a responsive CSS class overriding the
  library-set SVG attributes) — verified via Playwright at a 390×844
  viewport across all 7 static pages and the populated results view (with
  the Model & Evidence panel expanded), now pinned by 8 new automated
  tests (`e2e/responsive.spec.ts`).
- **Production API URL / no localhost**: the client already defaulted to
  a relative `/api` base URL (Phase 6) — correct for this phase's
  same-origin Caddy reverse-proxy topology, no override needed. Confirmed
  zero `localhost` references anywhere in `frontend/src` or `index.html`
  (the only `localhost` reference in the whole frontend is Vite's own dev
  server proxy config, which never ships in the production build).
- **No debug UI / no exposed secrets**: confirmed no `console.log`/`console.debug`
  calls anywhere in application code. The optional `VITE_API_KEY` (added
  this phase, paired with the backend's API-key gate) is explicitly
  documented as not a real secret once built into the bundle — the
  Caddy Basic Auth alternative is recommended for anything needing a real
  barrier.
- **Error states, loading states, accessibility**: unchanged from Phase 7
  (0 WCAG 2.1 AA violations across all pages, including 3 new ones this
  phase — About, Privacy, Terms — added to the automated scan).
- **HTTPS compatibility**: the app makes no assumptions about scheme;
  same-origin relative API calls work identically over HTTP or HTTPS.

Legal/scientific pages added this phase: `/about` (About DrugSim +
contact, with an explicitly placeholder `research@drugsim.example`
address, marked for replacement before real external use), `/privacy`,
`/terms` — all linked from every page's footer, all restating the required
disclaimers (computational estimate, not a diagnosis, not a safety
guarantee, does not replace lab/clinical testing, single validated
endpoint only, applicability-domain-dependent reliability, no regulatory
claim).

## 8. Test suite growth this phase

- Backend: 584 → 611 tests (+27: 13 security-middleware, 6 health-check,
  3 timeout, 1 model-registry manifest-checksum-adjacent, 7 backup/restore
  restoration cycle — all passing).
- Frontend unit: 44 → 48 tests (+4: API-key header, 401/429 classification).
- Frontend E2E: 9 → 20 tests (+11: 3 new pages added to the accessibility
  scan, 8 new responsive-layout checks).
- New standalone scripts, each manually run end-to-end at least once
  against a live local instance: `verify_model_integrity.py`,
  `backup_predictions_db.py` / `restore_predictions_db.py`,
  `smoke_test_deployment.py`.

## 9. Known limitations (manual setup required)

These are the concrete, honest gaps between "this repository's deployment
configuration" and "a live, running, publicly-reachable DrugSim":

1. **No `poetry.lock` exists in this repository** (a pre-existing Phase 7
   finding, still open). `pyproject.toml` requires Python `^3.12`; this
   sandboxed environment only had Python 3.9 available, so a real `poetry
   lock` could not be generated here despite network access being
   available. **This blocks every Docker build in this repository**
   (`Dockerfile.app`, the new `Dockerfile.predict-api`) at the
   `COPY pyproject.toml poetry.lock` step. Manual fix: run `poetry lock`
   on a machine with Python 3.12 + Poetry installed, review the diff,
   commit `poetry.lock`.
2. **Model artifacts are not fetchable in CI or a fresh clone.**
   `models/**/*.joblib` and `models/**/artifact/` are correctly gitignored
   (large binaries), but this repository implements no mechanism to fetch
   them from an artifact store. `scripts/verify_model_integrity.py` and
   the `predict-api` Docker build both correctly fail loudly (never
   silently substitute a different model) when they are absent — that is
   the intended, safe behaviour — but someone must provision them onto the
   build host first. Manual fix: copy the artifacts from the training/
   validation environment, or wire up a real artifact store (S3/GCS/DVC/
   MLflow) and add a fetch step to the Dockerfile and CI.
3. **No real domain, TLS certificate, or cloud infrastructure exists.**
   `DRUGSIM_DOMAIN` defaults to the reserved `drugsim.example` placeholder.
   Manual fix: point a real domain's DNS at the deployment host and set
   `DRUGSIM_DOMAIN`; Caddy handles certificate issuance automatically from
   there.
4. **No real API keys, secrets, or GitHub Environment are configured.**
   `DRUGSIM_PREDICT_API_KEYS` must be generated and set before this
   service can start in `staging`/`production` (it refuses to start
   without one — this is intended, not a bug to route around). The CI
   `deploy-and-smoke-test` job references a GitHub `production` Environment
   and `DRUGSIM_SMOKE_*` variables/secrets that do not exist yet.
5. **The `docker`/`model-integrity`/`predict-api`/`frontend`-build CI jobs
   are expected to fail today**, honestly, for the two reasons above —
   left as real, hard-failing jobs rather than disabled, per the brief's
   instruction not to sacrifice reproducibility for a green pipeline.
6. **No true multi-tenant authorization or distributed rate limiting** —
   both explicitly out of scope per the brief ("do not build a complex
   enterprise identity platform unless required"), appropriate for a
   small, known, controlled audience, not for open public access.
7. **No automated resource-usage (CPU/memory) monitoring** — deliberately
   deferred to the deployment's own infrastructure layer rather than
   building a custom exporter.
8. **The Postgres+RDKit migration chain was verified structurally
   (`alembic history`, single linear head) but not executed against a live
   database in this sandbox** — no Docker daemon was available here. The
   existing `tests/constraints` suite already does this for real in CI
   (via testcontainers) whenever Docker is available.
9. **`Dockerfile.frontend`'s `caddy validate` step and every Dockerfile's
   actual `docker build`** were reviewed carefully by hand but could not
   be executed in this sandbox (no Docker daemon available) — correctness
   is high-confidence, not empirically proven end-to-end the way the
   Python-level scripts and tests in this phase were.

## Readiness classification, restated

**CONTROLLED DEMONSTRATION READY**, contingent on completing the manual
setup steps in Sec 9 above (principally #1 and #2, which block any Docker
image from building at all). The application-level work — security
middleware, health checks, backups, timeouts, model change control,
smoke tests, legal pages, responsive-layout fixes — is complete, tested,
and in several cases verified against a live running instance in this
session, not merely written. What remains is infrastructure provisioning
this sandboxed environment could not perform: a Python 3.12 lockfile, real
model artifact transport, a real domain, and real secrets.

Not classified as clinically validated, medically certified, regulatory
approved, or production medical software.

Phase 8 is complete. Do not start Phase 9.
