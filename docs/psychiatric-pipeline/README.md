# Psychiatric Compound Screening Pipeline

A non-clinical, transparent, multi-objective research tool for
screening psychiatric drug candidates across five endpoints: DRD2
(therapeutic target), HRH1 (off-target/weight-gain liability), CYP2D6
(metabolic liability), BBB (CNS exposure), and hERG (cardiac
liability, reused from the existing validated model) — combined with a
direction-correct DRD2/HRH1 selectivity index.

**Status: offline research tool.** A live `POST /v1/psychiatric-screening`
endpoint was attempted twice, crashed the live service both times (OOM
restarts, confirmed in Render's own logs), and was reverted both
times. Retraining DRD2/CYP2D6/BBB smaller (a ~14x reduction in the
four new models' local measured footprint) was not enough to prevent
the second crash. See [api-integration.md](api-integration.md) for the
full two-incident story and what an actual fix would need.

## Read these in order

1. **[scientific-foundation.md](scientific-foundation.md)** — the
   pharmacology audit performed *before* any code was written. Every
   claim this pipeline could make is classified SUPPORTED / PARTIALLY
   SUPPORTED / SIMPLIFIED / NOT SUPPORTED, with the naive selectivity
   formula's error identified here first.
2. **[data-sources.md](data-sources.md)** — the data-availability audit,
   including the real live record counts for every endpoint and the
   discovery that Phase 9 had rejected CYP2D6 using the wrong ChEMBL
   target ID (corrected here and in `docs/phase9/endpoint-selection.md`'s
   own erratum).
3. **[selectivity-methodology.md](selectivity-methodology.md)** — the
   DRD2/HRH1 selectivity index: why the brief's own suggested formula
   is wrong, the actual formula used, and a worked real-compound
   verification.
4. **[benchmarking.md](benchmarking.md)** — every new model compared
   against real majority-class and descriptor-only baselines.
5. **[api-integration.md](api-integration.md)** — the real incident:
   built live, crashed the service on a real test request, reverted
   the same day, and what a real fix would actually need.
6. **[validation.md](validation.md)** — consolidated real results
   across all six endpoints, plus the end-to-end real-compound
   cross-checks.
7. **[limitations.md](limitations.md)** — every honest limitation in
   one place, not scattered only inside individual JSON reports.

## What was built

| Endpoint | Type | Real dataset | Status |
|---|---|---|---|
| DRD2 | regression (pKi) | 8,204 compounds (ChEMBL) | Offline, evaluated (retrained smaller: 248MB→41MB) |
| HRH1 | regression (pKi) | 1,395 compounds (ChEMBL) | Offline, evaluated |
| Selectivity | derived (DRD2 - HRH1) | n/a | Offline, verified |
| CYP2D6 | classification | 2,915 compounds (ChEMBL) | Offline, evaluated, registered EXPERIMENTAL (retrained smaller: 41MB→9MB) |
| BBB | classification | 1,909 compounds (TDC) | Offline, evaluated, registered EXPERIMENTAL (retrained smaller: 13MB→7MB) |
| hERG | classification | 9,589 compounds (ChEMBL, pre-existing) | Reused as-is, live-validated (unaffected by this pipeline) |

## Where the code lives

- `models/psychiatric/{drd2_activity,hrh1_activity,cyp2d6_activity,bbb_permeability}/`
  — each endpoint's fetch → build_dataset → prepare_features → train →
  evaluate pipeline, mirroring `models/admet/{herg_inhibition,cyp3a4_inhibition}/`'s
  established pattern.
- `models/psychiatric/selectivity.py` — the selectivity calculation.
- `models/psychiatric/screening_profile.py` — the multi-objective
  orchestrator combining all six signals.
- `models/psychiatric/benchmarking.py` — the baseline comparisons.
- `models/registry/{cyp2d6_activity,bbb_permeability}_v1.json` — registry
  entries for the two classification endpoints, loadable through the
  existing `drugsim_predict.model_registry` machinery (not currently
  fetched into the live Docker image).
- `tests/unit/test_psychiatric_{selectivity,screening_profile,model_registry}.py`
  — unit tests.

## What was explicitly not done

- CYP2D6/BBB/DRD2/HRH1 are not promoted past `EXPERIMENTAL` — no
  external validation has been performed for any of the four.
- Nothing in this pipeline is wired into the live `drugsim-predict-api`
  service — a live endpoint was attempted twice and crashed the
  service both times (see api-integration.md).
- No frontend UI exists for this pipeline.
- No GNN benchmark for any endpoint (small-data regime for all four
  new endpoints; no existing GNN infrastructure in this repository).
