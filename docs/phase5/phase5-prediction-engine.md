# Phase 5 — Prediction Engine

Internal inference service (`src/drugsim_predict`) serving the Phase 4 model
`herg_inhibition` v0.1.0 (**VALIDATED FOR INTERNAL RESEARCH** — not
clinically validated, not production-ready, not a replacement for
laboratory testing).

## Purpose

Given one molecular structure, produce a reproducible hERG-inhibition
prediction with mandatory uncertainty and applicability-domain information,
and log the request with full provenance — inference only, no training, no
new chemistry rules.

## Scope decision: minimal internal API, not the full TDS surface

The TDS (`docs/tds/05-api-specification.md`) specifies a multi-tenant,
OIDC-authenticated, async-job (`POST /v1/predictions` → `202` + job
polling) API supporting stereoisomer enumeration across ~20 endpoints and
batch upload. This phase implements the **explicit minimal endpoint set**
requested (`POST /predict`, `GET /predict/{id}`, `GET /health`, `GET
/model`, `GET /model/latest`, plus `GET /health/ready` per TDS Sec 5.8)
instead, because:

- No multi-tenant auth infrastructure (Keycloak, tenant-scoped Postgres)
  exists in this codebase or environment.
- One model, one endpoint, one compound per request completes in
  milliseconds — the async job model exists in the TDS to handle
  stereoisomer enumeration and 10,000-record batch uploads, neither of
  which this phase builds.
- Building the full surface would mean inventing tenancy/auth/job-queue
  infrastructure not requested and not load-bearing for "serve the
  validated model safely and reproducibly."

This is a scope decision, not a silent gap: contract elements that *don't*
require the missing infrastructure (the envelope shape, RFC 9457 errors,
the reliability-is-mandatory invariant, warning structure) are adopted
directly from the TDS. See **Limitations** for what this means for real
deployment.

## Supported input formats

`smiles` | `molblock` | `inchi` — the three formats `drugsim_chem.parsing`
supports and the TDS names for `POST /v1/predictions`. Parsing and
standardisation are `drugsim_chem.process_structure`, unchanged from Phase
2/3 training — this package never reimplements chemistry.

## Prediction response schema

```
PredictionResponse
├── id, request_id
├── molecule: canonical_smiles, isomeric_smiles, standardized_smiles, inchikey_full, molecular_formula
├── estimate: endpoint, predicted_label, predicted_probability_blocker
├── reliability (REQUIRED — no Optional in the schema):
│   ├── conformal: predicted_set, p_value_blocker, p_value_non_blocker, nominal_confidence, is_singleton
│   └── applicability_domain: verdict, max_tanimoto_to_training, knn_distance, knn_distance_threshold, scaffold_seen_in_training, rationale
├── provenance: model_id, model_version, dataset_version, feature_set_id, training_set_size, final_report_status
├── warnings: [{code, severity, message, field}]
├── inference_timestamp
└── status
```

`reliability` has no default and no `Optional` type — a response literally
cannot be constructed without it (`tests/unit/test_predict_schemas.py`
pins this). `estimate.predicted_probability_blocker`'s field description
states plainly that it is **not** a calibrated probability outside
training-like conditions (Phase 4 finding: ECE degrades 6× under a
class-prevalence shift) — see **Uncertainty and calibration behaviour**.

Errors are RFC 9457 `application/problem+json` (TDS Sec 5.3), for both
chemistry rejections and request-schema validation failures.

## Validation rules

Applied at the serving boundary, not inside `drugsim_chem` (TDS: "do not
invent new chemistry rules in the API layer"):

| Rule | Rejection |
|---|---|
| Empty / whitespace-only input | `StructureError` → `422 invalid-structure` |
| > 5,000 characters | `StructureError` → `422` |
| Fails parsing/sanitisation | `StructureError` (drugsim_chem) → `422` |
| Polymer/Markush wildcard (`*`) atom | `StructureError` → `422` (often surfaces earlier as an InChI-generation failure — both are correct rejections) |
| Mixture with no single dominant fragment | `StructureError` → `422` |
| Molecular weight > 2,000 Da | `StructureError` → `422` |
| Malformed request body / unknown format enum | Pydantic `RequestValidationError` → `422 malformed-request`, still logged |

**No stereoisomer enumeration.** The model was trained and validated on
structures exactly as given (Phase 1 Step 4 §2.3 left this an open policy
question). Enumerating stereoisomers at serving time would predict on
inputs the model was never validated against. Undefined/partial
stereochemistry instead produces a `medium`-severity warning.

## Standardisation and feature generation — reproducibility guarantees

Every call recomputes `feature_set_id` (`drugsim_features.compute_feature_set_id`,
same formula `prepare_features.py` used at training time) from the
*currently installed* RDKit/toolchain versions and compares it against the
value frozen in the model registry. A mismatch raises `ReproducibilityError`
→ `500`, before any chemistry work runs (TDS Sec 6.6 stage 3: "must raise,
never warn"). Feature layout is `concat(18 descriptors, 2048-bit chirality-
aware Morgan fingerprint)`, in the exact field order recorded at training.

## Model / version provenance

`models/registry/herg_inhibition_v1.json` is the source of truth, loaded
once per process (`drugsim_predict.model_registry.get_model_bundle`,
`lru_cache`). Every artifact it references — `model.joblib`, the frozen
`inference_support.npz` (calibration nonconformity scores, training
fingerprints/descriptors, scaffold set), and the descriptor AD scaler — is
**sha256-verified against the checksum recorded at registration**.
`IntegrityError` on any mismatch or missing file, hard-fail, never a
fallback to a different or partial model. `10_export_inference_support.py`
(new this phase) is the only thing that may regenerate the frozen reference
data, and only deliberately, alongside a new `model_version`.

`final_report_status` in the registry was found **stale** during this
phase's development — it still said `EXPERIMENTAL` after Phase 4 had
concluded `VALIDATED FOR INTERNAL RESEARCH`. Fixed, with a status-history
trail added to the registry file so this can't silently happen again
unnoticed.

## Uncertainty and applicability-domain behaviour

**Applicability domain** (`drugsim_predict.applicability_domain`): the exact
three-signal verdict logic validated in Phase 3/4 (max Tanimoto to
training, k-NN descriptor-space distance, scaffold-seen), evaluated against
the *frozen* training reference data — never a live recomputation from
dataset files that could drift. `out_of_domain` and `borderline` verdicts
attach a `high`/`medium` warning; `undeterminable` (uncomputable features)
also warns rather than silently proceeding.

**Conformal prediction** (`drugsim_predict.conformal`): split conformal
sets from the frozen Phase 3 calibration split (never refit at inference
time). **Stated precisely, not loosely**: the nominal-confidence coverage
is a *marginal, population-level* guarantee under exchangeability with
calibration — not a per-instance probability that any single prediction is
correct. Phase 4 confirmed this marginal guarantee survives a real
class-prevalence shift even though pointwise probability calibration does
not (ECE 0.06 → 0.36) — this is exactly why the response returns a
prediction *set* and p-values, never a bare confidence percentage
described as correctness.

Every response also carries a `low`-severity `small_training_set` warning
citing the actual training count (6,792) and the model's Phase 4 status —
so a caller cannot see a bare number without the caveat that justifies it.

## Logging and audit behaviour

Every request — accepted or rejected — is written to a SQLite provenance
log (`drugsim_predict.store.PredictionStore`, one atomic transaction per
write) with: prediction ID, request ID, timestamps, model/dataset/feature
versions, an input-structure digest, a canonical-structure digest,
validation status, applicability-domain verdict, and final status.

**Redaction boundary**: the SQLite row is the tenant-scoped "database row"
(TDS Sec 6.6.1) and legitimately holds the full canonical structure — a
caller must be able to retrieve their own molecule via `GET
/predict/{id}`. The **application log stream** (structlog, `api.py`'s
`log.info`/`log.error` calls) never receives the raw structure — only
`drugsim_core.redaction.structure_digest` hashes, reusing the exact
redaction module Phase 2 built for this purpose rather than inventing a
second one.

## Limitations

- **No authentication.** Internal-only trust model; no `(user_id,
  tenant_id, roles)` resolution exists. Anyone who can reach the service
  can call it. Do not expose this beyond a trusted internal network.
- **No async/batch path.** One structure per request; large batch workloads
  are out of scope for this phase (see Scope decision above).
- **No PBPK simulation, ICH M7 assessment, or the other TDS §5.7 product
  endpoints** — this phase is prediction-serving only.
- **Single model, single endpoint** (`herg_inhibition`). `GET
  /model/latest` is currently identical to `GET /model`; it exists
  separately because a second `model_version` would make them diverge.
- **Raw probability is not a calibrated confidence** outside conditions
  resembling the ~66%-positive training population (Phase 4 finding,
  restated here because it is the single most likely misuse of this API).
- **SQLite, not Postgres.** The provenance log is a local file, consistent
  with every other Phase 2–4 substitution for the unavailable Postgres
  instance in this environment — not horizontally scalable, no concurrent-
  writer story beyond SQLite's own locking.

## Known failure modes

| Symptom | Cause | Response |
|---|---|---|
| `422 invalid-structure` | Bad chemistry per validation rules above | Chemistry-specific message, safe to show a chemist (TDS: "a chemist can act on 'explicit valence...' but not on 'invalid input'") |
| `422 malformed-request` | Request body fails schema validation | Field-level `errors` array |
| `500 internal-error` on every request | `ReproducibilityError` — serving toolchain has drifted from the registered model's training toolchain | Service misconfiguration; not the caller's fault. Check `GET /health/ready` |
| `503` from `/health/ready` | Model bundle failed to load or an artifact checksum mismatched | Do not route traffic; investigate `models/registry/herg_inhibition_v1.json` and artifact integrity |
| `404` from `GET /predict/{id}` | Unknown ID, or the original request was rejected (rejections have no retrievable envelope) | Expected — a rejection is logged but produces no prediction to fetch |
