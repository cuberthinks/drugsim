# API integration (Step 11) — crashed twice, currently offline

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
7. **Redeployed. Crashed a second time.** The build succeeded, health
   checks passed on a fresh instance sitting at ~97MB baseline. A
   single test request loaded CYP2D6, BBB, and hERG — all three logged
   `model.loaded` successfully — and then the process restarted:
   the exact same full boot sequence (`Started server process`,
   `Application startup complete`, `Uvicorn running`) appeared in the
   logs seconds later, with no exception, no traceback, and no
   graceful-shutdown log line in between. That signature (a full
   restart with nothing logged in between) is consistent with an
   OS-level kill, not a Python-level error. Render's memory metric
   (30-second resolution) never showed a spike above ~98MB across this
   whole sequence — the likely explanation is that the actual memory
   spike (e.g. during DRD2's `model.predict()` call, which was never
   reached in the logs, or during response serialization) was brief
   enough to fall entirely between two 30-second samples.
8. **Reverted again, immediately**, back to the exact pre-attempt
   state (hERG + CYP3A4 only). Confirmed stable afterward.

## What both incidents together prove

A ~14x reduction in the four new models' measured *local* incremental
memory footprint (from the first fix) was not enough to prevent a
second real crash. Two real, and now well-evidenced, findings:

1. **Local memory measurements (this project's dev venv runs
   macOS/CPython 3.9) do not reliably predict a Linux/Docker
   container's real behavior**, not just in absolute terms but
   apparently in relative terms too — a measured 14x local improvement
   did not translate into a safe real-world margin.
2. **Render's 30-second metric resolution can miss the actual failure
   mode.** A transient allocation spike (e.g. inside a single
   `RandomForestRegressor.predict()` call across many trees, or during
   JSON-serializing a large combined response) can exceed the memory
   limit and get OS-killed faster than the metrics pipeline samples --
   "no visible spike in the metrics" is not proof of safety.

Retraining the *models themselves* smaller was a real, correct thing
to do (see validation.md's numbers — every accuracy cost was
disclosed), but it is not, by itself, a reliable fix for this specific
failure mode.

## Current status: offline, staying that way pending a different fix

`POST /v1/psychiatric-screening` does not exist on the live service.
Every result in this pipeline comes from running
`models/psychiatric/screening_profile.py::screen_compound()` locally.
All 16 model artifact files (current, retrained-smaller versions)
remain uploaded to the `models-v1` GitHub Release for whenever this is
revisited.

## What an actual fix would need

Two failed attempts at "just make the models smaller" is real evidence
this specific approach has a low ceiling. Options going forward, in
rough order of how directly each addresses what actually failed:

- **A bigger `drugsim-predict-api` instance.** The most direct fix —
  removes the constraint the last two attempts were fighting, rather
  than trying to out-shrink it. A real recurring cost, never a
  unilateral decision.
- **Don't load all six models in the same process for one request.**
  E.g. compute the six signals across multiple smaller calls, or cap
  which subset of experimental models a single request can combine, so
  the peak concurrent resident set is smaller even if the total
  artifact footprint is unchanged.
- **Shrinking further still.** Diminishing returns given what just
  happened — CYP2D6/DRD2 could in principle go smaller yet, at a
  growing, real accuracy cost, with no guarantee it clears whatever
  the actual (still not fully understood) failure threshold is.
