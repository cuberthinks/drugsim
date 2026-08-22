# DrugSim Confidentiality Implementation — 2026-08-22

Companion to `docs/privacy/confidentiality-audit.md` (the before-state
findings). This document describes what actually changed, what didn't, and
why — written so a future engineer or a customer's security reviewer can
verify every claim against real code rather than trusting this document.

## 1. Data flow

```
User's browser (SMILES text, typed)
        │  POST /predict  { structure: { format, value } }
        ▼
ApiKeyMiddleware            -- validates X-API-Key, hashes it (SHA-256),
                                attaches the hash to request.state
        ▼
run_inference()              -- standardises, featurises, scores; the raw
                                structure never leaves this in-process call
        ▼
PredictionStore.record_success()
        │  writes ONE row: canonical structure (inside response_json),
        │  input_hash (one-way digest), api_key_hash (one-way digest of
        │  the caller's key) -- var/predictions.sqlite3
        ▼
HTTP 200 response to the browser (the full PredictionResponse)

Later, optionally:
GET /predict/{id}  -- returns the stored response ONLY if the caller's
                       api_key_hash matches the row's api_key_hash
```

No step in this path calls any external service. See audit finding 8 for
the full accounting of every dependency and network call in the repo.

## 2. What molecular data is stored

- **`var/predictions.sqlite3`** (`src/drugsim_predict/store.py`): one row
  per prediction request (accepted or rejected). An accepted row's
  `response_json` column contains the full `PredictionResponse`, which
  includes the canonicalized structure (`canonical_smiles`,
  `isomeric_smiles`, `standardized_smiles`, `inchikey_full`). This is a
  deliberate design choice, not incidental — `GET /predict/{id}` exists to
  show a caller their own result back, and cannot do that from a hash
  alone. A rejected row stores only `input_hash` (a one-way digest) and
  the rejection reason; no chemistry fields.
- **`var/backups/`**: verbatim, unredacted copies of the same table,
  written locally by `scripts/backup_predictions_db.py` when explicitly
  run (not scheduled automatically by anything in this repo).
- **The browser's own `localStorage`** (`frontend/src/lib/history.ts`):
  purely client-side, under the key `drugsim_prediction_history_v1`,
  including the plaintext canonical SMILES. Never transmitted anywhere —
  confirmed by reading the entire file, which contains no `fetch`/network
  call at all.
- **Nowhere else.** No structure is written to any file, cache, search
  index, or external store outside the two above.

## 3. What molecular data is logged

**None, in raw form, anywhere.** Every log call in
`src/drugsim_predict/api.py` and `model_registry.py` that touches a
structure uses `structure_digest()` — a one-way SHA-256-based digest —
never the raw value. This is backed by a structlog processor
(`drugsim_core.redaction.redact_event`) that also redacts by key name and
by SMILES/InChI pattern matching, as a backstop against a future call site
that forgets. `tests/security/test_no_structure_in_logs.py` (pre-existing,
11 tests) proves this end-to-end, including the specific case of an
exception message that happens to embed a real structure.

## 4. What third parties receive

**None receive a submitted structure.** In full:

- No analytics, telemetry, error-tracking, or session-replay SDK exists in
  either the frontend or backend dependency tree (verified by reading
  `frontend/package.json` and `requirements-predict-api.txt` in full).
- No LLM/AI API is ever called — all explanatory text is generated locally
  from static strings and computed numbers.
- The only external network calls in the entire repository: a build-time
  download of model artifacts from GitHub Releases, and the frontend's
  static Google Fonts stylesheet request (font glyphs only, no molecule
  data, no query parameters).
- Hosting infrastructure (Render.com) runs the servers this deployment
  executes on, which is a different thing from "receives and processes
  submitted structures" — Render does not parse, log, or otherwise act on
  request bodies beyond routing them to this application.

## 5. Training-data isolation

**No training pipeline reads production prediction data**, confirmed by a
repo-wide search (audit finding 9) and now enforced by
`tests/security/test_training_pipeline_isolation.py`, which scans every
Python file in the repository and fails if any reference to the
prediction store appears outside an explicit, reviewed allowlist (the
store's own module, the API, settings, and the backup/restore scripts).
Extending model training to use submitted structures in the future is a
legitimate thing DrugSim could choose to do, but it is explicitly **not**
implemented here, and per the Privacy page, would require its own
separately documented consent mechanism, not a silent default.

## 6. Retention

Prediction records are retained for as long as the deployment operates —
there is no automatic expiry or deletion job anywhere in the code. This is
existing, unchanged behavior; **no retention period was invented for this
document**, and none was implemented, per the brief's own instruction not
to fabricate a policy the system doesn't enforce. Backups are similarly
retained indefinitely on local disk, wherever `backup_predictions_db.py`
was pointed when run.

## 7. Deletion

There is currently **no self-service or automatic deletion mechanism** for
an individual prediction record, in the primary database, in backups, or
anywhere else. A manual `DELETE FROM predictions WHERE id = ?` against
`var/predictions.sqlite3` would remove the live row, but would not reach
any backup file already taken, and this repository provides no tooling to
do either safely today. The Privacy page states this plainly rather than
promising a capability that doesn't exist; it directs a user who needs a
record removed to contact the deployment's operators directly.

## 8. Access control

- **Fixed this pass**: `GET /predict/{id}` now requires the retrieving
  caller's API key to match the key that created the row (compared as
  SHA-256 digests, never raw keys). A mismatch returns the identical 404
  response as a genuinely unknown ID — never a 403 — so the endpoint
  cannot be used to confirm which IDs exist for a caller who doesn't
  already have access to them.
- A row written before this migration, or while no API key was
  configured, has `api_key_hash IS NULL` and is retrievable by **no one**
  once key auth is active (fail closed, not open).
- This is scoped to **API keys**, not individual end users — this
  codebase has no user/tenant model at all (see `api.py`'s own module
  docstring). In the current production deployment, which configures a
  single shared key baked into the public frontend bundle, this fix closes
  the "any distinct valid key can read any other key's data" gap, but does
  **not** create isolation between different visitors to the one public
  site, because they all share that one key today. Real user-to-user
  isolation would require issuing a distinct key per user or building a
  real identity system — an operational/architectural decision this pass
  does not make.
- All other routes' authorization is unchanged: a shared API-key gate on
  every route except `/health`, `/health/ready`, `/docs`, `/redoc`,
  `/openapi.json` (`src/drugsim_predict/security.py`).

## 9. Security tests added

| Test file | What it proves |
|---|---|
| `tests/security/test_prediction_ownership.py` | A different valid API key cannot retrieve another key's prediction; a wrong-owner response is indistinguishable from a genuine 404; a pre-migration row with no recorded owner is retrievable by no one; retrieval is still open when no key auth is configured at all (matching every other route). |
| `tests/security/test_training_pipeline_isolation.py` | No file outside an explicit, reviewed allowlist references the production prediction store — catches any future accidental (or deliberate-but-undocumented) coupling of a training script to live prediction data. |
| `tests/security/test_no_structure_in_error_responses.py` | A malformed, "confidential-looking" structure is never echoed back in an HTTP error response body — covers the schema-validation path, the structure-parsing path, and the generic unhandled-exception path separately. |
| `tests/security/test_no_structure_in_logs.py` | Pre-existing (11 tests, unchanged) — structures never reach the log stream under any of 11 distinct code paths. |
| `frontend/src/components/MoleculeInput.test.tsx` (extended) | The new confidentiality notice renders next to the structure input, with a working link to `/privacy`. |

## 10. Remaining risks

Documented honestly rather than silently deferred:

1. **Backups are unredacted and stored on local disk only** (audit finding
   2). No encryption, no off-host replication is implemented anywhere in
   this repository. Recommended, not implemented: encrypt backup files at
   rest and copy them off the serving host. Not implemented in this pass
   because it is genuine new infrastructure, and the brief explicitly
   asked not to add "unnecessary encryption systems" — this is flagged as
   a decision for whoever operates a given deployment, not something to
   build speculatively.
2. **No per-user isolation exists, only per-API-key isolation** (item 8
   above). The current single-shared-key production deployment does not
   benefit from the `GET /predict/{id}` fix between different end users of
   the same public site — only a deployment that issues genuinely distinct
   keys per caller gets real isolation from it today.
3. **No deletion tooling** (item 7). A record can be manually removed from
   the live database by an operator with direct access, but no safe,
   tested, or backup-aware deletion mechanism exists.
4. **Internal TDS architecture docs overstate current isolation**
   (`docs/tds/07-security-architecture.md`,
   `docs/tds/01-overview-and-principles.md` — audit finding 3). These
   describe a multi-tenant RLS system with "contractual commitments" that
   is not what is actually deployed. Not corrected in this pass (out of
   scope: internal docs, not user-facing copy or code) — flagged so it is
   not mistaken for resolved.

None of these risks involve a third-party ever receiving a structure, a
training pipeline touching production data, or a structure appearing in a
log — those were the areas of highest concern per the brief, and all were
confirmed clean or fixed.
