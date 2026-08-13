# Deploying DrugSim on Render

This is a from-scratch, copy-pasteable walkthrough: no GitHub repo, no Render services yet. Two services get created — `drugsim-predict-api` (the FastAPI backend, as a Docker web service) and `drugsim-frontend` (the React app, as a static site).

**Honest disclosure up front:** this guide and `render.yaml` were written and reviewed carefully, but were not build-tested against a live Render account or a real Docker build in this environment (neither Docker nor the Render/GitHub CLIs are available here). Every file path, checksum, and env var name was cross-checked against the actual code. If something in Render's current dashboard doesn't match a field name below, its own UI will tell you clearly what's wrong — the manual (non-Blueprint) path in Step 4 is a guaranteed fallback either way.

---

## Step 1 — Create the GitHub repo and push

```bash
# from the drugsim/ directory
gh repo create drugsim --private --source=. --remote=origin
# or, without the gh CLI: create an empty repo on github.com first, then:
git remote add origin https://github.com/YOUR_USERNAME/drugsim.git

git push -u origin main
```

This pushes exactly what's tracked by `.gitignore` — source, docs, tests, config, and the model *registry metadata* (small JSON files). It does **not** push the trained model binaries (`models/**/artifact/*.joblib`, `*.npz` — 187MB combined, gitignored on purpose). That's Step 2.

## Step 2 — Host the model artifacts as a GitHub Release

The backend can't serve predictions without these two models' binary files. They're too large for a normal git push and this repo doesn't use Git LFS, so they travel as GitHub Release assets instead, fetched at Docker build time.

1. On GitHub: your repo → **Releases** → **Create a new release**.
2. Tag: `models-v1` (this exact tag is what `MODEL_RELEASE_URL_BASE` in `render.yaml` points at — use a different tag and update that value to match).
3. Upload these six files as release assets, **renamed exactly as shown** (the build script looks for these exact filenames):

   | Local file | Upload as |
   |---|---|
   | `models/admet/herg_inhibition/artifact/model.joblib` | `herg_model.joblib` |
   | `models/admet/herg_inhibition/artifact/inference_support.npz` | `herg_inference_support.npz` |
   | `models/admet/herg_inhibition/artifact/descriptor_ad_scaler.joblib` | `herg_descriptor_ad_scaler.joblib` |
   | `models/admet/cyp3a4_inhibition/artifact/model.joblib` | `cyp3a4_model.joblib` |
   | `models/admet/cyp3a4_inhibition/artifact/inference_support.npz` | `cyp3a4_inference_support.npz` |
   | `models/admet/cyp3a4_inhibition/artifact/descriptor_ad_scaler.joblib` | `cyp3a4_descriptor_ad_scaler.joblib` |

   (`models/admet/*/artifact/scaler.joblib` is a dev-time intermediate the registry never checksums — don't upload it, it isn't needed.)

4. Publish the release. Note the URL pattern: `https://github.com/YOUR_USERNAME/drugsim/releases/download/models-v1` — this is your `MODEL_RELEASE_URL_BASE`.

You can verify locally that the six URLs resolve before trusting Render's build to it:

```bash
for f in herg_model.joblib herg_inference_support.npz herg_descriptor_ad_scaler.joblib \
         cyp3a4_model.joblib cyp3a4_inference_support.npz cyp3a4_descriptor_ad_scaler.joblib; do
  curl -sIL "https://github.com/YOUR_USERNAME/drugsim/releases/download/models-v1/$f" | head -1
done
# every line should say "HTTP/2 200"
```

## Step 3 — Edit `render.yaml`

Open `render.yaml` at the repo root and replace the one placeholder:

```yaml
dockerBuildArgs:
  MODEL_RELEASE_URL_BASE: https://github.com/YOUR_USERNAME/drugsim/releases/download/models-v1
```

Leave the other `CHANGE_ME` values (`DRUGSIM_PREDICT_CORS_ALLOWED_ORIGINS`, `VITE_API_BASE_URL`) as-is for now — Render only assigns each service's real URL once it exists, so those get filled in during Step 5.

Commit and push:

```bash
git add render.yaml
git commit -m "deploy: configure Render model artifact URL"
git push
```

## Step 4 — Create the services on Render

**Option A — Blueprint (faster, if `render.yaml` validates as-is):**

Render dashboard → **New** → **Blueprint** → connect your GitHub account → select the `drugsim` repo → Render reads `render.yaml` and shows both services → **Apply**.

**Option B — Manual (guaranteed to work, a few more clicks):**

1. **New → Web Service** → connect the `drugsim` repo.
   - Runtime: **Docker**
   - Dockerfile path: `deployment/docker/Dockerfile.predict-api`
   - Docker build context: `.` (repo root)
   - Add a build argument: `MODEL_RELEASE_URL_BASE` = your Step 2 URL
   - Health check path: `/health`
   - Add a **persistent disk**: mount path `/app/var`, 1GB (this is where the prediction audit-log SQLite database lives — without a persistent disk it's wiped on every redeploy)
   - Name it `drugsim-predict-api`
2. **New → Static Site** → connect the same repo.
   - Build command: `cd frontend && npm ci && npm run build`
   - Publish directory: `frontend/dist`
   - Add a rewrite rule: source `/*` → destination `/index.html` (needed for React Router's client-side routes to survive a page refresh)
   - Name it `drugsim-frontend`

## Step 5 — Wire the two services together

Once both exist, Render has assigned each a real URL (e.g. `https://drugsim-predict-api.onrender.com`, `https://drugsim-frontend.onrender.com`). Go back and set:

- On `drugsim-predict-api` → Environment: `DRUGSIM_PREDICT_CORS_ALLOWED_ORIGINS` = the frontend's real URL (comma-separated if you also want to allow local dev, e.g. `https://drugsim-frontend.onrender.com,http://localhost:5173`)
- On `drugsim-frontend` → Environment: `VITE_API_BASE_URL` = the backend's real URL, **no trailing slash, no `/api` suffix** (the backend's routes are mounted at the root — `/predict`, `/health`, `/endpoints` — that `/api` prefix only existed in the docker-compose+Caddy topology, which this deployment doesn't use)

### Access control

`DRUGSIM_ENVIRONMENT=production` means the backend **refuses to start** with no API key configured (`assert_safe_to_start` — see `src/drugsim_predict/settings.py`). Generate one:

```bash
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Paste the **same value** into:
- `drugsim-predict-api` → `DRUGSIM_PREDICT_API_KEYS`
- `drugsim-frontend` → `VITE_API_KEY`

This is a shared key, not real multi-tenant auth — appropriate for "a link I'm sending colleagues," not for a public product (see `docs/deployment/index.md` "Known, disclosed gaps"). `/health` and `/health/ready` stay open regardless, so Render's own health checks keep working.

Changing any env var triggers Render to redeploy the affected service automatically — no need to manually re-trigger after Step 5's edits.

## Step 6 — Verify it actually works

Once both services show "Live" in Render's dashboard:

```bash
curl https://drugsim-predict-api.onrender.com/health
# {"status":"ok"}

curl https://drugsim-predict-api.onrender.com/health/ready
# {"status":"ready","checks":{"application":"ok","model":"ok","database":"ok","prediction_engine":"ok"}}
```

Or, more thoroughly, run this repo's own deployment smoke test against the live URLs (checks both endpoints, not just hERG — see `docs/phase10/DRUGSIM_V1_FINAL_REPORT.md` for why that matters):

```bash
python scripts/smoke_test_deployment.py \
  --api-url https://drugsim-predict-api.onrender.com \
  --frontend-url https://drugsim-frontend.onrender.com \
  --api-key YOUR_GENERATED_KEY
```

Then open `https://drugsim-frontend.onrender.com` in a browser and run a real prediction end to end.

## Known limitations of this specific deployment

- **Render's free/starter web services spin down after inactivity** and take ~30-60s to wake on the next request — the first prediction after a quiet period will be slow. This is a Render platform behavior, not a DrugSim issue; upgrade the backend's plan if that's not acceptable.
- **Redeploys re-download all six model files** from the GitHub Release on every build (no build cache for that step) — fine for occasional redeploys, worth knowing if you're iterating rapidly.
- Everything else already disclosed in `docs/deployment/index.md` "Known, disclosed gaps" (shared API key not real multi-tenant auth, in-memory rate limiting, no distributed workers) applies here unchanged.

## Redeploying after a code change

```bash
git add -A
git commit -m "..."
git push
```

Render auto-deploys both services on push to the connected branch. If you retrain a model and need to update the artifacts, re-upload new assets to a **new** Release tag (don't overwrite an existing release's assets — the whole point of the registry's checksums is to make a silent swap loud, not quiet), update `MODEL_RELEASE_URL_BASE` in `render.yaml`, and push.
