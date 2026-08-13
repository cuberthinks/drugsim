# API Reference (v1.0)

The DrugSim prediction API is a minimal internal service (`src/drugsim_predict/api.py`), not the full multi-tenant design in the original TDS §5 — see `docs/phase5/phase5-prediction-engine.md` for why. This page is the current, v1.0 contract; the Pydantic schemas in `src/drugsim_predict/schemas.py` are the source of truth if this page and the code ever disagree.

## Authentication

A shared `X-API-Key` header, required on every route except `/health` and `/health/ready`, whenever `DRUGSIM_PREDICT_API_KEYS` is configured. A deployment with no keys configured refuses to start in a staging/production environment (`assert_safe_to_start`). This is not a multi-tenant identity system — see `docs/phase8/phase8-deployment-report.md` §2.

## Endpoints

| Method & path | Purpose | Auth |
|---|---|---|
| `POST /predict` | Run inference on one structure for one endpoint | Required (if configured) |
| `GET /predict/{id}` | Retrieve a previously computed prediction | Required (if configured) |
| `GET /endpoints` | List every registered endpoint and its promotion status | Required (if configured) |
| `GET /model` / `GET /model/latest` | Detail for a deployed model (`?endpoint=` selects which; defaults to `herg_inhibition`) | Required (if configured) |
| `GET /health` | Liveness only, no dependency checks | Public |
| `GET /health/ready` | Application, database, model, and prediction-engine checks | Public |

### `POST /predict`

```json
{
  "structure": {"format": "smiles", "value": "CCO"},
  "endpoint": "cyp3a4_inhibition"
}
```

`endpoint` is optional and defaults to `"herg_inhibition"` — an existing client that predates Phase 9's multi-endpoint support gets exactly the behaviour it always had, unchanged.

Response — every field below is present on every successful prediction, always:

- `molecule` — canonical/isomeric/standardised SMILES, InChIKey, formula
- `estimate` — `endpoint`, `predicted_label`, `predicted_probability` (generic, all endpoints), `predicted_probability_blocker` (legacy, hERG-only, `null` for every other endpoint)
- `reliability.conformal` — `predicted_set`, p-values, `nominal_confidence`, `is_singleton`, `method` (names the uncertainty methodology, e.g. `split_conformal_prediction`)
- `reliability.applicability_domain` — `verdict`, similarity/distance evidence, `rationale`, `method`
- `provenance` — `model_id`, `model_version`, `model_checksum`, `dataset_version`, `feature_set_id`, preprocessing versions, `training_set_size`, `input_hash`, `final_report_status`
- `warnings` — structured, never a bare string

**Promotion gate**: an endpoint whose registry status is not `VALIDATED FOR INTERNAL RESEARCH` returns `403 endpoint-not-available`, never a fabricated prediction. An unrecognised endpoint name returns `404 unknown-endpoint`.

### Error shape

Every error response is RFC 9457 `application/problem+json`:

```json
{
  "type": "https://drugsim.internal/errors/invalid-structure",
  "title": "Molecular structure could not be processed",
  "status": 422,
  "detail": "could not parse smiles structure",
  "request_id": "req_...",
  "errors": [{"field": "structure.value", "code": "invalid_structure", "message": "..."}]
}
```

No error response ever contains an `estimate` field, a stack trace, an internal file path, or database detail.

## Rate limiting, body size, concurrency

- 30 requests/minute per API key (or client IP), configurable.
- 64 KiB request body ceiling.
- 10 concurrent in-flight requests per process; a request beyond that gets a `503 server-busy` with `Retry-After`, never queued indefinitely.

## Backward compatibility

The hERG contract predates Phase 9's multi-endpoint work and is unchanged by it: existing `predicted_label` values (`"blocker"`/`"non_blocker"`), `predicted_probability_blocker`, and the default (no `endpoint` field) request shape all still work exactly as before. `predicted_label` and `ConformalSchema.predicted_set` were widened from a hERG-only string-literal type to a plain string to accommodate other endpoints' own label vocabulary — a type relaxation only; the actual values served for hERG are unchanged.

Full audit of this contract for v1.0: [`../phase10/DRUGSIM_V1_FINAL_REPORT.md`](../phase10/DRUGSIM_V1_FINAL_REPORT.md) §"API Status".
