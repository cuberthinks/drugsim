# DrugSim v1.0 — Final Release Report

Phase 10 final report. Every claim below was re-verified live during this phase (test runs, checksum verifications, live server smoke tests, a real disaster-recovery cycle) — this is not a summary compiled from memory of earlier phases.

---

## Executive Summary

DrugSim v1.0 is a computational ADMET research and prioritisation platform. Given a molecular structure, it returns validated predictions for two independently evaluated endpoints — hERG cardiac-channel inhibition and CYP3A4 metabolic inhibition — each shown with its uncertainty, applicability domain, and full model provenance. Phase 10 integrated the two-endpoint system built across Phases 1–9 into one coherent product: audited every endpoint against the same standard, fixed several real gaps the audit found (below), built the DrugSim Compound Profile, ran a live disaster-recovery cycle, and re-verified the full test suite (720 automated tests across backend, frontend, and end-to-end layers, all passing).

**No new ADMET endpoints were created, no validated model was retrained, and no architecture was redesigned in this phase** — consistent with Phase 10's own execution rules. Every fix below is a correction to something already built: a documentation inaccuracy, a deploy-gate that silently didn't cover the second endpoint, stale product copy, or a genuinely missing (but small, additive) piece of provenance.

---

## Scientific Status

Both endpoints are `VALIDATED FOR INTERNAL RESEARCH`, held to the same bar:

| | hERG inhibition | CYP3A4 inhibition |
|---|---|---|
| Scaffold-split test ROC-AUC | 0.7875 | 0.7995 (95% CI 0.759–0.838) |
| Balanced accuracy | 0.6495 | 0.6520 |
| Conformal empirical coverage (target 90%) | 89.88% | 89.76% |
| Applicability domain | Monotonic degradation confirmed | Monotonic degradation confirmed |
| External validation | Not performed (disclosed gap) | Performed — 12,152 disjoint compounds |

Full detail, re-verified against the live model registry (fresh checksum verification, not cached claims): [`final-scientific-audit.md`](final-scientific-audit.md).

CYP3A4's weakest metric (specificity 0.4052 — a real, asymmetric tendency to over-call "inhibitor") is carried forward as a disclosed limitation, not hidden or explained away. Neither endpoint was downgraded or removed; neither needed to be.

---

## Technical Status

- **Architecture**: unchanged from Phase 8/9 — FastAPI prediction service, static frontend behind Caddy, PostgreSQL+RDKit for the broader platform, SQLite for the prediction audit trail. No redesign performed or required.
- **Test suite**: 636 backend tests (unit + security + golden regression), 53 frontend unit tests, 31 Playwright end-to-end tests (including a new dedicated release-gate suite and expanded accessibility coverage) — **720 total, all passing**, re-run in full during this phase.
- **Database migrations**: Alembic chain re-verified this phase (`alembic history` resolves to a single linear head, `0013`, no gaps or branches — base through 13 migrations). As in Phase 8, not executed against a live Postgres in this sandbox (no Docker daemon available here); the existing `tests/constraints` suite does this for real in CI whenever Docker is available. This is an inherited, still-true, disclosed limitation, not newly discovered or newly deferred.
- **Deployment reproducibility**: Docker build definitions unchanged and previously reviewed (Phase 8). `requirements-lock.txt` remains an interim, hand-maintained dependency snapshot, not a committed `poetry.lock` — a known, disclosed gap carried forward, not resolved this phase (resolving it safely would mean testing a full dependency re-resolution, out of Phase 10's "do not redesign" scope).
- **Real gaps found and fixed this phase**:
  - `scripts/verify_model_integrity.py` previously checked only the implicit default (hERG) model via a no-argument call — a CI/CD run of this gate never actually verified the CYP3A4 artifact. Now enumerates and checksum-verifies every registered endpoint; verified live (both pass).
  - `scripts/smoke_test_deployment.py` previously only ever exercised hERG through `/predict`. A deployment with a completely broken CYP3A4 endpoint would still print "All smoke tests passed." Now walks `GET /endpoints` and runs a real prediction against every servable endpoint; verified live against a running uvicorn + vite-preview instance (8/8 checks pass, including the new one).
  - `GET /endpoints`'s docstring incorrectly claimed the route was unauthenticated like `/health`. Live testing showed it was already correctly gated like `/model` — the code was right, the comment was wrong. Fixed the comment.
  - A prediction's uncertainty and applicability-domain methodology previously required a separate registry lookup by `model_id` to name by string (Phase 7's own stated principle: "a prediction must be reproducible from its own recorded metadata, without needing separate access to the model registry file" was not fully met). Added a `method` field to both `reliability.conformal` and `reliability.applicability_domain` in the API response — additive, backward-compatible, verified live and by 16 updated/new tests.

---

## Security Status

- **Dependency audit** (`pip-audit`, `npm audit`): frontend production dependencies clean (0 vulnerabilities). Backend: of everything flagged, only `pyarrow` is a genuine direct runtime dependency with known advisories — and it is not imported anywhere in `src/` (confirmed by grep), meaning it is unreachable from the live, internet-facing prediction API; it is only used by the offline ETL pipeline run by trusted maintainers. `starlette` (FastAPI's core transitive dependency, genuinely in the live request path) has advisories whose only listed fixes cross a major version boundary (0.x → 1.x) that FastAPI's own pin (`<1.0.0`) does not yet allow — bumping it safely requires a coordinated FastAPI upgrade and its own regression cycle, which is out of this phase's "do not redesign" scope. Documented as a deferred, disclosed item, not silently ignored. Everything else flagged (`torch`, `transformers`, `poetry`, `dulwich`, etc.) is confirmed, by cross-referencing `requirements-lock.txt`, to not be a real project dependency at all — noise accumulated in this long-lived shared development environment, not part of what ships.
- **Secrets**: grepped for hardcoded API keys/passwords/tokens across `src/`, `frontend/src/`, `scripts/`, `deployment/` — none found. Only `.env.example` files (templates, no real values) are tracked.
- **Malicious/pathological input**: live-tested an oversized structure (422), an HTML/script-injection-shaped SMILES (422, correctly rejected as invalid chemistry), a SQL-injection-shaped payload (422, and inherently safe regardless — the store uses parameterised queries throughout), a pathological long-chain SMILES (rejected in 232ms via the molecular-weight ceiling, no catastrophic-backtracking hang observed), and an oversized JSON body (413). All handled cleanly.
- **Frontend**: no `dangerouslySetInnerHTML`, no `eval`, no unsafe SVG injection in the molecule-drawing code path.
- **Error responses**: live-verified no stack traces, internal paths, or database detail leak through any error path (404, 422, 500, 503 all checked).
- **Access controls**: API-key gating, rate limiting (429 + `Retry-After`), body-size limiting (413), and concurrency limiting (503 at capacity, verified with a genuine 40-concurrent-request burst on a single event loop — exactly 10 succeeded, the other 30 got a clean 503, matching the configured `max_concurrent_requests=10`) all re-verified live this phase, in addition to the 636 passing automated tests covering the same controls.

No critical or high-severity issue was found in the live-reachable system this phase. The two disclosed dependency findings (pyarrow, starlette) are documented above rather than fixed under time pressure with an untested major-version bump.

---

## Product Status

- **Primary user journey** (enter → validate → predict → see prediction + uncertainty + AD + reliability + model version + limitations link) verified end-to-end via a new dedicated Playwright release-gate suite (8 tests, including invalid molecule, unsupported input, API failure, timeout, out-of-domain molecule, experimental endpoint, and unavailable endpoint — all passing).
- **Errors are understandable**: every error state renders honest, plain-language copy (`ErrorPanel`), never a fabricated result — verified across all seven failure modes above.
- **Accessibility**: 11 axe-core WCAG 2.1 AA scans, zero violations, across every static page, the populated results view, the error state, the endpoint selector (including its disabled experimental option), and the new DrugSim Compound Profile view. Matches the Phase 7 standard.
- **DrugSim Compound Profile** (new this phase): one molecule, every validated endpoint grouped by category (Toxicity, Metabolism — only categories with an actual approved endpoint appear), each with its own independent prediction, uncertainty, and reliability card. No combined "DrugSim score" exists anywhere in the product; verified by a dedicated component test asserting no such heading or claim renders.
- **Scientific claims accuracy**: found and fixed three real, stale product-positioning claims left over from before CYP3A4 existed — `TermsPage.tsx` and `AboutPage.tsx` both still said DrugSim covered "a single validated endpoint — hERG... only," which became false in Phase 9 and was never updated until this phase. Also made the "does not replace animal testing" positioning explicit (previously only implied via "in vivo assays"), per Phase 10's own named positioning guardrail.
- **Legal/disclaimer pages**: Privacy, Terms, Limitations, and About are all reachable from global navigation on every page, e2e-tested.

---

## Cross-Endpoint Consistency

Both endpoints share the same standardisation pipeline (`drugsim_chem`), the same input-validation rules (`PredictSettings`'s global `max_smiles_length`/`max_molecular_weight`), the same provenance schema, the same API request/response contract, and the same reliability/applicability-domain presentation and methodology (`drugsim_predict.conformal`/`applicability_domain`, unmodified shared implementations, not per-endpoint duplicates). The one necessary difference — each endpoint's own label vocabulary (`blocker`/`non_blocker` vs. `inhibitor`/`non_inhibitor`) — is handled generically via a `positive_class_label`/`negative_class_label` pair on the model bundle, not a hardcoded special case, and is documented in the registry.

---

## Endpoint Summary

### hERG inhibition
- Model version: `0.1.0` | Dataset size: 9,589 compounds | Training-set size: 6,792
- Validation: ROC-AUC 0.7875, balanced accuracy 0.6495 (scaffold-split test, n=800)
- Applicability domain: 2-signal in-domain 75.4% → borderline 66.9% → out-of-domain 58.2% accuracy (monotonic)
- Uncertainty: split conformal, 89.88% empirical coverage at 90% nominal target
- Limitations: no external validation performed (disclosed since Phase 3); 10 µM threshold is a literature convention
- Release status: **VALIDATED FOR INTERNAL RESEARCH**

### CYP3A4 inhibition
- Model version: `0.1.0` | Dataset size: 5,344 compounds | Training-set size: 3,767
- Validation: ROC-AUC 0.7995 (95% CI 0.759–0.838), balanced accuracy 0.6520 (scaffold-split test, n=459)
- Applicability domain: 2-signal in-domain 82.8% → borderline 69.9% → out-of-domain 52.9% accuracy (monotonic)
- Uncertainty: split conformal, 89.76% empirical coverage at 90% nominal target
- External validation: 12,152 genuinely disjoint TDC compounds, ROC-AUC 0.7758 — consistent with internal test
- Limitations: specificity 0.4052 is a real, disclosed weakness; 10 µM threshold is a literature convention; external validation uses a differently-labelled dataset
- Release status: **VALIDATED FOR INTERNAL RESEARCH**

No endpoint in this release carries `EXPERIMENTAL` or `REJECTED` status. The mechanism that would refuse to serve one (the promotion gate in `drugsim_predict.pipeline.run_inference`, raising `EndpointNotAvailableError`/403 for any non-`VALIDATED` status) is implemented and covered by automated tests, verified again this phase.

---

## Known Limitations

- CYP3A4's specificity (0.4052) is a real, asymmetric over-calling of "inhibitor" — the weakest metric of any endpoint in the system.
- hERG has no external validation (a pre-existing, disclosed gap since Phase 3/4 — TDC's endpoint was unreachable from the original training environment).
- Both endpoints' 10 µM thresholds are literature screening conventions, not fixed biological or regulatory boundaries.
- DrugSim covers exactly two narrow endpoints. It says nothing about any other ADMET property, drug-likeness, target engagement, efficacy, or clinical outcome, and its two endpoints are never combined into a single score or an implied whole-organism picture.
- Operational: no per-user data isolation (shared API key, not multi-tenant identity); in-memory, non-distributed rate limiting; no real TLS domain provisioned in this environment; no committed dependency lockfile (interim snapshot only); database migrations verified structurally but not executed against a live Postgres in this sandbox (no Docker daemon available here, same as Phase 8).
- Security: two dependency-vulnerability findings (pyarrow, starlette) documented above as deferred, with reasoning for why neither was force-fixed this phase.

---

## Deferred Post-v1.0 Features

Explicitly out of scope for this release, listed so they are not silently forgotten:

- A third ADMET endpoint, using the same one-at-a-time, fully-audited process Phase 9 and this phase both followed — not started, per the explicit "do not create new ADMET endpoints" rule for Phase 10.
- A coordinated `starlette`/`fastapi` major-version upgrade to close the one deferred dependency-security finding.
- A real `poetry.lock` (or equivalent) replacing the interim `requirements-lock.txt` snapshot.
- A live, Docker-available execution of the Postgres+RDKit Alembic migration chain (structurally verified twice now — Phase 8 and this phase — never executed end-to-end in this sandbox).
- A distributed (multi-worker-safe) rate limiter, if this deployment is ever scaled beyond a single process.
- Real TLS/domain provisioning and a non-placeholder operator contact address, both explicitly deployment-time tasks already documented as manual setup steps.
- Full mkdocs navigation coverage for Phases 2–8's existing reports (only Phase 1 and a new "DrugSim v1.0 Release" section are wired into `mkdocs.yml`'s nav; the phase directories exist and are linked from `docs/README.md`, but are not all individually in the mkdocs sidebar — a pre-existing gap that predates this phase, not fixed here to avoid unrelated scope creep).

---

## Final Release Decision

### **DRUGSIM v1.0 — CONTROLLED RELEASE**

**Justification**: Every scientific, technical, security, operational, and product criterion in Phase 10 Sec 17 is met for a controlled research/demonstration audience — 720 automated tests passing, zero WCAG violations, a live-verified disaster-recovery cycle, live-verified security controls under real malicious and pathological input, and two independently validated endpoints held to the same evidentiary standard with their real limitations disclosed rather than hidden.

This is **not** designated PUBLIC RESEARCH RELEASE, because several of this system's own already-disclosed limitations are specifically inappropriate for broad public access without a human operator in the loop: a shared API key rather than real multi-tenant authentication, in-memory (single-process) rate limiting with no protection against a moderately sophisticated distributed abuser, no real TLS domain provisioned, and no monitoring/alerting beyond structured logs that someone has to be watching. These are Phase 8 findings, unresolved because resolving them is infrastructure work explicitly out of scope for a phase whose own rules say "do not introduce unnecessary infrastructure" — they were correct decisions for their phase, but they are exactly the gap between "safe for a known, controlled set of users" and "safe for the general public."

No `clinically validated`, `medically approved`, `regulatory approved`, `diagnostic`, `therapeutic`, or `clinically safe` claim is made anywhere in this product, this release, or this report.
