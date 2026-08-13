# Deployment Guide (v1.0)

Full architecture, security, and operations detail: [`../phase8/phase8-deployment-report.md`](../phase8/phase8-deployment-report.md). This page is a v1.0-current summary plus what Phase 10 changed.

**Deploying on Render specifically?** See [`render.md`](render.md) for a full step-by-step walkthrough (GitHub repo, hosting the model artifacts, `render.yaml`, wiring the two services together). The rest of this page covers the self-hosted Docker Compose topology.

## Architecture

Docker Compose: a FastAPI prediction service (`Dockerfile.predict-api`), a static frontend served behind Caddy (`Dockerfile.frontend`), and a PostgreSQL+RDKit image for the broader platform's data layer. The prediction service's own audit trail is SQLite (`var/predictions.sqlite3`), not Postgres — see the Phase 8 report for why. Caddy terminates TLS and sets standard security headers (`Strict-Transport-Security`, `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, a scoped CSP).

## Pre-deploy gates

Run these before every deploy — both were fixed during Phase 10 to actually cover every registered endpoint, not only the original hERG default:

```bash
python scripts/verify_model_integrity.py
```

Checksum-verifies every registered model's artifact, inference-support data, and descriptor scaler against the registry. Refuses to proceed on any mismatch, missing endpoint's artifact, or unknown endpoint — fails closed.

```bash
python scripts/smoke_test_deployment.py --api-url <url> --frontend-url <url> --api-key <key>
```

Runs against a live, already-deployed instance: frontend loads, API responds, database and model are ready, a known molecule produces a valid prediction with uncertainty and applicability domain attached, **every servable endpoint reported by `GET /endpoints` produces a valid prediction** (Phase 10 addition — this previously only ever exercised the hERG default), and errors are handled correctly.

## Backups and disaster recovery

```bash
python scripts/backup_predictions_db.py --dest-dir var/backups
python scripts/restore_predictions_db.py --backup <path> --dest <path> [--force]
```

Backup uses SQLite's own online-backup API (never a raw file copy) and verifies row count before writing a checksum sidecar. Restore refuses an unverifiable or checksum-mismatched backup, and preserves whatever was at the destination as a `.pre-restore` copy before overwriting. A full cycle — seed, back up, delete the live database, restore, verify exact row content — was re-run live during the Phase 10 audit; see [`../phase10/DRUGSIM_V1_FINAL_REPORT.md`](../phase10/DRUGSIM_V1_FINAL_REPORT.md) §"Disaster Recovery" for the result.

Model artifacts (`.joblib` files) are gitignored and checksum-addressed, not covered by the database backup script — in a real deployment these belong in object storage with its own versioning/redundancy, as documented in the registry's own `artifact.note` field.

## Configuration

Every environment variable is documented, with no real values, in `.env.example` (root) and `frontend/.env.example`. A staging/production deployment with no `DRUGSIM_PREDICT_API_KEYS` configured refuses to start rather than serving unauthenticated.

## Known, disclosed gaps (carried from Phase 8, still true at v1.0)

- No real poetry.lock — `requirements-lock.txt` is an interim, hand-maintained snapshot of direct dependency versions (see that file's own header for the full explanation).
- No per-user data isolation — a shared API key model, not a multi-tenant identity platform.
- In-memory (non-distributed) rate limiting — correct for this deployment's single-worker topology, not for a horizontally-scaled one.
- No domain/TLS certificate provisioned in this environment — `deployment/caddy/Caddyfile` uses the reserved `.example` placeholder domain.
