# API integration (Step 11) — status and the decision point ahead

## What Step 11 actually required

The brief's own §6 selectivity requirement (a real, continuous binding
comparison, not a binary label) already forced a finding, documented in
`data-sources.md`'s architecture note: `drugsim_predict`'s live
schemas/pipeline only support binary classification output. Building
DRD2/HRH1 for real meant this gap had to be dealt with somehow before
"API integration" could mean anything for those two endpoints.

## What has been done (offline, safe, already pushed)

- **CYP2D6 and BBB** (both binary classifiers) are registered
  (`models/registry/{cyp2d6_activity,bbb_permeability}_v1.json`) into
  the exact same generic `drugsim_predict.model_registry` /
  `applicability_domain` / `conformal` machinery hERG and CYP3A4
  already use in production. This is real, verified integration work —
  `load_model_bundle(model_id=...)` loads and checksum-verifies both
  correctly, and the real AD/conformal functions run against them
  unmodified. Both are registered as `final_report_status: EXPERIMENTAL`,
  so `run_inference`'s own promotion gate correctly refuses to serve
  them as normal predictions — verified live (`EndpointNotAvailableError`).
- **DRD2 and HRH1** are scored directly against their own artifacts
  (no classification-shaped serving path exists for continuous
  regression output yet — the gap above, still open).
- **`models/psychiatric/screening_profile.py`** combines all six
  signals (DRD2, HRH1, Selectivity, CYP2D6, BBB, hERG) into one
  structured, per-endpoint-honest Python object — this is the real
  "API integration" at the *library* level: a single function,
  `screen_compound(smiles)`, that any future HTTP layer could wrap
  directly. It is tested (`tests/unit/test_psychiatric_screening_profile.py`)
  and verified end-to-end on real reference compounds
  (`demo_screening_profile.py`).

None of this changes anything the live `drugsim-predict-api` service
currently serves. Every artifact and registry entry above is either
gitignored (never reaches the deployed container) or additive JSON/code
the live app never imports or mounts.

## What has NOT been done, and why it's a separate decision

Turning `screen_compound()` into a live, public HTTP route (a new
FastAPI endpoint on `drugsim-predict-api`) is **not done in this pass**,
deliberately. Two things make this different from every other commit in
this pipeline so far:

1. **Every push to `main` auto-deploys** both live Render services
   (`drugsim-predict-api`, `drugsim-frontend`) — this is not a
   hypothetical, it is this project's actual deploy behaviour. A new
   mounted route would go live the moment it's pushed, not after a
   separate deploy step.
2. Even though the underlying CYP2D6/BBB models are correctly gated
   EXPERIMENTAL, a **new public endpoint that returns real predictions
   for six signals at once** is new live capability on a public
   service — the kind of change this project's own working agreement
   says to check in on first ("anything that would actually change
   live behavior — promoting a new model to serve real predictions"),
   not something to fold into the same "build → verify → push → next
   step" autonomy the offline pipeline work has been using.

**The frontend step (Step 12) is blocked on this same decision** — a
new UI section for psychiatric compound screening needs a live backend
route to call; there is nothing to build a UI against until this is
resolved.

## The actual decision

- **Option A**: keep this pipeline as an offline research tool
  (Python library + CLI demo script) for now. No new live route, no
  frontend work yet. Steps 13-15 (tests/docs/changelog) can still
  proceed to properly close out what's built.
- **Option B**: build and mount a new, clearly-labelled-experimental
  HTTP route (e.g. `POST /v1/psychiatric-screening`) wrapping
  `screen_compound()`, accept that pushing it goes live immediately,
  and then build the frontend UI against it.

This document exists so that choice is made explicitly, not by
momentum.
