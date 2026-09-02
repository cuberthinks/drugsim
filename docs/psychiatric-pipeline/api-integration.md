# API integration (Step 11) — attempted, reverted after a real incident

## What happened, in order

1. `POST /v1/psychiatric-screening` was built and shipped: a separate,
   explicitly-labelled live endpoint combining DRD2, HRH1, selectivity,
   CYP2D6, BBB, and the existing hERG model, each signal carrying its
   own honest `reliability_tier` (`"validated"` for hERG,
   `"experimental"` for the rest).
2. Before going live, Render's real memory metrics showed the existing
   2-model `drugsim-predict-api` service already running near its
   512MB plan limit. DRD2's originally-trained model (248MB) was
   retrained with a bounded hyperparameter grid down to 41MB
   specifically to reduce this risk (R² cost: 0.5994 → 0.4980).
3. Deployed. The build succeeded, health checks passed, the new route
   registered correctly.
4. **A real test request to the new endpoint crashed the service.**
   Render's logs show the request loading hERG, then starting to load
   CYP2D6, then: `Instance srv-da0828dbedkc73a51dag-49sqj restarted` —
   an OOM kill, ~10 seconds after the request started. The instance
   auto-restarted (Render's supervisor) and health checks resumed
   within ~10 seconds, but during that window `/predict` itself would
   have failed for any concurrent real user, not just the new endpoint.
5. **Reverted the same day.** The route, its schemas
   (`psychiatric_schemas.py`), and its serving wrapper
   (`psychiatric_pipeline.py`) were removed; `Dockerfile.predict-api`
   and `scripts/fetch_model_artifacts.sh` were reverted to fetching
   only hERG and CYP3A4, matching the state before this attempt.

## What this proves and doesn't prove

The DRD2 retraining fix was real and worth keeping (41MB is still much
better than 248MB), but it wasn't sufficient on its own — the
*combined* footprint of hERG + CYP2D6 alone (before BBB, DRD2, or HRH1
were even touched) was enough to exceed the container's memory budget.
This is a genuine capacity problem, not a bug in any one model.

## What's kept vs. reverted

**Kept** (real, verified, offline):
- All four new datasets, models, and evaluations (DRD2, HRH1, CYP2D6,
  BBB) — unchanged in what they measure and report.
- `models/psychiatric/screening_profile.py` — the six-signal
  orchestrator, now clearly documented as an offline library
  (`screen_compound()`), with the caching fixes found during this
  attempt (see below) kept because they're correct regardless of
  whether this is ever served live.
- `models/registry/{cyp2d6_activity,bbb_permeability}_v1.json` —
  still real, valid registrations proving these fit the generic
  architecture; just not fetched into the live Docker image.
- All 16 model artifact files remain uploaded to the `models-v1`
  GitHub Release, ready for whenever this is revisited.
- Two real engineering fixes found and kept: (1) `screening_profile.py`
  was calling the *uncached* model loaders on every request — switched
  to the same `lru_cache`-based loaders `/predict` itself uses; (2)
  DRD2's smaller, retrained model.

**Reverted**:
- `POST /v1/psychiatric-screening` and its route/schema code.
- The `Dockerfile.predict-api` / `fetch_model_artifacts.sh` additions
  for CYP2D6/BBB/DRD2/HRH1.

## What a real fix would need

Either of these, not attempted in this pass:

- **A bigger `drugsim-predict-api` instance.** The current plan
  (Starter, 512MB) is already near its limit with just hERG+CYP3A4.
  This is a real cost decision, not something to make unilaterally.
- **A smaller combined footprint.** Further reducing DRD2 (already
  retrained once), and/or CYP2D6 (41MB) and BBB (13MB), and/or not
  loading all six models in a single process per request (e.g. a
  request-scoped subset, or lazy-unloading between requests) would
  need real measurement, not just estimation from local dev-venv
  numbers (which run on macOS/CPython 3.9 and do not reliably predict
  Render's Linux/3.12-slim container behavior — the discrepancy was
  large enough in this attempt to be worth naming explicitly).
