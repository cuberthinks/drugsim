# Deploying DrugSim on Vercel

**Status: live on Vercel.** API: https://drugsim-api.vercel.app. Frontend:
https://drugsim-frontend.vercel.app. Both were deployed with the Vercel CLI from the
`vercel-migration` branch; the projects are **not yet connected to GitHub**, so a push
does not redeploy them. Render was suspended by the account owner before this work and
was left untouched.

## Shape

Two Vercel projects from this one repository, plus a hosted PostgreSQL:

| Project | Root Directory | What it is |
|---|---|---|
| `drugsim-api` | `deployment/vercel-api` | The FastAPI prediction service as a Python function |
| `drugsim-frontend` | `frontend` | The Vite/React static site (SPA rewrite in `frontend/vercel.json`) |
| PostgreSQL | — | The prediction provenance store (e.g. Neon, via the Vercel Marketplace) |

### Why PostgreSQL
Every `/predict` call writes an audit/provenance row, and `GET /predict/{id}` is
scoped to the API key that created it. Vercel functions have no persistent disk,
so the SQLite file used on Render cannot hold that trail. `PredictionStore` now
runs on PostgreSQL when `DRUGSIM_PREDICT_PREDICTION_DATABASE_URL` is set, and on
SQLite otherwise, so Render and local development are unaffected.

## Setup

**`drugsim-api`** — Root Directory `deployment/vercel-api`. `vercel.json` already
sets the build command (`bash build.sh`, which assembles source + model artifacts
exactly as `Dockerfile.predict-api` does) and the Python version is pinned by
`.python-version`. Environment variables:

| Variable | Value |
|---|---|
| `DRUGSIM_ENVIRONMENT` | `production` (the service refuses to start without an API key in this mode) |
| `DRUGSIM_PREDICT_API_KEYS` | a freshly generated key: `python -c "import secrets; print(secrets.token_urlsafe(32))"` |
| `DRUGSIM_PREDICT_PREDICTION_DATABASE_URL` | the Postgres **pooled** connection string |
| `DRUGSIM_PREDICT_CORS_ALLOWED_ORIGINS` | the frontend's URL, no trailing slash |

**`drugsim-frontend`** — Root Directory `frontend`. Build-time variables:
`VITE_API_BASE_URL` = the API project's URL (no trailing slash, no `/api` suffix;
routes are at the root: `/predict`, `/health`, …) and `VITE_API_KEY` = the same
key as above. As already documented in `frontend/.env.example`, a `VITE_` value is
readable in the browser bundle: it is a weak barrier, not a secret.

## Verified locally

The assembled bundle (not the repo source) was run in production mode against a
real PostgreSQL 16: readiness reports model, database and prediction engine all
`ok`; a keyless request is 401; caffeine is identified and predicted; the creating
key can fetch its prediction and a different valid key gets 404; an invalid
structure is 422; and both the accepted (keyed) and rejected rows are in the
database. Ownership isolation is also covered by the test suite on both backends.

## Verified on real Vercel builds

- **Bundle size: fits.** The first build was 505.02 MB against Vercel's **500 MB**
  function limit. `build.sh` now prunes `tests`/`test` directories from the installed
  venv (Vercel installs dependencies *before* running it and bundles *after*), then runs
  a real prediction in the pruned environment so a bad prune fails the build. Result:
  site-packages 402 -> 371 MB, bundle **478.65 MB**. Vercel then moves dependencies to
  install at cold start (about 3 s) and the deployed function is 67 MB.
- **Behaviour matches Render.** For the same molecule, all 14 compared fields (label,
  probability, conformal set and p-values, applicability-domain verdict and statistics,
  model checksum, RDKit version, feature-set id, identity) were identical to the last
  live Render response.
- **Latency (preview, Hobby):** first prediction on an idle instance about 3.3 s, warm
  about 0.7 s, second model's first call about 1.6 s.
- **Persistence:** with Neon attached, the repository's own
  `scripts/smoke_test_deployment.py` passes all checks, and the audit rows are present
  in Neon (pooled endpoint; keyed rows for accepted requests; probability stored as
  double precision; no raw structure in the hash columns).

## Gotchas learned the hard way

- **A project's first deploy becomes *production*** in the CLI even when you pass
  `--target preview` (it happened to the frontend). Deployment protection keeps such a
  URL private, but the project's `<name>.vercel.app` production alias was publicly
  reachable. Create the project, set its production env vars, and only then deploy.
- Deployment protection blocks previews. Test them with a project **automation bypass
  secret** sent as the `x-vercel-protection-bypass` header; revoke it when finished.
- `--prefix DRUGSIM_PREDICT_PREDICTION_` on `vercel integration add neon` yields
  `DRUGSIM_PREDICT_PREDICTION_DATABASE_URL` (the pooled string), which is what the
  API reads. It prefixes every Neon variable; the API ignores the extras.
- The Vercel CLI uploads git-ignored files; `.vercelignore` keeps the 115 MB of local
  model artifacts out (the build fetches them itself).

## Cutover (done 2026-10-05)

API project protection turned off (the API key is its lock), CORS origin set to the
frontend, API promoted to production, frontend wired to it and redeployed. Verified on
the public URLs: repository smoke test passes all 8 checks including the frontend;
missing or wrong key is 401; CORS allows only the frontend origin; and a prediction made
through the real UI (Terfenadine) returned its PubChem-verified identity, a hERG
inhibitor call with probability 0.920, and the audit row in Neon. The temporary
protection-bypass secret used for preview testing was revoked.

## Remaining

1. Merge `vercel-migration` to `main` and connect both projects to GitHub
   (`vercel git connect`) so pushes deploy. Until then, redeploy by hand with
   `vercel deploy --prod` from the repository root using the project's IDs.
2. A custom domain, if wanted.
3. Decide Render's fate (it is suspended). Nothing here depends on it.
4. Preview and production share one Neon database, so test rows from previews and smoke
   tests are mixed into the audit table. Use a separate Neon branch for previews if
   that matters.
5. `VITE_API_KEY` is baked into the public frontend bundle. This is the project's
   documented design (a weak barrier, not a secret); stronger protection needs a
   server-side proxy or Vercel's firewall rate limiting, not a different env var.
6. Vercel's Hobby plan is for non-commercial use.

## Behaviour that differs from Render

- Rate limiting and the concurrency cap are in-process, so on serverless they apply
  **per instance**, not globally. Stricter global limits would need Vercel's
  firewall rate limiting.
- `scripts/backup_predictions_db.py` / `restore_predictions_db.py` are SQLite-only.
  On PostgreSQL, backups are the provider's (point-in-time recovery).
- The first request to a cold instance pays the model-load cost.

## Cutover and rollback

1. Deploy. Run
   `python scripts/smoke_test_deployment.py --api-url <api> --frontend-url <web> --api-key <key>`
   against them; it must pass.
2. Only then point users at the Vercel URLs. Leave Render running for at least a
   week.
3. Rollback is to switch back to the Render URLs, which are untouched.

If the bundle does not fit, the fallback that needs no further engineering is a
hybrid: frontend on Vercel, API left on Render (set `VITE_API_BASE_URL` to the
Render URL and add the Vercel origin to the API's CORS list).
