# API integration (Step 11) — now live

## What Step 11 required

The brief's own §6 selectivity requirement (a real, continuous binding
comparison, not a binary label) forced a real finding, documented in
`data-sources.md`'s architecture note: `drugsim_predict`'s live
schemas/pipeline only support binary classification output. DRD2/HRH1
needed something else.

## What's live

**`POST /v1/psychiatric-screening`** (`src/drugsim_predict/
psychiatric_pipeline.py` + `psychiatric_schemas.py`) — a separate,
explicitly-labelled surface from `/predict`, deliberately outside
`run_inference`'s promotion gate:

- **hERG** is called through the real, validated `run_inference` path
  exactly as `/predict` does — `reliability_tier: "validated"`.
- **CYP2D6 and BBB** are registered (`models/registry/
  {cyp2d6_activity,bbb_permeability}_v1.json`) into the same generic
  `drugsim_predict.model_registry`/`applicability_domain`/`conformal`
  machinery hERG/CYP3A4 use, but called via the loader directly
  (`get_model_bundle`), not the gated `run_inference` wrapper —
  `reliability_tier: "experimental"`.
- **DRD2 and HRH1** are scored directly against their own artifacts
  (no classification schema fits a continuous value) —
  `reliability_tier: "experimental"`.
- **Selectivity** is derived from the DRD2/HRH1 signals in the same
  response.

Every response carries every signal's own honest `reliability_tier` —
never a single blind pass/fail, and never presenting the four
experimental signals as equivalent to hERG's validated status.

## Why this is a separate endpoint, not part of `/predict`

Two reasons, both real:

1. Routing CYP2D6/BBB through `run_inference` would either fail closed
   (they're `EXPERIMENTAL` -- `EndpointNotAvailableError`, verified
   live) or require weakening `run_inference`'s own promotion gate,
   which would ALSO let them start being served through the primary,
   implicitly-trusted `/predict` route — a much bigger, unintended
   change than this feature asked for.
2. A caller of `/predict` gets one clear guarantee (a validated,
   promoted model). A caller of `/v1/psychiatric-screening` gets six
   signals of genuinely different reliability at once — that needs its
   own response shape (`reliability_tier` required on every signal),
   not a variant of `PredictionResponse`.

## A real deployment problem found and fixed before going live

Render's actual memory metrics showed the existing 2-model
`drugsim-predict-api` service already running near its 512MB plan
limit. DRD2's originally-trained model (`n_estimators=500,
max_depth=None`) was 248MB — deploying it as-is would very likely have
crashed the whole service, taking hERG and CYP3A4 down with it, not
just the new endpoint. DRD2 was retrained with a bounded hyperparameter
grid (`n_estimators=200, max_depth=20`) to 41MB, at a real, disclosed
R² cost (0.5994 → 0.4980) — see `validation.md`'s "Deployment note" and
`limitations.md`.

## What's still not done

- No persisted history for this endpoint (`/predict/{id}`'s equivalent
  does not exist here yet).
- CYP2D6/BBB/DRD2/HRH1 have not been promoted past `EXPERIMENTAL` — no
  independent external validation has been performed for any of the
  four.
