# Phase 6 — User Interface & Product Experience

## Status: complete

Phase 6 builds the first user-facing DrugSim application on top of the Phase 5
prediction engine. It does not modify the validated `herg_inhibition` model,
does not add ADMET endpoints, and does not change prediction methodology. All
scientific values shown in the UI are read directly from the Phase 5 API
response.

## 1. What was built

A React + TypeScript single-page application (`frontend/`) with four routes:

| Route | Page | Purpose |
|---|---|---|
| `/` | `HomePage` | Value proposition, framed as computational estimation, not discovery or diagnosis. Links to the prediction workspace and methodology. |
| `/predict` | `PredictPage` | The core workspace: molecule input, validation, prediction, and results. |
| `/methodology` | `MethodologyPage` | Data → Standardisation → Dataset → Model → Applicability domain → Uncertainty → Prediction pipeline summary, linking to the Phase 3–5 reports rather than duplicating them. |
| `/limitations` | `LimitationsPage` | Explicit, non-buried disclaimer list (also linked from every page footer). |

Stack: Vite, React 19, TypeScript, React Router 7, Tailwind CSS v4, and
`smiles-drawer` for client-side 2D structure depiction. Vitest + React
Testing Library for component tests, Playwright for the end-to-end test.

## 2. Core user flow

Enter molecule (SMILES) → Validate → see the standardised structure and
canonical representation → Predict → see the result with uncertainty,
applicability domain, and reliability always visible → optionally expand
"Model & evidence" or read "What does this mean?" → optionally read the
methodology or limitations pages.

The Phase 5 API has a single `POST /predict` endpoint — there is no separate
validation endpoint. "Validate" and "Predict" both call `/predict`; the
"Validate" step shows the returned molecule preview without yet foregrounding
the prediction result, giving the two-step interaction the spec asks for
without inventing a backend capability that does not exist. This is
documented here rather than silently worked around.

## 3. API integration

`frontend/src/api/client.ts` is a thin fetch wrapper: `predict()`,
`getPrediction()`, `getModel()`, `checkHealth()`. It contains no prediction
logic — every displayed value originates from the JSON the backend returns.
Errors are classified into `validation | not_found | server_error |
unavailable | network | timeout` from HTTP status and fetch failures, so the
UI can render an honest, specific failure state instead of guessing.

`frontend/src/api/types.ts` mirrors `src/drugsim_predict/schemas.py`
field-for-field with no independent logic, so the frontend cannot silently
drift from the Phase 5 contract.

**Backend change**: `src/drugsim_predict/api.py` gained CORS middleware
(`CORSMiddleware`, origins from `DRUGSIM_CORS_ORIGINS` env var, defaulting to
the local Vite dev origins). This is the only backend change in Phase 6 — it
is infrastructure glue required for any browser client to call the API
directly, not a change to prediction methodology. All 21 existing
`test_predict_api.py` tests still pass with it in place.

In local development, `vite.config.ts` also proxies `/api/*` to
`localhost:8000`, so CORS is not exercised in that path — it matters for
direct/production access.

Verified against the real running Phase 5 service (not just mocks): a live
`POST /predict` through the dev proxy returns the exact shape
`api/types.ts` expects, including a real `out_of_domain` verdict and its
associated warnings.

## 4. UI components (`frontend/src/components/`)

- `MoleculeInput` — SMILES textarea, example-molecule fill, clear, Validate/Predict buttons with busy and disabled states.
- `MoleculePreview` — input-side view: 2D depiction, canonical SMILES, molecular formula, InChIKey. Explicitly labelled "Input information" and contains no predicted values.
- `MoleculeStructure` — renders a 2D depiction via `smiles-drawer`, which only computes layout coordinates, never properties or predictions; falls back to a text note if rendering fails, with the canonical SMILES remaining authoritative.
- `PredictionResults` — the primary dashboard. Labelled "Predicted information"; lays out the headline prediction, warnings, uncertainty, reliability, applicability domain, scientific explanation, and model evidence with equal visual weight — uncertainty and applicability domain are never secondary to the headline label.
- `UncertaintyPanel` — shows the conformal prediction set and `nominal_confidence` explicitly as a population-level coverage guarantee, never rephrased as a per-prediction correctness probability.
- `ApplicabilityDomainGauge` — the product's signature visual: a "known chemistry → novel chemistry" gradient bar with the molecule marked at its real `max_tanimoto_to_training` position, captioned to make clear this reflects evidence, not biological correctness.
- `ReliabilityBadge` — see §5 below on the one derived (non-fabricated) value in the UI.
- `ScientificExplanation` — static "What does this mean?" copy, explicitly framed as not a clinical diagnosis.
- `ModelEvidencePanel` — collapsible model/version/dataset/training-set-size/AD-method/uncertainty-method detail, linking to `/methodology`.
- `WarningsList` — renders real backend `warnings[]` entries by severity.
- `ErrorPanel` — one distinct, honest message per `ApiError` kind; never renders a fabricated prediction on failure.

## 5. The one derived value: Reliability rating

The Phase 5 API has no `reliability_rating` field, but spec section 6
explicitly calls for a High/Moderate/Low reliability line. Rather than
inventing a fictional backend field or dropping the requirement,
`frontend/src/lib/reliability.ts` derives a label from two real fields
already in the response — `applicability_domain.verdict` and
`conformal.is_singleton` — with a fixed decision table (out-of-domain or
undeterminable → Low; borderline → Moderate; in-domain non-singleton →
Moderate; in-domain singleton → High). This is presentational summarisation
of real data, not a new scientific calculation, and every place it is shown
(`ReliabilityBadge`) carries a visible disclosure: "Summarised from the
applicability-domain verdict and prediction-set width above — not a separate
backend measurement."

## 6. Accessibility

- All interactive controls are real `<button>`/`<label>`/`<textarea>` elements with associated labels (`useId`-generated `htmlFor`/`id` pairs).
- `ErrorPanel` uses `role="alert"`.
- `ModelEvidencePanel`'s toggle exposes `aria-expanded`/`aria-controls`.
- Structure depictions and the applicability-domain gauge are `role="img"` with a descriptive `aria-label`/computed alt text, not decorative.
- Layout includes a "Skip to content" link and visible focus rings (`:focus-visible` styled with the accent colour) on every focusable element.
- `prefers-reduced-motion` is respected globally.
- Colour is never the only signal: verdict/severity/reliability states pair colour with text labels.

## 7. Tests

**Component/unit tests** (Vitest + React Testing Library, `npm run test` from `frontend/`) — 34 tests across 9 files, all passing:

- `MoleculeInput` — field labelling, disabled/enabled states, example fill, clear, busy state.
- `MoleculeStructure` — accessible image rendering, custom labels.
- `UncertaintyPanel` — singleton/non-singleton copy, and that a per-prediction "confidence" claim is never made.
- `ApplicabilityDomainGauge` — verdict labelling for in-domain and out-of-domain, real rationale text, accessible image role, and the "not biological correctness" disclaimer.
- `ReliabilityBadge` — derived rating for in-domain/singleton and out-of-domain cases, disclosure text.
- `ModelEvidencePanel` — collapsed-by-default, `aria-expanded` toggling, real provenance values shown.
- `WarningsList` — empty case, message rendering.
- `ErrorPanel` — `role="alert"`, distinct copy per error kind, retry callback.
- `PredictPage` — prediction request payload, loading state, molecule preview after validation, full results rendering (uncertainty/AD/reliability headings present), and honest error states for both an invalid-molecule (422) and an unreachable-API (network) failure, asserting no fabricated result appears.

**End-to-end test** (Playwright, `npm run test:e2e` from `frontend/`) — 2 tests, both passing:

- Full flow: home → "Enter a molecule" → fill SMILES → Validate → see molecule preview → Predict → see the prediction, uncertainty, applicability domain, reliability, and training-set size. The `/predict` network call is stubbed with a response shaped exactly like a real Phase 5 payload, so the test is deterministic in CI while still exercising real routing, state, and rendering code.
- API-failure flow: a stubbed 500 response produces a visible `role="alert"` and never renders a prediction result.

## 8. Known limitations

- "Validate" and "Predict" both call the same `/predict` endpoint (§2) — there is no lighter-weight validation-only backend call, so validating a molecule already runs the full model.
- The reliability rating is a frontend-derived summary of two backend fields, not a backend-computed value (§5) — always disclosed, never presented as raw model output.
- No shareable "view a past prediction by ID" page was built, even though `GET /predict/{id}` exists in the client — it wasn't required by the spec's core flow, so `ApiError`'s `not_found` handling exists in `ErrorPanel` but is currently unexercised by any page.
- E2E coverage stubs the network boundary rather than running against a live model server in CI; it was additionally verified once by hand against the real running Phase 5 service (§3) but that is not part of the automated suite.
- No dark-mode, print stylesheet, or i18n — out of scope for this phase.

## 9. Explicitly deferred (per spec section 18 — not built)

User accounts, payments/subscriptions, advertising, social features, a
molecule marketplace, additional ADMET endpoints beyond hERG, an AI chatbot,
automated drug design, and public model training. None of these were
implemented, referenced, or scaffolded.

## 10. Phase 7 recommendation

The product experience is now complete for the single validated endpoint.
Natural next steps, in rough priority order:
1. Deployment hardening — production CORS origin configuration, static asset hosting, and a real health/readiness check wired into the served frontend.
2. A "view saved prediction" page using the already-built `getPrediction(id)` client method and `PredictionResults` component, giving predictions a shareable URL.
3. If a second ADMET endpoint is validated in a future phase, extend `PredictionResults` and `ModelEvidencePanel` to be endpoint-aware rather than hERG-specific, without touching prediction logic.
4. Usability testing with actual chemists/researchers on the applicability-domain gauge and reliability rating, since both are novel UI elements this phase introduced.

Phase 6 is complete. Do not start Phase 7.
