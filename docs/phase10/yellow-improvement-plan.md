# DrugSim — 🟡 Product Improvement Plan

Scope: worthwhile, non-blocking improvements on top of an already-functional, already-audited (🔴 blocker audit, 🟠 usability/credibility pass) system. Every candidate below was checked against the existing architecture — `drugsim-predict-api` (stateless-per-request except its own SQLite audit log, no multi-tenant identity, single shared demo key) and the static-hosted frontend — before being ranked, so nothing here assumes infrastructure that doesn't exist.

**Governing constraint that shaped every ranking below**: the backend's `PredictionResponse` contract (`schemas.py`/`types.ts`) does not include physicochemical descriptors (molecular weight, LogP, etc.) — only `canonical_smiles`, `isomeric_smiles`, `standardized_smiles`, `inchikey_full`, `molecular_formula`. Any feature that would need those values either requires a backend schema change (real, if small, architectural risk — deferred, documented below) or must be built from what the API already returns.

The backend also has no per-user identity — the shared API key is explicitly not real multi-tenant auth (documented since Phase 8). Any "history" or "compare" feature that stored data server-side would either mix every visitor's compounds together or need new auth infrastructure — both are out of scope ("do not introduce major architectural changes"). Every stateful feature below is therefore **client-side only** (the browser's own `localStorage`), which sidesteps that problem entirely: it's private to the user's own device by construction, needs zero backend changes, and trivially satisfies section 5's "do not store confidential structures unnecessarily... do not use private user compounds for model training" (nothing is sent or stored anywhere except the user's own browser).

---

## HIGH VALUE (implementing)

1. **Prediction history (client-side)** — save each completed prediction to `localStorage` (compound name if given, structure, endpoint, timestamp, predicted label, reliability rating, model version) with a page to review and clear it. Directly serves workflow efficiency and researcher convenience; zero backend risk; privacy-safe by construction (never leaves the browser).
2. **Results export (JSON + CSV)** — a "Download result" action on the results view, exporting exactly what's already on screen (prediction, uncertainty, applicability domain, reliability, model version, timestamp, the scientific disclaimer) — nothing invented, nothing requested from the backend that isn't already in the response object in memory.
3. **Curated example compounds** — expand from the single existing aspirin example to a small, labelled set demonstrating different real scenarios (in-domain, out-of-domain, borderline where reachable). Every example is verified against the live backend before being shipped, and each is explicitly labelled as an example, per the brief's own requirement not to make unsupported claims about them.
4. **Visible changelog / "What's new"** — a simple page summarizing what changed across the recent hardening and usability passes. Directly requested by the brief (final-report item 9) and serves Trust & Transparency (section 18) — users and reviewers can see the product is actively maintained without needing to read commit history.

## MEDIUM VALUE (implementing if the above lands cleanly)

5. **Compound comparison (2 compounds, from history)** — reuse the localStorage history to let a user compare two of their own previously analysed compounds side by side: endpoint-by-endpoint prediction, uncertainty, applicability domain. Explicitly no combined "better drug" score (the brief and this project's own Phase 9/10 rules already rule that out for a single compound's endpoints — it applies at least as strongly across compounds). Only attempted after 1–4 are solid, since it depends on the history feature existing first.

## MEDIUM VALUE (documented, deferred)

6. **Physicochemical properties in the Compound Profile** (MW, LogP, TPSA, etc.) — genuinely useful, but the backend response doesn't return them today. Adding them is a real (if small) backend schema change and a live redeploy, which is explicitly out of scope for a frontend-focused improvement pass whose own rule is "do not introduce major architectural changes." Documented here rather than implemented, per section 20's own instruction for exactly this situation.
7. **Per-endpoint "what/why/means/limitations" exploration page** — a real gap, but a smaller one than it first appears: `lib/endpointCopy.ts` already carries a per-endpoint biological description, and `ScientificExplanation.tsx`/`MethodologyPage.tsx` already cover the general "what does uncertainty/applicability domain mean" material from the prior usability pass. A dedicated exploration page would mostly be reorganizing information that already exists elsewhere into one more place to maintain. Deferred as medium-term polish rather than a new information gap.

## LOW VALUE / explicitly out of scope

- **Server-side prediction history / sharing / feedback backend** — would need new authenticated, per-user backend infrastructure this deployment does not have and this pass is not authorized to build ("do not introduce major architectural changes," "do not introduce unnecessary databases"). A `mailto:` feedback link (reusing the existing contact address) is trivial enough to include as a low-cost addition; a real feedback *system* is not.
- **New charts/visualizations beyond the existing applicability-domain gauge** — the existing gauge, p-value display, and reliability rating (from the prior two passes) already communicate the real signal without fabricating certainty. Nothing identified in this pass would add genuine new information rather than a different picture of the same numbers — skipped rather than adding decoration.
- **Performance infrastructure (caching layers, lazy-loading frameworks)** — measured first (see Performance section of the final report): the production bundle is 145KB gzipped, well within normal budgets for this kind of app, and the live API already responds sub-second. No measured problem exists to justify new infrastructure, consistent with "do NOT introduce complex infrastructure unless measurements demonstrate a need."
- **Visual redesign** — explicitly against this brief's own final rule ("improve the interface only after functional improvements... avoid excessive gradients/animations/decorative elements"). Not attempted.

---

## Implementation order

1. Prediction history (client-side, `localStorage`) + its review/clear page.
2. Results export (JSON/CSV), built on top of the same prediction data.
3. Curated example compounds (independent of 1–2, can run in parallel conceptually).
4. Changelog page.
5. Compound comparison (only if 1–4 land cleanly and tests stay green).

Every change is additive to the existing UI (new page, new button, expanded example list) — nothing in the existing prediction pipeline, API contract, or validated model output is touched.
