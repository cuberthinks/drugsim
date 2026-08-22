# DrugSim Confidentiality Audit — 2026-08-22

Read-only audit of how DrugSim handles confidential/unpublished molecular
structures, conducted before any code changed. Findings are classified:

- 🔴 Security problem
- 🟠 Important privacy issue
- 🟡 Improvement
- 🟢 Strength / no action needed

Every finding below cites the exact file and line it was verified against.
Where a finding was later fixed, the corresponding change is named — see
`docs/privacy/confidentiality-implementation.md` for the full account of
what shipped.

---

## 🔴 Security problems

### 1. `GET /predict/{id}` had no ownership check

**Before this audit**, any caller holding any one configured API key could
retrieve **any** stored prediction by ID — including its canonical chemical
structure — regardless of who created it.

- Endpoint: `src/drugsim_predict/api.py:591-598` (line numbers as they
  stood before the fix).
- `PredictionStore.get()` (`src/drugsim_predict/store.py:171-182`) performs
  a plain `SELECT * FROM predictions WHERE id = ?` with no owner/tenant
  filter.
- `ApiKeyMiddleware` (`src/drugsim_predict/security.py`) validates that a
  request carries *some* configured key, but never recorded *which* key,
  so no downstream code could scope a query to "the caller who made this
  request."
- Mitigating factor: prediction IDs are `prd_<26-char ULID>`
  (`src/drugsim_core/ids.py`), 80 bits of `os.urandom` entropy — not
  practically guessable by brute force. This is **not** the "sequential or
  guessable ID" scenario the brief specifically asked about; it is the
  narrower but still real gap of **no defense-in-depth if an ID is ever
  exposed through any other channel** (a shared JSON/CSV export, a
  screenshot, a support ticket, a copied URL — the ID appears in the
  `PredictionResponse.id` field returned to every caller, including the
  frontend's own downloads via `predictionToJSON`/`predictionToCSV`).
- Compounding factor: the live production deployment configures a
  **single** shared API key, embedded in the public frontend JS bundle. In
  that specific deployment, this gap meant any visitor to the public site
  who obtained another visitor's prediction ID by any means could fetch
  that structure back, because everyone shares the one key already.

**Fixed** — see implementation doc, item 1.

---

## 🟠 Important privacy issues

### 2. Backups are unredacted, unencrypted, local-disk-only copies

- `scripts/backup_predictions_db.py:68` uses SQLite's online backup API to
  copy the `predictions` table verbatim, including the full
  `response_json` column (which holds the canonical structure — see
  finding 4 below). No redaction, no encryption.
- Written to `var/backups/` on local disk by default
  (`backup_predictions_db.py:99`). The script's own docstring
  (`backup_predictions_db.py:14-19`) states off-host/cloud upload is left
  entirely to deployment-time operational wiring — nothing in the repo
  implements it.
- **Not fixed in this pass.** Implementing backup encryption or off-host
  storage is genuine new infrastructure, which the brief explicitly asked
  us not to add without cause ("do not overengineer... no unnecessary
  encryption systems"). Documented honestly on the Privacy page and as a
  remaining risk below rather than silently left unmentioned.

### 3. Internal architecture docs describe a system more elaborate than what is deployed

- `docs/tds/07-security-architecture.md:42` and
  `docs/tds/01-overview-and-principles.md:110` describe a multi-tenant,
  row-level-security architecture with "contractual commitments" that
  customer structures are "never crossed between tenants."
- The actual deployed system (`src/drugsim_predict/security.py`,
  `src/drugsim_predict/store.py`) has no tenant or user concept at all — a
  single shared API-key set, confirmed by `security.py`'s own docstring:
  "this codebase has no user/tenant concept anywhere in it."
- Not itself a code-level privacy risk, but a documentation-accuracy risk:
  anyone reading the TDS as a description of the live system (a customer's
  security reviewer, for instance) would be misled about what isolation
  actually exists today.
- **Not fixed in this pass** (out of scope — internal architecture docs,
  not user-facing copy or code; rewriting them is a larger documentation
  project than this pass's brief). Flagged here so it is not silently
  carried forward as if resolved.

---

## 🟡 Improvements (implemented)

### 4. `response_json` legitimately stores the canonical structure — but wasn't scoped to a caller

`store.py`'s own pre-existing docstring (`store.py:9-16`, before this
audit) already stated this store "legitimately holds the full canonical
structure, because retrieving `GET /predict/{id}` must be able to show a
caller their own molecule back" — this is a deliberate, reasonable design
choice, not a bug. What made it a problem was finding 1 (no scoping). Now
that retrieval is scoped to the creating API key, this is expected,
documented behavior — see the Privacy page.

### 5. Historical copy readable as a broader guarantee than intended

- `frontend/src/pages/ChangelogPage.tsx:28` and the pre-audit comment in
  `frontend/src/lib/history.ts:20-31` both say local prediction history is
  "never sent to or stored by the server" — accurate for that specific
  feature (a browser-only `localStorage` cache of past results), but easy
  to misread as a claim about the whole backend, especially set against
  the Privacy page's own admission that submitted structures ARE stored
  server-side in the prediction audit record.
- **Fixed**: `history.ts`'s comment was tightened to explicitly
  distinguish "this list" (the local history cache) from the underlying
  submit-and-predict request (still recorded server-side, per the Privacy
  page). The historical changelog entry was left as a historical record
  rather than retroactively edited — `docs/privacy/index.md` already
  states the frontend Privacy page is the authoritative source if any
  other copy ever disagrees with it.

### 6. Two unqualified claims on the Privacy page, unsubstantiated by a stated third-party accounting

- `frontend/src/pages/PrivacyPage.tsx` (pre-audit) stated "DrugSim does not
  sell, share, or use submitted structures for any purpose other than..."
  and "never the structure itself" (in logs) as bare assertions, with no
  section actually naming what third parties exist or don't.
- Per the infra audit (finding 8 below), both claims are **true** — but
  true claims made with no supporting detail read as marketing, not
  engineering fact.
- **Fixed**: added a "Third parties" section naming exactly what does and
  doesn't receive data (see implementation doc), and tied the training and
  logging claims to the specific automated tests that now enforce them.

---

## 🟢 Strengths — already solid, verified, no action needed

### 7. Logging already redacts consistently, with a real enforcement backstop

- Every log call site in `src/drugsim_predict/api.py` and
  `model_registry.py` that touches structure-adjacent data uses
  `structure_digest()` (a one-way hash) — never the raw value. Verified by
  reading every `log.info`/`log.error` call site in both files.
- `configure_logging()` wires `drugsim_core.redaction.redact_event` into
  the structlog processor chain — a pattern-and-key-name-based backstop
  that would catch a raw structure even if a future log call accidentally
  included one.
- `tests/security/test_no_structure_in_logs.py` already contains 11
  end-to-end regression tests, including one that reproduces the exact
  "exception message embeds the real structure" scenario RDKit can
  produce. This is genuinely strong, pre-existing coverage — the audit's
  new tests (implementation doc item 3) extend the same discipline to a
  surface this file didn't cover (HTTP error *responses*, not logs).

### 8. No third-party service ever receives a submitted structure

Confirmed by a full dependency, environment-variable, and code-path audit:

- Zero analytics/telemetry/error-tracking/session-replay SDK exists
  anywhere in the frontend (`frontend/package.json`, full source grep) or
  backend (`requirements-predict-api.txt` lists only `rdkit`, `pydantic`,
  `pydantic-settings`, `structlog`, `pyyaml`, `numpy`, `scikit-learn`,
  `joblib`, `fastapi`, `uvicorn` — no HTTP client at all is even
  installed).
- No LLM/AI API is ever called to generate explanatory text. The
  applicability-domain "rationale" (`src/drugsim_predict/applicability_domain.py:128-133`)
  is a plain Python f-string built from locally computed numbers.
- The only third-party network calls anywhere in the live prediction path:
  none. The only external calls in the *whole repo* are a build-time
  model-artifact download from GitHub Releases
  (`scripts/fetch_model_artifacts.sh`) and the frontend's static Google
  Fonts stylesheet request (`frontend/index.html`) — neither carries
  molecule or user data.
- The S3-backed data-ingestion module (`src/drugsim_ingest/landing.py`,
  used for pulling public chemistry datasets like ChEMBL) is not even
  installed in the live prediction service's Docker image
  (`requirements-predict-api.txt` does not list `boto3`) — it is
  architecturally and physically unreachable from `/predict`.
- `render.yaml` and `.env.example` contain no third-party API
  key/DSN/token of any kind — the only "keys" present are DrugSim's own
  self-issued inbound access-control tokens.

### 9. No training pipeline reads production prediction data

Repo-wide search found no file under `models/`, `scripts/`, or anywhere
else that references `predictions.sqlite3`, `PredictionStore`, or
`prediction_db_path` outside `store.py`/`api.py`/`settings.py` themselves,
the backup/restore scripts, and test files. Now enforced by an automated
structural test (implementation doc item 2) so this cannot silently regress.

### 10. No structure ever reaches the frontend URL, browser telemetry, or an error report

- No `useSearchParams`, `URLSearchParams`, or dynamic route param exists
  anywhere in the frontend router — every route is a static path.
- No error boundary, `window.onerror`, or `unhandledrejection` handler
  exists in the frontend at all, and no error-reporting SDK exists to send
  a caught error to. `frontend/src/components/ErrorPanel.tsx` only renders
  already-local error state to the DOM.
- `localStorage` usage is exactly two keys: the prediction-history cache
  (private to the browser by construction — never transmitted) and a
  boolean UI preference for a collapsible guide. No `sessionStorage` usage
  exists at all.

### 11. Error responses (not just logs) were checked and found safe

`drugsim_core.errors.StructureError`'s `message` is always a fixed
template string ("could not parse smiles structure") — the real RDKit
diagnostic, which can embed fragments of the input, is deliberately
isolated in `context["detail"]`, a field the API layer never reads when
building an HTTP response (`api.py`'s `_problem()` calls use only
`str(exc)`, which returns `message`, never `context`). Verified directly
by reading `drugsim_core/errors.py` and every `StructureError` raise site
in `drugsim_chem/parsing.py` and `standardize.py`. Now pinned by
`tests/security/test_no_structure_in_error_responses.py`.

---

## Summary

Of everything the brief asked us to check, exactly **one** real gap was
found — the `GET /predict/{id}` ownership check — and it has been fixed
with the smallest change consistent with the existing architecture (an API
key hash column, not a new identity system). Backups remaining unencrypted
on local disk is a real, undecided-in-this-pass operational gap, documented
rather than silently deferred. Everything else audited — logging
discipline, third-party isolation, training-pipeline isolation, frontend
telemetry, and error-response safety — was already correctly built, and is
now backed by automated regression tests where it wasn't already.
