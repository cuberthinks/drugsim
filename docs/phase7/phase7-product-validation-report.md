# Phase 7 — Product Hardening & Real-World Validation

## Readiness classification: **INTERNAL DEMONSTRATION READY**

Not clinically validated, not production medical software, and not yet
ready for unsupervised external exposure (see "Production readiness" §11
for the specific blockers). Safe for controlled internal demonstrations and
internal research use by people who have read [Limitations](../../frontend/src/pages/LimitationsPage.tsx).

No new prediction models were created. The validated `herg_inhibition`
v0.1.0 model's methodology is unchanged — every fix in this phase is
infrastructure, testing, security, performance, or UI-copy work.

---

## 1. Full-system audit

A full pipeline trace (User → Frontend → API → validation → standardisation
→ features → model → uncertainty → AD → response → UI) was run as a
dedicated read-only audit. Confirmed solid, with citations:

- **Model/feature version consistency**: `feature_set_id` is recomputed
  from the live toolchain on every request and hard-fails
  (`ReproducibilityError`) on any mismatch against the registry's frozen
  value (`pipeline.py`) — this is a real, load-bearing guard, not
  decorative.
- **Model integrity**: `model.joblib`, `inference_support.npz`, and
  `descriptor_ad_scaler.joblib` were already SHA-256 verified before load.
- **Standardisation determinism**: no unordered-collection or unseeded-
  randomness issues found; idempotency is already tested.
- **Provenance sourcing**: all provenance fields are read from the live
  model bundle / inference result at request time, never hardcoded.
- **UI fidelity**: the frontend renders backend fields verbatim; the one
  derived value (Reliability High/Moderate/Low) is explicitly disclosed as
  a frontend summary, never presented as a backend measurement.

Two real gaps were found and fixed (see §4, §8):
1. `inference_support_manifest.json` (carries the k-NN/conformal
   thresholds) was loaded without a checksum — the one unverified artifact
   in the bundle. **Fixed**: added `manifest_sha256` to the registry and a
   verification call in `model_registry.py`, plus a tampering regression
   test.
2. `predicted_probability_blocker` was displayed at 2 decimal places in the
   UI versus the backend's 4-decimal rounding, which could obscure a value
   sitting near the 0.50 decision boundary. **Fixed**: bumped to 3 decimals.

A stale, unreferenced artifact (`models/admet/herg_inhibition/artifact/scaler.joblib`,
distinct from `descriptor_ad_scaler.joblib`) was found and left in place —
documented, not deleted, since deleting model artifacts is out of scope for
a hardening phase and it is confirmed dead (never read at inference).

## 2. End-to-end test coverage

Extended beyond Phase 6 to explicitly cover every scenario in the Phase 7
brief. All of the following are automated and passing:

| Scenario | Backend | Frontend (unit) | Frontend (E2E) |
|---|---|---|---|
| Valid molecule | ✓ | ✓ | ✓ |
| Invalid molecule | ✓ | ✓ | — (covered at unit level) |
| Malformed input | ✓ (schema-level 422) | ✓ | — |
| Out-of-domain molecule | ✓ (new) | ✓ (new) | ✓ (new) |
| API failure / server error | ✓ (new, was previously unhandled — see §4) | ✓ | ✓ |
| Timeout | n/a server-side (see §8 note on `request_timeout_seconds`) | ✓ (new, fake-timer test of the 15s client abort) | — |
| Missing prediction (404) | ✓ | ✓ (new, client-level) | — (no page currently calls `getPrediction`; see Phase 6 known limitation, still open) |
| Unexpected server error | ✓ (new) | ✓ (new) | — |

No failed request path produces a fabricated or stale prediction anywhere
in this matrix — verified explicitly in both the backend (`TestPredictUnexpectedServerError`)
and frontend (`PredictPage` error-state tests assert the prediction result
never renders alongside an error).

## 3. Scientific regression suite

`tests/golden/test_herg_model_regression.py` — 40 tests, new. A fixed panel
of 7 real molecules, empirically run against the live registered model and
their observed behaviour pinned as the expectation (not invented):

| Molecule | Categories covered | Observed label | AD verdict | Singleton |
|---|---|---|---|---|
| Terfenadine | strong inhibition, **in-domain** | blocker (p=0.878) | in_domain | yes |
| Astemizole | strong inhibition, out-of-domain | blocker (p=0.892) | out_of_domain | yes |
| Aspirin | weak inhibition | non_blocker (p=0.281) | out_of_domain | yes |
| Glycine | weak inhibition, minimal molecule | non_blocker (p=0.209) | out_of_domain | yes |
| Dofetilide | **borderline** (right at the 0.5 boundary) | blocker (p=0.518) | out_of_domain | no |
| Caffeine | borderline, common compound | non_blocker (p=0.342) | out_of_domain | no |
| Ivermectin | **chemically unusual** macrocycle, borderline | blocker (p=0.634) | out_of_domain | no |

Assertions per molecule use wide (±0.15) probability bands, not exact
floats — designed to catch a label flip or a large shift, not ordinary
retraining noise. Separately, `TestBundleIdentity` pins `model_id`,
`model_version`, `feature_set_id`, `dataset_version`, and
`nominal_confidence` globally, which is the cheapest, highest-signal check
in the suite: it fires on model replacement or any toolchain drift before
any single molecule's prediction even changes.

## 4. Security audit

Reviewed: structure leakage in logs/errors, unsafe file handling,
malicious input, API abuse, injection, exposed secrets, CORS, dependency
vulnerabilities, error-message leakage.

**Findings, fixed:**

1. **(High) The structlog redaction pipeline was never wired into the running service.** A full redaction system (`SensitiveStructure`, `redact_event`, key/pattern scrubbing, its own dedicated CI test file) already existed from an earlier phase, but `drugsim_predict.api` never called `configure_logging()` — the service ran under structlog's unconfigured default, so the redaction processor built specifically for this purpose was never actually in the active chain. **Fixed**: wired `configure_logging()` into `api.py`. Added a subprocess-based regression test (`test_importing_the_api_module_configures_structlog`) proving a fresh process import actually configures it.
2. **(High) Unhandled exceptions bypassed both the audit-log invariant and the redaction pipeline.** `/predict` only caught `StructureError`/`ReproducibilityError`; any other exception (an `IntegrityError` mid-request, a bug in feature computation) would propagate to Starlette's default handler — skipping `store.record_rejection` (breaking the module's own stated "every prediction must be logged" invariant) and printing a raw, unredacted traceback to stderr. Since RDKit's own exception messages sometimes embed the raw structure text, this was a real (if narrow) structure-leakage path. **Fixed**: added a catch-all `except Exception` in `/predict` (logs only `type(exc).__name__`, never `str(exc)`, and still records the rejection) plus a global `@app.exception_handler(Exception)` for every other route. Verified live: a simulated `KeyError` embedding a real SMILES string produced a clean JSON log with only `error_type: "KeyError"` and a proper audit-trail row — the structure never appeared in the log or the traceback.
3. **(Medium) `inference_support_manifest.json` was unverified** — see §1, fixed.
4. **(Low) Schema `max_length` (100,000) was 20x more permissive than the actually-enforced business rule (5,000, `PredictSettings.max_smiles_length`)**, so the OpenAPI-documented limit didn't reflect reality. Not a DoS issue in practice (the pipeline's cheap length check runs before any expensive parsing either way), but a documentation-accuracy fix. **Fixed**: tightened to 6,000.

**Findings, assessed and not fixed (documented):**

- **Dependency versions**: `starlette 0.49.3` (a `fastapi` transitive dependency) has five known CVEs fixed in 1.0.1–1.3.1 (host-header URL confusion, unbounded urlencoded-form parsing, Windows `StaticFiles` SSRF, `HTTPEndpoint` arbitrary-method dispatch). Reviewed each against this codebase: none are reachable — the service never calls `request.form()`, never mounts `StaticFiles`, never uses class-based `HTTPEndpoint` routes, and does no hostname-based authorization. Upgrading was not attempted live in this environment (no `poetry.lock`, no verified compatibility matrix — see §11); recorded as a dependency-hygiene item for the next dependency-update pass, not a live vulnerability.
- **No authentication or rate limiting** — by explicit, documented design ("internal-only service", `api.py` module docstring). This is a real blocker for external exposure specifically (§11), not a defect for internal use.
- **SQL injection**: none found — all queries in `store.py` are parameterised.
- **CORS**: reviewed and confirmed minimal (`allow_credentials=False`, explicit method/header allowlists, no wildcard origin).

## 5. Performance

Measured against the real running service, not estimated:

| Metric | Before | After | Method |
|---|---|---|---|
| Inference latency (in-process) | ~57 ms/call | ~25 ms/call | `time.perf_counter` around `run_inference`, 30-call average |
| End-to-end HTTP latency (median) | ~62 ms | ~34 ms | persistent-connection `http.client`, 30 requests |
| Memory (RSS after model load) | ~828 MB | ~828 MB (unchanged) | `ps -o rss=` |
| Frontend DOMContentLoaded | ~960 ms | ~28 ms | Playwright navigation timing, production build |

**Root cause, inference latency**: `cProfile` showed ~65% of total
inference time was spent in `time.sleep` inside joblib's parallel-backend
result-retrieval loop. The registered `RandomForestClassifier` was pickled
with `n_jobs=-1` — correct for training or batch scoring, actively harmful
for single-sample serving, where joblib's worker-pool coordination
overhead dwarfs the actual per-tree computation. **Fixed**: `model.n_jobs = 1`
set once at load time in `model_registry.py`. Verified `predict_proba`
output is bit-identical before/after (confirmed via direct comparison, and
pinned by a new regression test) — this changes execution strategy only,
never a prediction value.

**Root cause, frontend load time**: the Google Fonts stylesheet in
`index.html` was loaded the ordinary render-blocking way and measured (via
Playwright resource timing) at ~675ms of a ~960ms total load — by far the
largest contributor, dwarfing the app's own JS+CSS (under 15ms combined).
**Fixed**: standard non-blocking `media="print"` + `onload` swap pattern,
with a `<noscript>` fallback. The app already renders on system fonts
while (or if) the custom fonts load, so nothing is unreadable either way.

No further optimisation was attempted — per the Phase 7 brief, this is not
a "prematurely introduce complex infrastructure" situation. At ~25–35ms/prediction,
a single research user clicking "Predict" one molecule at a time is well
within comfortable interactive latency.

## 6. Accessibility & UX review

**Automated**: added `@axe-core/playwright` and ran a full WCAG 2.1 A/AA
scan across all four pages plus the populated results view, the expanded
"Model & evidence" panel, and an error state (6 scenarios). Found and fixed
one real, reproducible violation:

- **Color contrast**: the footer's persistent disclaimer text
  ("DrugSim internal research preview — not for clinical or regulatory use")
  and three separate scientific-caveat captions (reliability disclosure,
  conformal coverage-guarantee footnote, applicability-domain "not
  biological correctness" footnote) all used reduced-opacity text
  (`text-ink-soft/70` and `/80`) that measured 3.59:1 and 4.56:1 contrast
  against the page background — one clearly failing, one passing only by a
  hair. Notably, these were exactly the disclosure/limitation texts this
  product repeatedly insists must never be visually de-emphasised.
  **Fixed**: all four bumped to full-opacity `text-ink-soft` (7.62:1).
  Re-scanned: **zero violations** across all 6 scenarios after the fix.

**Heuristic comprehension walkthrough** (disclosed substitute for real user
testing — see §9): reading every page fresh from a "biomedical background,
limited computational-chemistry knowledge" persona, following the task
script (enter molecule → predict → explain the prediction → explain trust
→ explain applicability domain → identify limitations):

- Prediction meaning, uncertainty framing, and limitations: understood
  correctly from the existing copy — the plain-language sentence in
  `UncertaintyPanel` (singleton vs. non-singleton) is read first, with the
  more technical "population-level coverage guarantee" language
  appropriately secondary.
- **Applicability domain: found unclear, and fixed.** `ApplicabilityDomainGauge`
  defined a plain-language sentence per verdict (`copy.description`, e.g.
  "This structure closely resembles compounds the model was trained on.")
  but never rendered it — only the backend's own technically-precise
  rationale string (e.g. "descriptor-space distance to nearest training
  neighbours is 2.56 (training-internal threshold 1.74)") was shown as the
  primary explanation, which leans on vocabulary the target persona
  wouldn't have. **Fixed**: the plain-language sentence now leads; the
  backend's real rationale is still shown in full, unaltered, now labelled
  "Supporting detail from the model" rather than being the only
  explanation offered. Pinned with a new test.
- **Real gap found, not fixed (out of scope)**: a user who knows a
  compound by name or structure drawing, not by SMILES, has no path into
  the tool — `MoleculeInput` assumes a SMILES string is already in hand.
  Building a name→structure lookup is a new capability, not a hardening
  fix, and is recorded as a Phase 8 candidate rather than built here.

## 7. Scientific communication audit

Grepped every user-facing string in `frontend/src` and every warning/status
string returned by the backend against the explicit forbidden-claims list
(clinical validation, guaranteed safety, replacement of lab/animal testing,
certainty, universal applicability, "Safe"/"Unsafe" as absolute
conclusions). **Result: clean, no violations.** Every match against
guarantee/replace/safe-pattern searches was already correctly used in
negated/prohibition context (e.g. "not a clinical diagnosis or a guarantee
of safety", "Does not replace lab testing"). The backend's own
`small_training_set` warning explicitly states "...not clinically
validated" as a warning surfaced to the UI. No changes were needed.

## 8. Reproducibility

Checked whether a prediction's own recorded metadata is sufficient to
identify: model version, model checksum, dataset version, preprocessing
version, feature version, timestamp, input hash. **Two real gaps found and
fixed**:

- `model_checksum` did not appear anywhere in the API response (only used
  internally, transiently, during load-time verification).
- `input_hash`, `standardization_pipeline_version`, `descriptor_spec_version`,
  and `rdkit_version` were computed/loaded but never surfaced in the
  response, even though `feature_set_id` (their combined content-hash) was.

**Fixed**: `ProvenanceSchema` and `ModelDetailResponse` both gained
`model_checksum`, `standardization_pipeline_version`, `descriptor_spec_version`,
`rdkit_version`; `ProvenanceSchema` also gained `input_hash` (a one-way
digest of the submitted structure — safe to return, since a response is
only ever sent back to the same caller who already has the raw structure,
and the digest lets that caller correlate their result against
server-side audit logs without exposing anything new). Verified live
against the running service — all fields populate correctly with real
values. The "Model & evidence" panel now surfaces all of this, with a line
explaining what it's for.

**One gap noted, not fixed**: `PredictSettings.request_timeout_seconds`
(10.0s) is declared but never enforced anywhere in the codebase — a
single inference call has no server-side timeout cutoff. Not fixed, since
building timeout infrastructure for an operation that reliably completes
in ~25ms would be exactly the "prematurely introduce complex
infrastructure" the brief warns against; the frontend's own 15s client-side
abort (`client.ts`, tested) is the operative timeout in practice.

## 9. User testing

**No real external users were available in this environment.** Per the
disclosure agreed at the start of this phase, a heuristic multi-persona
walkthrough was run instead (§6) and is explicitly recorded here as **not
equivalent to real user testing** — no confusion-point data from an actual
naive user exists, and this factors directly into the readiness
classification (§10, §11): a product cannot be called "external
demonstration ready" on the strength of the product team's own read of its
own copy alone. Recommended for Phase 8 or before any real external
showing: a short session (5–10 minutes, 3–5 participants with biomedical
but not cheminformatics backgrounds) running the exact task script in §6.

## 10. Fixes completed, by priority

1. **Scientific misinformation**: none found (§7).
2. **Incorrect/imprecise displayed values**: probability display precision (§1), applicability-domain manifest checksum gap (§1, §4).
3. **Security vulnerabilities**: redaction pipeline wiring, unhandled-exception audit/leakage gap (§4).
4. **Broken prediction flow**: none found — the flow works correctly end to end, including every error path (§2).
5. **Misleading uncertainty/reliability display**: applicability-domain plain-language sentence was dead code (§6).
6. **Major accessibility problems**: color-contrast failures on the product's own limitation/disclosure text (§6).
7. **Major usability problems**: none beyond the AD-copy fix and the documented SMILES-only-input gap (§6).
8. **Performance issues**: inference latency (joblib overhead) and frontend load time (blocking font request) (§5).
9. **Visual polish**: none attempted — correctly out of scope per the brief's own priority ordering.

Test suite growth this phase: backend 539 → 584 tests (+45, all passing);
frontend unit 34 → 44 tests (+10, all passing); frontend E2E 2 → 9 tests
(+7: out-of-domain flow, 6 accessibility scans, all passing).

## 11. Production readiness checklist

| Item | Status | Notes |
|---|---|---|
| Build reproducibility | ⚠️ Partial | No `poetry.lock` ever existed despite `pyproject.toml` claiming reproducibility depends on it. Interim fix: `requirements-lock.txt`, a labeled snapshot of the verified working environment — not a resolved lockfile. A real `poetry lock` is a Phase 8 prerequisite for calling this fully reproducible. |
| Test suite | ✅ | 584 backend + 44 frontend unit + 9 E2E, all passing; includes a scientific regression suite and automated accessibility scans. |
| API stability | ✅ | Contract additions this phase (reproducibility fields) are additive/non-breaking. |
| Frontend stability | ✅ | Builds clean, lints clean, zero WCAG 2.1 AA violations. |
| Dependency locking | ⚠️ Partial | See "Build reproducibility". `npm audit`: 0 vulnerabilities. `pip-audit` on the actually-used dependency set: 0 exploitable findings (starlette CVEs assessed non-reachable, §4). |
| Environment configuration | ✅ | `DRUGSIM_CORS_ORIGINS`, `DRUGSIM_LOG_LEVEL`, `DRUGSIM_LOG_FORMAT`, `DRUGSIM_PREDICT_*` — documented, env-overridable, safe defaults. |
| Secrets management | ✅ | No secrets used or exposed by the prediction service; unrelated ETL config's placeholder credentials use `pydantic.SecretStr` correctly and are not reachable from this service. |
| Logging | ✅ (fixed this phase) | Structured JSON, redaction pipeline now actually wired into the running service (§4). |
| Monitoring | ❌ Not present | No metrics, tracing, or alerting beyond structured logs. Acceptable for internal demonstration; a real blocker before any unsupervised deployment. |
| Error handling | ✅ (fixed this phase) | Every route now has a safety net; no failed request produces a fabricated result anywhere in the matrix (§2, §4). |
| Backup requirements | ❌ Not present | `var/predictions.sqlite3` (the audit trail) has no backup/retention policy. Low severity — it's a record-keeping log, not required for serving predictions — but worth a policy decision before relying on it for compliance/audit purposes. |
| Documentation | ✅ | This report plus five prior phase reports; `docs/phase7/` and `requirements-lock.txt` added this phase. |
| Scientific disclaimer | ✅ | Present, accessible from every page footer, never buried, and now passes accessibility contrast checks (§6). |
| Privacy policy requirements | ❌ Not present | No user accounts, no PII collected — but submitted molecular structures may be proprietary/pre-patent (per the redaction module's own stated threat model), and there is no user-facing statement about how long submissions are retained. Needed before any external demonstration; not needed for internal use by people already covered by employment/NDA terms. |
| Terms of use requirements | ❌ Not present | Same reasoning as above. |
| Authentication / rate limiting | ❌ Not present (by design) | Documented as an explicit internal-only-service decision (`api.py` docstring). A real blocker for external exposure specifically — an unauthenticated, unthrottled endpoint is fine on a controlled internal network and is not fine reachable by the public internet. |

**Overall**: the core scientific and product experience is solid,
thoroughly tested, and now measurably more secure, faster, and more
accessible than at the start of this phase. What's missing is entirely
external-facing infrastructure (auth/rate-limiting, monitoring, backups,
privacy/terms copy, a real dependency lockfile) and real user validation —
none of which block controlled internal use, all of which block
unsupervised external exposure.

## 12. Remaining risks

- No real user testing has been conducted (§9) — the UX fixes in this
  phase are well-reasoned but unvalidated by an actual naive user.
- `starlette` is several major versions behind; currently assessed
  non-exploitable given how this app is built, but that assessment should
  be re-checked at every future dependency bump, not assumed permanent.
- No `poetry.lock` — a future `pip install` in a fresh environment is not
  guaranteed to reproduce today's exact dependency graph.
- No monitoring/alerting — an outage or silent model-load failure in a
  deployed instance would only be visible via logs, not proactively
  surfaced.
- The applicability-domain and reliability concepts, while now better
  explained, remain genuinely novel UI patterns that only real user testing
  (not a heuristic walkthrough) can validate are understood correctly by
  the target audience under real conditions.
- SMILES-only input is a real onboarding barrier for the "biomedical, not
  cheminformatics" persona this product targets; not fixed, recorded as a
  Phase 8 candidate.

## Readiness classification, restated

**INTERNAL DEMONSTRATION READY.**

Suitable for controlled research use and internal demonstrations by people
who have read the limitations page. Not yet **LIMITED EXTERNAL
DEMONSTRATION READY** — the blockers are specifically the items marked ❌
above (auth/rate-limiting, monitoring, privacy/terms copy, backups) plus
the absence of real user testing (§9), not any scientific or core-product
deficiency. Not clinically validated, not production medical software, and
this report does not represent it as either.

Phase 7 is complete. Do not start Phase 8.
