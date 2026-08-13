# Methodology

How every DrugSim prediction is made, stage by stage. This mirrors the frontend's own Methodology page (`frontend/src/pages/MethodologyPage.tsx`) so the two never drift apart in meaning, expanded here with links to the underlying phase reports.

1. **Data** — Raw bioactivity measurements for each endpoint are assembled from curated public sources (ChEMBL, fetched directly via its REST API), with provenance tracked for every record. Every endpoint uses its own dataset, built and audited independently of the others.
2. **Standardisation** — Structures are parsed, sanitised, and canonicalised through a fixed RDKit-based pipeline (`drugsim_chem`) so the same molecule always yields the same representation, regardless of which endpoint is being predicted.
3. **Dataset construction** — Measurements are deduplicated and aggregated per compound (geometric mean of matching activity records), labelled against a fixed, documented activity threshold, and split by molecular scaffold (deterministic hashing, ADR-009) to prevent leakage between training and test sets.
4. **Model** — A classical, interpretable classifier (Random Forest) is trained on molecular descriptors and a Morgan fingerprint derived from the standardised structures, then registered with a versioned, checksummed model ID. No deep learning is used without a demonstrated reason (none has been, as of v1.0).
5. **Applicability domain** — Each new structure is compared against the training set by fingerprint similarity, descriptor-space distance, and scaffold membership, to assess how well-covered it is by the model's actual evidence.
6. **Uncertainty** — Split conformal prediction wraps the model's raw output in a calibrated prediction set with a stated, empirically-verified coverage guarantee, rather than a single point estimate presented as if it were exact.
7. **Prediction assembly** — The prediction engine (`src/drugsim_predict/pipeline.py`) combines the model output, applicability-domain assessment, and conformal set into one response, self-describing its own uncertainty and AD methodology by name — never returned without that context.

Each endpoint's own dataset size, model version, validation metrics, and known limitations are in [`../scientific/index.md`](../scientific/index.md) and, in full, [`../phase10/final-scientific-audit.md`](../phase10/final-scientific-audit.md).

## Full documentation trail

- hERG: model validation ([Phase 3](../phase3/phase3-model-validation-report.md)), scientific audit ([Phase 3.5](../phase3/phase3.5-scientific-audit.md)), reliability and robustness testing ([Phase 4](../phase4/phase4-reliability-report.md))
- Prediction engine and API contract: [Phase 5](../phase5/phase5-prediction-engine.md)
- CYP3A4's own end-to-end evaluation: [Phase 9](../phase9/phase9-admet-expansion-report.md)
- Final, cross-endpoint scientific audit for release: [Phase 10](../phase10/final-scientific-audit.md)

These are not duplicated in full here, to avoid the two copies drifting out of sync.
