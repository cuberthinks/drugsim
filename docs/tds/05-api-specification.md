# TDS §5 — API Specification

**Definition only. No implementation.**

---

## 5.1 Design Decisions

### 5.1.1 Prediction is asynchronous

**Decision: `POST /v1/predictions` returns `202 Accepted` with a job reference, not a result.**

A single request may involve stereoisomer enumeration (up to 8 structures), descriptor computation, inference across ~20 endpoints, conformal interval computation, and k-NN applicability-domain assessment against the training set. For a batch upload, multiply by the compound count. Response times range from hundreds of milliseconds to minutes.

A synchronous API would force either an arbitrary cap on batch size or long-held connections with timeout ambiguity — where a client cannot distinguish "still working" from "failed", and retries duplicate work. The job model makes progress observable and retries safe.

**A synchronous convenience path exists** — `POST /v1/predictions?wait=true&timeout=30` — which blocks up to 30 s and falls back to `202` with the job reference on timeout. This serves interactive single-compound use without making the contract dishonest about the underlying execution.

### 5.1.2 Other conventions

| Concern | Decision |
|---|---|
| Versioning | Path-based `/v1/`. Explicit, cache-friendly, unambiguous in logs. Header negotiation was rejected as too easy to get wrong |
| Errors | **RFC 9457** `application/problem+json` |
| Idempotency | `Idempotency-Key` header on all POSTs; keys retained 24 h |
| Pagination | Cursor-based. Offset pagination is unstable under concurrent inserts |
| Auth | OIDC Bearer (interactive) or API key (programmatic); both resolve to a user and tenant |
| Rate limiting | Token bucket per tenant; `429` with `Retry-After` |
| Compression | gzip/br on responses > 1 KB |
| Request size | 10 MB default; 100 MB for batch upload endpoints |
| Correlation | `X-Request-Id` echoed; propagated as `trace_id` |

---

## 5.2 Authentication & Authorisation

| Method | Use | Header |
|---|---|---|
| OIDC Bearer (Keycloak) | Web app, interactive | `Authorization: Bearer <jwt>` |
| API key | Scripts, pipelines | `Authorization: ApiKey <key>` |

**Every request resolves to `(user_id, tenant_id, roles)`. `tenant_id` is never accepted from the client** — always derived from the credential. A client-supplied tenant is the classic cross-tenant data leak, and for DrugSim that means leaking one customer's molecular IP to another.

| Role | Permissions |
|---|---|
| `readonly` | GET on own-tenant resources |
| `scientist` | + create compounds, predictions, experiments |
| `curator` | + manage datasets, trigger ingestion |
| `reviewer` | + sign expert reviews (requires `can_sign`, MFA) |
| `admin` | + tenant user management |

Model, dataset and endpoint metadata are readable by any authenticated user regardless of tenant — it is public reference data. Everything compound- or prediction-shaped is tenant-scoped.

---

## 5.3 Error Model

```json
{
  "type": "https://api.drugsim.io/errors/invalid-structure",
  "title": "Molecular structure could not be parsed",
  "status": 422,
  "detail": "RDKit sanitisation failed: Explicit valence for atom # 3 N, 4, is greater than permitted",
  "instance": "/v1/compounds",
  "request_id": "req_01J8XK...",
  "errors": [{ "field": "smiles", "code": "sanitisation_failed",
               "message": "Explicit valence for atom # 3 N, 4, is greater than permitted" }]
}
```

| Status | Type slug | When |
|---|---|---|
| 400 | `malformed-request` | Unparseable JSON, missing required field |
| 401 | `unauthenticated` | Missing/invalid credential |
| 403 | `forbidden` | Authenticated, insufficient role |
| 404 | `not-found` | Absent, **or exists in another tenant** |
| 409 | `conflict` | Idempotency key reuse with different payload |
| 413 | `payload-too-large` | Above size limit |
| 415 | `unsupported-media-type` | Unrecognised chemical format |
| 422 | `invalid-structure` | Parseable request, invalid chemistry |
| 422 | `unsupported-endpoint` | No validated model for the requested endpoint |
| 429 | `rate-limited` | Quota exceeded |
| 500 | `internal-error` | Unexpected — never leaks internals |
| 503 | `service-unavailable` | Dependency down; `Retry-After` |

**404, not 403, for cross-tenant access.** Returning 403 confirms the resource exists, which leaks the existence of another customer's compound — for a drug discovery platform, even that is commercially sensitive.

**Chemical errors are 422 with the RDKit message**, because a chemist can act on "explicit valence for atom 3 N is 4" but not on "invalid input".

---

## 5.4 Prediction Endpoints

### `POST /v1/predictions`

**Purpose:** Request predictions for one structure across one or more endpoints.
**Auth:** `scientist`+ · **Idempotency:** required

**Request**
```json
{
  "structure": { "format": "smiles", "value": "CC(=O)Oc1ccccc1C(=O)O" },
  "endpoints": ["caco2_papp", "herg_inhibition", "hepatotoxicity_dili"],
  "options": {
    "stereoisomer_policy": "enumerate",
    "max_stereoisomers": 8,
    "include_evidence": true,
    "experiment_id": null
  }
}
```

| Field | Type | Req | Validation |
|---|---|---|---|
| `structure.format` | enum | ✔ | `smiles`\|`molblock`\|`inchi` |
| `structure.value` | string | ✔ | ≤ 100 KB; must parse and sanitise |
| `endpoints` | string[] | ✔ | 1–50; each must exist and have a deployed validated model |
| `options.stereoisomer_policy` | enum | ○ | `as_given`\|`enumerate`\|`require_defined` (default `enumerate`) |
| `options.max_stereoisomers` | int | ○ | 1–16, default 8 |
| `options.include_evidence` | bool | ○ | default `true` |
| `options.experiment_id` | string\|null | ○ | Must belong to caller's tenant |

**Response `202`**
```json
{ "object": "job", "id": "job_01J8XK...", "status": "queued",
  "compound_id": "cmp_01J8XK...", "endpoints_requested": 3,
  "estimated_completion_seconds": 12,
  "links": { "self": "/v1/jobs/job_01J8XK...", "results": "/v1/jobs/job_01J8XK.../results" } }
```

**Validation rules**
1. Structure parses and sanitises → else `422 invalid-structure`
2. Rejected classes: polymers/Markush (`*` atoms), MW > 2000, mixtures with no dominant fragment → `422` with a specific reason
3. Every requested endpoint has a **deployed, validated** model → else `422 unsupported-endpoint` listing the unsupported ones
4. `require_defined` policy with undefined stereocentres → `422 undefined-stereochemistry`
5. Tenant quota checked before enqueue

**Errors:** 400, 401, 403, 413, 422 (`invalid-structure`, `unsupported-endpoint`, `undefined-stereochemistry`), 429, 503

**Note on rule 3:** requesting an endpoint DrugSim cannot credibly predict returns an error naming it, rather than a low-confidence guess. Phase 1 identified NOAEL, nephrotoxicity and neurotoxicity as having no adequate public source; they are absent from the endpoint registry and this is the path by which that absence surfaces.

---

### `POST /v1/predictions/batch`

**Purpose:** Predictions for many structures (SDF, SMILES list, CSV).
**Auth:** `scientist`+ · **Content-Type:** `multipart/form-data` · **Max:** 100 MB / 10,000 structures

**File validation — a security boundary, not a convenience check** (§7):

| Check | Rule |
|---|---|
| Size | ≤ 100 MB uncompressed; compressed uploads rejected (zip-bomb surface) |
| Record count | ≤ 10,000; counted by streaming, never by loading whole |
| Per-record size | ≤ 100 KB |
| Parse timeout | 5 s per record, hard-killed |
| Memory ceiling | Parsing in a sandboxed subprocess with an rlimit |
| Encoding | UTF-8 only; nulls and control characters rejected |
| Property fields | Names/values length-capped; never evaluated or interpolated |

**Response `202`** with `job_id`, `accepted_count`, `rejected_count`, and per-record rejection reasons. Partial acceptance is intentional — one bad record in 10,000 must not fail the batch, but the caller is told exactly which.

---

### `GET /v1/jobs/{job_id}`

**Purpose:** Job status.
**Response `200`:** `{object: "job", id, status: queued|running|complete|failed|partial, progress: {total, completed, failed}, created_at, completed_at, error?, links}`

`partial` is a real terminal state: some endpoints succeeded, others failed. Reporting the whole job failed would discard usable results.

---

### `GET /v1/predictions/{id}`

**Purpose:** Retrieve one prediction envelope.
**Auth:** any role, own tenant.
**Response `200`:** the envelope defined in §4.3 — `estimate`, `reliability`, `evidence`, `provenance`, `must_display`, `warnings`.

**Contract guarantee:** the response **never** contains `estimate` without `reliability`. This is asserted by contract tests, not merely intended (§5.9).

**Warnings** are structured, e.g.:
```json
[{ "code": "out_of_domain",
   "severity": "high",
   "message": "Query compound has maximum Tanimoto similarity 0.21 to the training set. This prediction is an extrapolation.",
   "field": "reliability.applicability_domain" },
 { "code": "small_training_set",
   "severity": "medium",
   "message": "Model trained on 475 compounds. Interval width reflects this limitation." }]
```

---

## 5.5 Compound Endpoints

| Endpoint | Purpose | Auth | Key validation | Errors |
|---|---|---|---|---|
| `POST /v1/compounds` | Register/standardise a structure; idempotent on InChIKey | scientist | As §5.4 rule 1–2 | 422, 413 |
| `GET /v1/compounds/{id}` | Retrieve with properties, drug-likeness, alerts | readonly | Tenant scope | 404 |
| `GET /v1/compounds/{id}/predictions` | All predictions; paginated, filterable by endpoint | readonly | — | 404 |
| `POST /v1/compounds/search` | Substructure / similarity / exact | readonly | §5.5.1 | 422 |

### 5.5.1 `POST /v1/compounds/search`

```json
{ "query": { "type": "similarity", "format": "smiles",
             "value": "CC(=O)Oc1ccccc1C(=O)O", "threshold": 0.7 },
  "scope": "public",
  "limit": 50, "cursor": null }
```

| Field | Validation |
|---|---|
| `query.type` | `exact`\|`substructure`\|`similarity`\|`scaffold` |
| `query.threshold` | 0.5–1.0; **required** for `similarity` |
| `scope` | `public`\|`tenant`\|`both` — default `public` |
| `limit` | 1–200 |

**Substructure queries are cost-bounded:** a highly generic query (e.g. a bare benzene ring) can match millions of rows. The API applies a statement timeout and returns `422 query-too-broad` with guidance rather than degrading the database. Backed by the RDKit cartridge GiST indexes.

**`scope` defaults to `public`.** Searching one's own tenant is opt-in, and cross-tenant search does not exist at any scope value.

---

## 5.6 Reference Endpoints

All readable by any authenticated user; tenant-independent public reference data.

| Endpoint | Purpose | Notes |
|---|---|---|
| `GET /v1/endpoints` | List predictable endpoints | Filter by `category`, `has_deployed_model`. **The authoritative statement of what DrugSim can predict** |
| `GET /v1/endpoints/{id}` | Endpoint detail | Canonical unit, task type, `higher_is_worse`, training-set size, model availability |
| `GET /v1/models` | List models | Filter by `endpoint_id`, `status`, `is_validated` |
| `GET /v1/models/{id}` | Model detail | Includes **dual-split performance** (§4.4.1) |
| `GET /v1/models/{id}/validation` | OECD five-principle records + QMRF link | `403` unless `reviewer`+ |
| `GET /v1/datasets` | Source registry projection | Licence, verification status, cadence, staleness |
| `GET /v1/datasets/{id}` | Dataset detail | Includes `unit_documentation_available` |
| `GET /v1/targets/{id}` | Target detail | Components, classification |
| `GET /v1/proteins/{id}` | Protein detail | Includes `is_reviewed`, orthologs |

**`GET /v1/endpoints` is the honest inventory.** An endpoint with no deployed model appears with `has_deployed_model: false` and a reason — this is how a client discovers that hepatotoxicity is supported and nephrotoxicity is not, without inferring it from an error.

---

## 5.7 Experiment, Simulation, Report, Assessment

| Endpoint | Purpose | Auth | Notes |
|---|---|---|---|
| `POST /v1/experiments` | Create | scientist | Draft state |
| `GET /v1/experiments` | List own-tenant | readonly | Paginated |
| `GET /v1/experiments/{id}` | Detail + summary | readonly | Includes OOD count |
| `POST /v1/experiments/{id}/run` | Execute | scientist | **Freezes `core_db_release` and model versions** |
| `POST /v1/simulations` | PBPK simulation | scientist | **Phase 5** — returns `501` until then |
| `GET /v1/simulations/{id}` | Result | readonly | Phase 5 |
| `POST /v1/reports` | Generate report | scientist | Async → job |
| `GET /v1/reports/{id}` | Retrieve (JSON/PDF) | readonly | Content-negotiated |
| `POST /v1/assessments/ich-m7` | Dual-methodology mutagenicity assessment | scientist | §5.7.1 |
| `GET /v1/assessments/{id}` | Assessment detail | readonly | — |
| `POST /v1/assessments/{id}/review` | Expert review + e-signature | **reviewer + `can_sign` + MFA** | §5.7.1 |

### 5.7.1 ICH M7 assessment

`POST /v1/assessments/ich-m7` runs **both** required methodologies — expert rule-based (structural alerts) and statistical — and returns an assessment with `predictions_concordant` and `requires_expert_review`.

**The endpoint cannot return a final ICH M7 classification when `requires_expert_review` is true.** `final_class` remains `null` until a reviewer submits `POST /{id}/review`. This mirrors the database constraint `ck_review_when_required` (Phase 1 Step 3 §7.4) at the API layer: the guideline requires expert judgement for discordant, out-of-domain or equivocal results, and the API must not permit an automated conclusion in those cases.

`POST /{id}/review` requires re-authentication (MFA challenge) even within an active session — Part 11 §11.200 treats signing as a distinct act from being logged in. The request carries `outcome`, `rationale` (required, non-empty), optional `literature_refs`, and a `signature_meaning`.

---

## 5.8 Operational Endpoints

| Endpoint | Purpose | Auth | Response |
|---|---|---|---|
| `GET /health` | Liveness | none | `200 {status: "ok"}` — no dependency checks |
| `GET /health/ready` | Readiness | none | Checks DB, object storage, queue. `503` if any critical dependency is down |
| `GET /v1/meta` | Build and data versions | authenticated | `{api_version, contract_version, core_db_release, toolchain_id, deployed_at}` |
| `GET /v1/me` | Caller identity | authenticated | User contract (§4.7) |

**Liveness and readiness are separate.** Liveness must not check dependencies — a database blip would otherwise cause the orchestrator to kill healthy application containers, turning a recoverable outage into a cascading one.

`GET /v1/meta` exposes `core_db_release` and `toolchain_id` because a user reproducing results needs to know which data and toolchain version served them (P2).

---

## 5.9 Contract Testing

The specification is enforced, not merely documented:

1. **Schema conformance** — Schemathesis generates cases from the OpenAPI document; every response is validated against its schema in CI.
2. **Envelope invariant** — a property test asserting **no prediction response contains `estimate` without a complete `reliability` block**. This is the API-layer expression of P6.
3. **`must_display` conformance** — the frontend test suite asserts that every field named in `must_display` is rendered in the DOM when the corresponding value is shown. A frontend that renders `estimate.value` without `reliability.applicability_domain` **fails CI**.
4. **Tenant isolation** — automated cross-tenant access attempts must return 404 on every tenant-scoped endpoint.
5. **Error contract** — every error path returns valid `problem+json` with a documented `type`.

Test 3 is the mechanism that makes §1.4 real. Without it, "predictions always show their uncertainty" is a wish; with it, it is a build failure.

---

*End §5.*
