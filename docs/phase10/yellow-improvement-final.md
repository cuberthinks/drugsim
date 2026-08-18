# DrugSim — 🟡 Product Improvement Pass: Final Report

Follows `docs/phase10/yellow-improvement-plan.md`. All four HIGH VALUE items and one MEDIUM VALUE item were implemented; nothing else was attempted, per the plan's own prioritization and this pass's rule to prefer one useful feature over ten unnecessary ones. Every feature is additive and frontend-only — no backend file was touched, no API contract changed, no model or preprocessing code changed.

---

# Improvements Implemented

1. **Prediction history** (`lib/history.ts`, `pages/HistoryPage.tsx`) — every completed prediction is saved to the browser's own `localStorage`: compound name, structure, endpoint, prediction, reliability rating, applicability-domain verdict, and model version. A `/history` page lists, removes, and clears entries. Capped at 50 entries. Never sent to the backend — the backend has no idea this feature exists.
2. **Results export** (`lib/export.ts`) — "Download JSON" / "Download CSV" buttons on a completed result, exporting exactly the fields already on screen (prediction, uncertainty, applicability domain, model version, timestamp) plus the scientific disclaimer, per the brief's explicit list. Both formats are round-trip-verified in tests; the CSV encoder properly quotes fields containing commas (the disclaimer text itself does).
3. **Curated example compounds** (`lib/exampleCompounds.ts`) — expanded from one hardcoded aspirin example to four, each **verified against the live hERG endpoint before being written**, not guessed: aspirin and paracetamol (common drugs that fall outside the model's training chemistry despite being extremely familiar), terfenadine (a real blocker confidently within the model's training chemistry), and dofetilide (a real antiarrhythmic showing a correct-looking label can still carry real, disclosed uncertainty). Each example's one-line note states only what was actually observed.
4. **Changelog** (`pages/ChangelogPage.tsx`) — a `/changelog` page (linked from the footer as "What's new") summarizing recent changes in plain language, explicitly separating product/UX changes from anything touching validated science, and pointing to the methodology page for actual endpoint-validation history rather than claiming validation changes here.
5. **Compound comparison** (`pages/ComparePage.tsx`, MEDIUM value, implemented since 1–4 landed cleanly) — compares two of the user's own history entries **restricted to the same endpoint** (scientifically compatible information only, per the brief), side by side: prediction, reliability, applicability domain, model version. No combined "better drug" score — each compound's own real numbers, never merged.

---

# Improvements Deferred

- **Physicochemical properties in the Compound Profile** (MW, LogP, TPSA) — the backend response doesn't return them today; adding them would be a real backend schema change and redeploy, out of scope for a frontend-focused pass per its own "do not introduce major architectural changes" rule. Documented in the plan rather than implemented.
- **Dedicated per-endpoint exploration page** — judged, after review, to be mostly reorganizing information (`endpointCopy.ts` descriptions, `ScientificExplanation.tsx`, `MethodologyPage.tsx`) that already exists elsewhere, rather than closing a real gap. Deferred as medium-term polish.
- **Server-side history, sharing, or a feedback backend** — would require new authenticated, per-user backend infrastructure this deployment doesn't have and this pass isn't authorized to build. The client-side history/compare features above deliver the same user-facing value without that infrastructure.
- **New chart types beyond the existing applicability-domain gauge** — nothing identified would add genuine new information rather than a different picture of numbers already shown.
- **Performance infrastructure** — measured, not needed; see Performance section below.

---

# Scientific Safety

No backend file was modified in this pass. Confirmed directly:
- **Prediction results unchanged**: 172/172 backend tests pass, identical to before this pass.
- **Model versions unchanged**: `src/drugsim_predict/model_registry.py`, `models/registry/*.json`, and the model artifacts themselves were not touched.
- **Preprocessing unchanged**: `src/drugsim_chem`, `src/drugsim_features` were not touched.
- **API contracts unchanged**: `src/drugsim_predict/schemas.py`, `frontend/src/api/types.ts`, and `frontend/src/api/client.ts` were not touched — every new feature reads fields the API already returns.
- **Scientific regression suite unchanged**: `tests/golden/` — 53/53 pass, identical to before.
- **New scientific content added (the example compounds) was verified, not invented**: every claim in `exampleCompounds.ts` about what a compound demonstrates was checked against a real, live `/predict` call before being written into the file.

---

# Performance

Production bundle size, measured before and after this pass (`vite build`, gzip):

| | Before | After | Change |
|---|---|---|---|
| JS | 145.95 kB | 149.64 kB | +3.69 kB |

The increase is proportionate to what was added (3 new pages, a history module, an export module) and stays well within normal budgets for an app of this kind — no lazy-loading, caching layer, or other performance infrastructure was judged necessary. Per the brief's own rule ("do NOT introduce complex infrastructure unless measurements demonstrate a need"), none was added. Live API response times were not re-measured this pass since no backend code changed.

---

# Testing

- Frontend unit (`vitest`): **107/107 pass** (78 before this pass + 29 new: history module, export module, and the new/updated History, Compare, and MoleculeInput tests).
- Typecheck (`tsc --noEmit`): clean.
- Production build (`vite build`): clean.
- Lint (`oxlint`) on every new/changed file: clean.
- E2E (`playwright`, 38 tests): **38/38 pass**, including the full WCAG 2.1 AA axe-core scan and mobile no-overflow check extended to all three new pages (`/history`, `/compare`, `/changelog`).
- Backend (predict service + security + scientific-regression suite): **172/172 pass**, unchanged from before this pass, confirming release safety per the section above.

**New regression tests added this pass**: 9 in `lib/history.test.ts` (save/load/dedupe/cap/remove/clear, and that it never throws if storage is unavailable or corrupted), 7 in `lib/export.test.ts` (every exported field traces to a real API field, disclaimer always present, valid JSON, correctly-quoted CSV, download triggers the right browser calls), 6 in `pages/HistoryPage.test.tsx`, 3 in `pages/ComparePage.test.tsx`, 2 updated + 2 new in `MoleculeInput.test.tsx` (the curated example set), 2 new in `PredictPage.test.tsx` (history save on completion, export buttons present). One pre-existing E2E test needed a scoping fix after the new example buttons introduced a legitimate second element containing the word "Aspirin" — fixed by scoping the query to the specific result region, not by loosening what it checks.

---

# Remaining Improvements

## 🟡 Medium-term
- Exposing physicochemical properties (MW, LogP, TPSA) once/if the backend response is extended to include them.
- A dedicated per-endpoint "what/why/means/limitations" exploration page, if user feedback (via the changelog's implicit invitation to explore, or future direct feedback) suggests the information scattered across `endpointCopy.ts`/`ScientificExplanation.tsx`/`MethodologyPage.tsx` isn't being found.
- A real feedback mechanism (currently just the existing `mailto:` contact address on the About page) — would need backend infrastructure to collect and triage.

## 🟢 Optional polish
- Visual refinement of the new History/Compare/Changelog pages once real usage patterns are known — deliberately built plain and functional first, per this pass's own rule to prefer functional improvement over decoration.
- A "recently used endpoints" or saved-analyses shortcut on the homepage, if history usage turns out to be common enough to warrant surfacing it earlier than the nav link.
