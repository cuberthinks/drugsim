# Deploying DrugSim on Vercel

**Status: prepared, not live.** Render still serves production and is unchanged.
This documents the Vercel path, what has been verified, and what can only be
verified by a real Vercel deploy.

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

## NOT verified — needs a real Vercel deploy

1. **Bundle size.** Measured for Linux x86_64: dependencies 396 MB unzipped
   (scipy 83, rdkit 68, sklearn 42, numpy + its libs 65, psycopg 20) plus 116 MB of
   source and models = about **512 MB**; roughly 414 MB if test directories are
   excluded. Vercel's documentation confirms Python bundles have a size cap but the
   figure was not retrievable, so whether this fits is unknown until a preview
   deploy builds. This is the go/no-go for moving the API.
2. That files produced by `build.sh` are included in the function bundle.
3. Cold-start time (two models, 115 MB, loaded on first request per instance) and
   the memory available to the function.

## Behaviour that differs from Render

- Rate limiting and the concurrency cap are in-process, so on serverless they apply
  **per instance**, not globally. Stricter global limits would need Vercel's
  firewall rate limiting.
- `scripts/backup_predictions_db.py` / `restore_predictions_db.py` are SQLite-only.
  On PostgreSQL, backups are the provider's (point-in-time recovery).
- The first request to a cold instance pays the model-load cost.

## Cutover and rollback

1. Deploy both projects as previews. Run
   `python scripts/smoke_test_deployment.py --api-url <api> --frontend-url <web> --api-key <key>`
   against them; it must pass.
2. Only then point users at the Vercel URLs. Leave Render running for at least a
   week.
3. Rollback is to switch back to the Render URLs, which are untouched.

If the bundle does not fit, the fallback that needs no further engineering is a
hybrid: frontend on Vercel, API left on Render (set `VITE_API_BASE_URL` to the
Render URL and add the Vercel origin to the API's CORS list).
