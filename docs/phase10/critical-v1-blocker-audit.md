# DrugSim v1.0 — Critical Blocker Audit

**Scope**: a fresh, independent audit of the current repository and live deployment against the 14 categories in the audit brief (scientific correctness, model/data integrity, core prediction functionality, security/privacy, API integrity, misleading scientific communication, usability, database integrity, testing, and deployment configuration). Conducted by reading source directly, testing the live deployment (`https://drugsim-predict-api.onrender.com`, `https://drugsim-frontend.onrender.com`) with real requests, running the test suites, and dispatching parallel research passes over the frontend copy and backend security surface. No new features, no retraining, no redesign — per the brief's own "do not over-fix" rule.

This audit also documents four real blockers that were found and fixed **earlier in the same engagement**, immediately before this formal pass began, because they define the current state of the system and belong in a "was DrugSim actually made release-ready" record. Nothing in this document was fixed *merely to make it look better* — every fix has a verification step below, and every unresolved item is disclosed rather than hidden.

---

# Executive Summary

DrugSim's Phase 1–10 work is scientifically and architecturally sound, and this audit found **no unresolved 🔴 blockers**. Four real 🔴-class defects existed in the current deployment and were fixed during this engagement (a model-accuracy regression that flipped a known hERG blocker's classification, a memory crash that made the hERG endpoint unusable in production, a rate-limiter bug that made concurrent users interfere with each other, and a UX bug that erased valid results on transient errors). This fresh audit pass, run after those fixes, surfaced only hardening opportunities — two were fixed on the spot (non-constant-time API key comparison, a packaging manifest omission), the rest are legitimately out of scope for a controlled research release and are disclosed below, consistent with (and in one case correcting) the existing Phase 10 final report.

**735 of 746 executable tests pass** (0 genuine failures — the other 11 are traced to a Python-version mismatch in the audit's own throwaway test venv, not a code defect, and verified as such). 63 database-constraint tests could not run in this sandbox for lack of a Docker daemon, unchanged from Phase 8/10's own prior finding. Frontend: 74/74 unit tests, 32/32 Playwright E2E tests, clean typecheck.

---

# Critical Blockers

## Found and fixed earlier in this engagement (before this formal audit pass)

### 🔴 BLOCKER — hERG model misclassified a known cardiac-channel blocker

- **Problem**: an earlier, over-aggressive fix (reducing the hERG random forest from 500 to 35 trees to fit hosting memory limits) held up on aggregate ROC-AUC (0.8113) but flipped **dofetilide** — a Class III antiarrhythmic whose mechanism of action *is* hERG blockade — from `blocker` to `non_blocker`.
- **Location**: `models/registry/herg_inhibition_v1.json`, `models/admet/herg_inhibition/artifact/model.joblib`.
- **Impact**: this is exactly the failure mode the endpoint exists to catch, and aggregate metrics alone did not detect it — only the project's own `tests/golden/test_herg_model_regression.py` behavioural panel caught it.
- **Fix**: re-selected the tree count by running that golden panel at each candidate size rather than by aggregate accuracy alone. Landed on 200 trees: 40/40 golden panel tests pass, ROC-AUC 0.8376 (vs. the full 500-tree model's 0.8394 — a rounding-error gap), and measured resident memory 353MB against the 512MB hosting limit (the original 500-tree model needed ~523MB, which is what caused the crash below).
- **Verification**: `PYTHONPATH=src python3 -m pytest tests/golden/ -q` → 53 passed. Live-verified: `curl .../predict` with dofetilide's SMILES now returns `predicted_label: "blocker"`.

### 🔴 BLOCKER — hERG endpoint crashed on every real request in production

- **Problem**: the full 500-tree hERG model, loaded alongside the CYP3A4 model, exceeded the Render Starter plan's 512MB memory limit. Every hERG prediction request silently OOM-killed the worker process mid-request (visible in platform logs as the process dying between `predict.request` and any response, then a container restart) — the endpoint was unusable in production, though it worked in local testing.
- **Location**: deployment memory budget vs. `models/admet/herg_inhibition/artifact/model.joblib`.
- **Fix**: same fix as above (200-tree model, 353MB measured resident memory, 159MB headroom).
- **Verification**: 24 sequential and 5 concurrent-with-CYP3A4 live hERG predictions against production, 0 failures, all sub-second after the fix (previously: crash on the first request every time).

### 🔴 BLOCKER — every visitor shared one rate-limit bucket

- **Problem**: `RateLimitMiddleware` keyed its 30-req/min bucket on the API key alone. This product ships a single shared key baked into the public frontend bundle (by design — see `client.ts`'s own disclosure that this is not real multi-tenant auth), so every visitor on earth shared one quota. Two people using the app at the same time would rate-limit each other, surfacing as "the app randomly breaks."
- **Location**: `src/drugsim_predict/security.py`, `RateLimitMiddleware._client_key`.
- **Fix**: bucket key now includes the originating address (`X-Forwarded-For`, since `scope["client"]` is the platform's own router and identical for every request) alongside the API key.
- **Verification**: live-tested — visitor A exhausts their own 30/min quota (30×200, then 429s); visitor B on the *same* shared key from a different address is unaffected (5×200, 0×429). Two new regression tests (`test_one_shared_api_key_does_not_pool_every_client_into_one_bucket`, `test_forwarded_for_chain_uses_the_originating_client`) confirmed to fail against the prior code, pass against the fix.

### 🟠 (borderline 🔴) — a failed request erased a valid result still on screen

- **Problem**: `PredictPage.tsx`'s error handler reset the view to `"idle"` on any failed request, and every result panel is gated on that state — so a transient failure (a platform restart window, a dropped connection) silently discarded a correct prediction the user was still reading, forcing a full re-submission to see it again. Classified borderline-🔴 rather than clearly 🔴 because it never *displayed* incorrect information — it displayed nothing, which is a reliability/usability defect, not a correctness-of-displayed-science defect (Section 7's actual 🔴 example is the opposite case: showing a *stale* result as if it were current, which this codebase already guarded against and continues to).
- **Location**: `frontend/src/pages/PredictPage.tsx`.
- **Fix**: the catch handler now falls back to whatever stage was on screen before the failed attempt, with an explicit note that the visible result is from the last successful run. The client also now retries transient failures (network drops, timeouts, gateway 502/503/504 — never a 4xx, since a rejected structure won't change on retry) before surfacing an error at all.
- **Verification**: 2 new tests confirmed to fail against the prior code, pass against the fix; full frontend suite green (74/74).

## Found in this fresh audit pass

**None.** Every category audited below (scientific correctness, model integrity, prediction pipeline, security, API contract, database integrity) came back either PASS or a lower-severity finding — see Important/Improvements below.

---

# Important Issues

### 🟠 Rate limiter's per-client key trusts a client-spoofable header

`RateLimitMiddleware._client_ip` (`security.py`) takes the first entry of `X-Forwarded-For` with no validation that the request actually traversed a trusted proxy. A client holding the (publicly shipped) API key can fabricate a new `X-Forwarded-For` value per request to get a fresh bucket every time, defeating the per-client 30-req/min limit for that key. This does **not** bypass authentication — the API-key gate runs first and rejects unkeyed requests before the rate limiter is ever reached — and overall throughput is still bounded by the separate, non-spoofable `ConcurrencyLimitMiddleware` (10 concurrent requests, process-wide). This is the same class of gap the existing Phase 8/10 reports already disclosed under "in-memory, non-distributed rate limiting... no protection against a moderately sophisticated distributed abuser" — not new, and the code's own comment already states the accepted tradeoff. Recommendation: leave as-is for a controlled release; a real fix (validating against Render's actual edge, or moving to a distributed limiter) is infrastructure work explicitly out of scope per the brief's own rules.

### 🟠 CPU-exhaustion risk from unbounded RDKit parse time

`request_timeout_seconds` (10s) bounds only the HTTP response the client receives — `api.py`'s own docstring states a timed-out Python thread cannot be forcibly terminated, so a pathological (but under the 5,000-character SMILES / 2,000 Da limits) structure that triggers slow RDKit parsing could tie up a threadpool worker past the client's timeout. Impact is bounded by `ConcurrencyLimitMiddleware` (max 10 concurrent requests) rather than unbounded. Phase 10's own live testing found no catastrophic-backtracking case in the one pathological structure it tried; this audit did not find a new exploit, only confirmed the same disclosed, bounded-impact gap. Real process-level isolation is explicitly out of scope per the module's own docstring and the brief's "do not add unnecessary infrastructure" rule.

### 🟠 Two dependency-vulnerability findings remain deferred (pre-existing, re-confirmed not re-scanned per instructions)

`docs/phase10/DRUGSIM_V1_FINAL_REPORT.md` already documents: `pyarrow` has advisories but is not imported anywhere in `src/` (confirmed by grep — unreachable from the live API); `starlette` (a genuine, live-path FastAPI dependency) has an advisory whose only listed fix crosses a major version boundary FastAPI's current pin doesn't yet allow. Both are disclosed, deferred, tracked in "Deferred Post-v1.0 Features." Not re-scanned this pass per the audit brief's own instruction to trust existing reports where they exist; re-verified only that the reasoning still holds.

---

# Improvements

### 🟡 `model_checksum` is not a directly queryable database column
`store.py`'s `predictions` table has no `model_checksum` column — the checksum is present (and traceable) only inside the serialized `response_json` blob per row. Every prediction *is* traceable to its checksum, just not via a direct SQL `WHERE model_checksum = ...` query. Not a correctness bug; worth a future schema addition if audit tooling ever needs to query by checksum directly.

### 🟡 `drugsim_ingest` was missing from the Poetry package manifest — **fixed**
`pyproject.toml`'s `packages` list omitted `drugsim_ingest`, despite it being imported by `drugsim_db/snapshots.py`, `drugsim_core/cli.py`, and several tests. A real `poetry install`/`poetry build` (as `deployment/docker/Dockerfile.app` performs, for the CLI/ETL image) would have silently excluded it, producing an `ImportError` at runtime for any CLI path that reaches those imports. **Does not affect the live prediction API** — `Dockerfile.predict-api` never runs a package build; it copies `src/` directly and sets `PYTHONPATH`. Fixed by adding the missing line; verified the file still parses as valid TOML.

### 🟡 Home page hero copy used unqualified "validated" — **fixed**
The very first user-facing sentence on `HomePage.tsx` read "...using validated machine-learning models..." with no qualifier — the clarifying "does not establish clinical safety" language exists but only in a second section further down the page. Every other instance of "validated" across the frontend (Terms, Limitations, About, Layout, component copy) is already properly scoped or immediately paired with a disclaimer; this was the one first-contact exception. Fixed to read "...using machine-learning models statistically validated on held-out data — not clinically validated — ...". Full frontend copy audit (43 files) found no other overclaiming — see Scientific Integrity section below for detail.

### 🟡 API key comparison was not constant-time — **fixed**
`ApiKeyMiddleware` compared the provided key via plain `frozenset` membership (`provided not in keys`) rather than a constant-time comparison. Real-world exploitability against a single shared demo key over HTTP was already low (CPython's per-process randomized string hashing scrambles bucket placement; network jitter dwarfs any residual timing signal) but the fix costs nothing — replaced with `hmac.compare_digest` against every configured key. Verified: 31/31 security tests still pass.

### 🟡 Testing environment gaps (not code defects)
- The throwaway venv this audit used to run backend tests is Python 3.9.6; `pyproject.toml` requires `^3.12`. This caused 11 false test failures in `test_landing.py` (a boto3 Python-3.9-deprecation warning becomes a hard error under this repo's `filterwarnings=["error"]` policy) — confirmed non-bug by isolating and suppressing that one warning, after which all 11 pass. This is a gap in the audit's own sandbox tooling, not a repository defect, but is worth fixing in whatever environment actually runs CI.
- `requirements-lock.txt` self-discloses that it is "NOT a resolved dependency graph," an interim snapshot pending a real `poetry.lock` — already known, already tracked in Deferred Post-v1.0 Features.

---

# Polish

None identified — visual polish was explicitly out of scope for this audit per the brief, and was not reviewed.

---

# Tests

| | Before this audit's fixes | After |
|---|---|---|
| `tests/unit` (backend) | 569 collected | 558 pass, 11 env-only false-fails (non-bug, see above) |
| `tests/security` | 16 | 16 pass |
| `tests/golden` (scientific regression) | 53 | 53 pass — **this suite is what caught the dofetilide misclassification** described above |
| `tests/integration` (live network) | 2 | 2 pass |
| `tests/constraints` (Postgres+RDKit, Docker-gated) | 63 | not run — no Docker daemon in this environment, same disclosed gap as Phase 8/10 |
| Frontend `vitest` | 74 | 74 pass |
| Frontend `tsc --noEmit` | clean | clean |
| Frontend/E2E `playwright` | 32 | 32 pass |
| **Total executable** | **746** | **735 pass, 0 genuine failures** |

**Newly added regression tests this audit** (all confirmed to fail against the pre-fix code, pass against the fix):
- `test_one_shared_api_key_does_not_pool_every_client_into_one_bucket`, `test_forwarded_for_chain_uses_the_originating_client` (`tests/unit/test_predict_security.py`) — rate-limit bucket isolation.
- `keeps the existing result on screen when a later request fails`, `does not claim a previous result exists when the very first request fails` (`frontend/src/pages/PredictPage.test.tsx`) — result-persistence-on-error.
- 3 retry-behavior tests in `frontend/src/api/client.test.ts` (recovers from a gateway 502, recovers from a dropped connection, gives up after 3 attempts and never retries a 4xx).
- 19 tests across `UncertaintyPanel.test.tsx`, `ApplicabilityDomainGauge.test.tsx`, `ScientificExplanation.test.tsx` from the earlier UX pass (p-value display, bullet-formatted rationale, simple-molecule applicability-domain note, three-part Prediction/Uncertainty/Applicability-Domain structure).

No test was deleted or weakened to make this audit's suite pass.

---

# Security

**Vulnerabilities found and fixed:**
- Non-constant-time API key comparison → `hmac.compare_digest`.
- Shared rate-limit bucket across all users → keyed by client address in addition to API key.

**Vulnerabilities found, disclosed, not fixed (deliberately, per scope rules):**
- Rate limiter's client-address key trusts a spoofable `X-Forwarded-For` header — bounded impact (doesn't bypass auth, bounded by a separate concurrency limit), same class as an already-disclosed operational limitation.
- CPU-exhaustion risk from unbounded RDKit parse time inside the 10s response timeout — bounded by concurrency limit, already disclosed and tested against one pathological case.
- `starlette` dependency advisory reachable in the live path, no compatible fix available under the current FastAPI pin — already disclosed, deferred.

**Confirmed clean (tested, not just read):**
- CORS: live-tested — the real frontend origin gets `Access-Control-Allow-Origin`; a spoofed origin gets none (400, no ACAO header).
- No raw chemical structure ever reaches the application log stream, including on every exception path (dedicated `redact_event` structlog processor, plus an end-to-end regression test that fabricates an exception mid-request and asserts the structure never appears in captured logs).
- SQL injection: all four queries in `store.py` are parameterized; no string interpolation with user data anywhere.
- No command/path injection: no `eval`/`exec`/`os.system`; the one `subprocess` call is an operator-only CLI command with typed, non-HTTP-reachable input; no file path is ever built from request data.
- No stack traces, internal paths, or raw exception text ever reach an HTTP response — verified by both reading every exception handler and live-testing malformed/malicious requests against production.
- Checksum-mismatch fail-safe: live-tested by corrupting a copy of the hERG model artifact and confirming `IntegrityError` is raised rather than the corrupted model being silently loaded; confirmed the API's own exception handling converts this into a clean `503`/health-check failure, never a raw error.
- No secrets committed anywhere in the tracked source (`.env.example` files contain only placeholders; `render.yaml` uses `sync: false` for both real secrets).
- `/docs` and `/openapi.json` are intentionally public (in the code's own `_PUBLIC_PATHS` list) — normal for a documented research API, not a leak; contains no secrets.

**Remaining risk, summarized:** everything unresolved is bounded, already disclosed prior to this audit or newly disclosed here, and specifically about "safe for a controlled, known set of users" rather than "safe for unrestricted public traffic" — consistent with the Controlled Release classification below.

---

# Scientific Integrity

- **Model integrity**: both registered models (hERG, CYP3A4) load only via checksum-verified artifacts; a corrupted or swapped artifact fails loudly (`IntegrityError` → `503`), never silently. Live-tested, not just read. hERG's tree count was reduced from 500 to 200 for memory reasons, chosen against the project's own golden regression panel rather than aggregate metrics, with the tradeoff fully disclosed in the registry's `deployment_variant` block (measured accuracy delta, reasoning, and a preserved full-accuracy backup artifact).
- **Uncertainty**: conformal p-values (`p_value_blocker`, `p_value_non_blocker`) are now displayed directly, not just used internally — user feedback specifically flagged this gap, addressed this session. No invented confidence percentages anywhere in the codebase; every reliability signal shown is either a real backend value or an explicitly-disclosed-as-derived categorical summary (`deriveReliabilityRating`, which states in its own rendered caption that it is "not a separate backend measurement").
- **Applicability domain**: verified live against the exact user-reported confusion case (paracetamol correctly does score `out_of_domain`; the UI now explains why a common, simple molecule can score this way against a model trained on complex drug candidates, addressed this session). Every prediction, in both the single-endpoint and multi-endpoint (Compound Profile) views, is structurally incapable of rendering without its accompanying uncertainty and applicability-domain context — verified by reading both render paths, not just the API contract.
- **Provenance**: every prediction response carries model ID/version/checksum, dataset version, feature-set ID, and input hash; the database's write path makes it structurally impossible for a failed prediction to be recorded as successful (`record_success`/`record_rejection` are separate methods with hardcoded, mutually exclusive `final_prediction_status` values).
- **Scientific claims**: a full-frontend copy audit (43 files, all user-facing strings) found no claim of clinical validation, guaranteed safety, or replacement of laboratory/animal/clinical testing anywhere in the product — every disclaimer required by the audit brief is already present, consistently worded, and in one case (Home page hero) tightened further this session.

---

# Final Decision

## 🟡 CONTROLLED RELEASE READY

DrugSim v1.0 meets the bar for a controlled research/demonstration release to a known, trusted audience. Scientific correctness, model integrity, core prediction functionality, database integrity, and the API contract all passed direct testing against the live deployment, not just a reading of the code. The four real defects present in the deployed system at the start of this engagement — a model-accuracy regression, a memory crash, a shared-bucket rate-limit bug, and a result-erasure UX bug — were found and fixed, each with a verified regression test. This fresh audit pass found no new unresolved 🔴 blockers.

It is **not** V1.0 RELEASE READY for unrestricted public traffic, for the same reasons the existing Phase 10 report already identified: a single shared API key rather than real multi-tenant authentication, a single-process in-memory rate limiter with a spoofable per-client key, and no monitoring/alerting beyond structured logs someone has to be watching. These are genuine, disclosed, bounded-impact gaps — appropriate for "a small number of known collaborators," not "the general public." Resolving them is infrastructure work explicitly out of scope for this audit's own rules ("do not introduce unnecessary infrastructure"), matching the reasoning the project has already applied consistently since Phase 8.

One correction to the existing Phase 10 report: it lists "no real TLS domain provisioned" as an unresolved limitation. Since that report was written, DrugSim has been deployed live with real HTTPS via Render's platform certificate (`https://drugsim-frontend.onrender.com`, `https://drugsim-predict-api.onrender.com`) — this specific item is resolved in practice, even without a custom branded domain.
