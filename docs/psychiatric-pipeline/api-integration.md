# API integration (Step 11) — crashed once, fixed, retried

## What happened, in order

1. `POST /v1/psychiatric-screening` was built and shipped: a separate,
   explicitly-labelled live endpoint combining DRD2, HRH1, selectivity,
   CYP2D6, BBB, and the existing hERG model, each signal carrying its
   own honest `reliability_tier` (`"validated"` for hERG,
   `"experimental"` for the rest).
2. Before the first deploy, Render's real memory metrics showed the
   existing 2-model `drugsim-predict-api` service already running near
   its 512MB plan limit. DRD2's originally-trained model (248MB) was
   retrained with a bounded hyperparameter grid down to 41MB
   specifically to reduce this risk (R² cost: 0.5994 → 0.4980).
3. Deployed. Build succeeded, health checks passed, the route
   registered correctly.
4. **A real test request crashed the service.** Render's logs show the
   request loading hERG, then starting to load CYP2D6, then:
   `Instance ... restarted` — an OOM kill, ~10 seconds after the
   request started. The instance auto-restarted and health checks
   resumed within ~10 seconds, but during that window `/predict`
   itself would have failed for any concurrent real user, not just the
   new endpoint.
5. **Reverted the same day.** The route, its schemas, and its serving
   wrapper were removed; `Dockerfile.predict-api` and
   `fetch_model_artifacts.sh` were reverted to fetching only hERG and
   CYP3A4.
6. **CYP2D6 and BBB were also retrained smaller**, on top of DRD2's
   earlier fix, before attempting again:

   | Model | Before | After | Accuracy before → after |
   |---|---|---|---|
   | DRD2 | 248MB | 41MB | R² 0.5994 → 0.4980 |
   | CYP2D6 | 41MB | 9MB | ROC-AUC 0.8333 → 0.8251 |
   | BBB | 13MB | 7MB | ROC-AUC 0.9615 → 0.9507 (test-set confusion matrix unchanged) |
   | HRH1 | 0.13MB | unchanged | unchanged |

   All three retrainings used the same fix: a bounded hyperparameter
   grid (`n_estimators=200, max_depth=20` for the two that had been
   unbounded) instead of the original `(200, 500) x (None, 20)` search,
   which had picked the largest, most expensive option each time for a
   negligible validation-set gain. Combined, the four new models'
   local incremental memory cost (measured via a local FastAPI
   TestClient, not identical to but indicative of the real container)
   dropped roughly 14x, from ~329MB to ~23MB, between the first and
   second attempt.
7. **Redeployed.** See the result below.

## What this incident proves

The DRD2-only retraining fix was real and worth keeping, but wasn't
sufficient on its own — the *combined* footprint of hERG + CYP2D6
alone (before BBB, DRD2, or HRH1 were even touched) was enough to
exceed the container's memory budget. This is a genuine capacity
problem across the whole new-endpoint set, not a defect in any one
model. It's also a reminder that **local memory measurements (this
project's dev venv runs macOS/CPython 3.9) do not reliably predict a
Linux/Docker container's real behavior** — Render's own `get_metrics`
(memory_usage, memory_limit) was the only trustworthy signal used to
decide whether the second attempt was safe enough to try.

## What's live now

`POST /v1/psychiatric-screening`, combining DRD2, HRH1, selectivity,
CYP2D6, BBB, and hERG, each with its own real `reliability_tier`.
Registered the same way as before (CYP2D6/BBB into
`drugsim_predict.model_registry`, DRD2/HRH1 scored directly), reusing
the same `get_model_bundle`/`assess_applicability_domain`/
`compute_conformal_set` machinery `/predict` itself uses for the two
classification endpoints.

## What a further fix would still need, if this recurs

If real Render metrics after this deploy show the margin is still too
thin for comfort, the remaining options are the same two named after
the first incident: a bigger `drugsim-predict-api` instance (a real
cost decision, never made unilaterally), or shrinking further still
(BBB and HRH1 are already small; CYP2D6/DRD2 could in principle go
smaller yet, at a growing accuracy cost each time).
