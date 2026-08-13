"""DrugSim prediction engine: reproducible inference over the validated
Phase 4 hERG inhibition model.

This package implements inference only — no training, no new chemistry
rules. Structure parsing, standardisation, and feature computation reuse
``drugsim_chem`` unchanged (the same library Phase 2/3 training used), per
TDS Sec 6.6's anti-skew requirement: training and serving must compute
features identically, or the reported validation results do not apply to
what is actually served.

Modules:
    settings: Paths and limits, overridable via ``DRUGSIM_PREDICT_*`` env vars.
    model_registry: Loads the model + frozen calibration/AD reference data,
        with mandatory checksum verification.
    applicability_domain: The three-signal AD verdict (Tanimoto, k-NN
        descriptor distance, scaffold-seen), matching TDS Sec 6.8.
    conformal: Split conformal prediction sets from the frozen calibration
        split.
    pipeline: The single reproducible parse -> standardise -> featurise ->
        predict -> reliability pipeline.
    schemas: The prediction request/response contract (Pydantic).
    store: SQLite-backed provenance log.
    api: The FastAPI application.
"""

from __future__ import annotations

__all__: list[str] = []
