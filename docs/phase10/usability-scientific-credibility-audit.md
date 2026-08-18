# DrugSim — Usability & Scientific Credibility Audit

**Scope**: a fresh read of the current frontend (post v1.0 critical-blocker audit) against the 10 priority areas in the brief — prediction interpretation, uncertainty communication, applicability-domain explanation, molecule input experience, results presentation, terminology, error handling, onboarding, navigation, and accessibility/responsiveness. Findings below are from direct reads of the actual component source and, where noted, from a dedicated background audit of accessibility and responsive behaviour. Not redesign — this audit assumes the current information architecture (result-card structure, collapsible technical panels, endpoint selector) is correct and looks for confusion, missing definitions, and clarity gaps within it.

Much of what this brief asks for was already addressed in the immediately preceding session (conformal p-values now shown with a plain-English definition, applicability-domain verdicts explained per-case with a "why does a simple molecule get flagged" note, and a three-part Prediction/Uncertainty/Applicability-Domain breakdown). This audit does not re-litigate that work — it looks specifically for what's still missing on top of it.

---

## 🟠 IMPORTANT

### 1. No explanation of what SMILES is or how to get one
`MoleculeInput.tsx` labelled its field "Molecule (SMILES)" and offered an example, but never explained what SMILES notation actually is, nor how a user with a molecule in mind but no cheminformatics background would obtain one. For the target audience explicitly named in this brief ("users who may know biomedical science but not cheminformatics"), this is the single most likely point where a real user gets stuck before even reaching a prediction.

### 2. "ADMET" never spelled out
The acronym appears five times across the app — including in the very first sentence a new visitor reads (`HomePage.tsx`'s hero paragraph, and its eyebrow label "Computational ADMET prediction") — and is never once expanded to Absorption, Distribution, Metabolism, Excretion, Toxicity anywhere in the UI.

### 3. "Applicability domain" as a general concept wasn't defined at its own point of use
`ApplicabilityDomainGauge.tsx` explained the *specific* verdict for a given molecule well (in/out of domain, why, the simple-molecule note), but never stated the general concept — what "applicability domain" means at all — before diving into the specific case. The one place that concept was defined in full (`ScientificExplanation.tsx`'s "whether the model has the right experience to guess" section) sits below the gauge in reading order, so a user who stops reading at the gauge (a realistic scenario — it's the more visually prominent element) never encounters the definition.

### 4. No lightweight workflow overview for a first-time user on the prediction page itself
The brief specifically asks for a skippable "1. Enter a molecule → 2. Run a prediction → 3. Review prediction + reliability" overview. Nothing like it existed on `PredictPage.tsx` — a first-time visitor landed directly on the endpoint selector and input form with only a single descriptive sentence above it.

### 5. `EndpointProfileCard`'s three-column result grid had no mobile fallback
Every other multi-column layout in the codebase (`PredictionResults.tsx`, `CompoundProfile.tsx`, `ModelEvidencePanel.tsx`, `EndpointSelector.tsx`) has a responsive breakpoint that collapses to a single column on narrow viewports. `EndpointProfileCard.tsx`'s `grid-cols-3` (Prediction / Uncertainty / Reliability, shown per-endpoint in the multi-endpoint Compound Profile view) was the one exception — at a ~375px viewport, each column would get roughly 110px, cramping values like "p=0.123" and rating text.

### 6. `--color-caution` sat right at the WCAG AA contrast floor, with no margin
Measured 4.54:1 against the page background — technically passing AA's 4.5:1 minimum for normal text, but the only color in the design system without real margin (every other text color clears 5.9:1+). Used for medium-severity warning text and "Moderate" reliability ratings.

---

## 🟡 IMPROVEMENT

### 7. The frontend only ever offers SMILES input, though the backend contract supports more
`frontend/src/api/types.ts` (and the backend's `schemas.py`) support three structure formats — `smiles`, `molblock`, `inchi` — but `MoleculeInput.tsx`/`PredictPage.tsx` hardcode `"smiles"` and never expose the other two. This is **not** a false claim (the UI only ever says "Accepted format: SMILES," never claims broader support, satisfying the brief's explicit "do not claim support for formats the backend does not actually support"), and adding format-switching UI risks the brief's own "do not make the interface unnecessarily complicated" instruction for a population that is, per the brief, more likely to be confused by more input modes than helped by them. Deferred, not fixed this pass.

### 8. Automated accessibility coverage is strong but not exhaustive
`e2e/accessibility.spec.ts` runs a real axe-core WCAG 2.1 A/AA scan across every static page and every dynamic state (populated results, expanded technical panel, error state, multi-endpoint profile) — genuinely thorough for what it covers. It does not, however, run a scripted keyboard-only traversal (Tab-order verification) or simulate actual assistive-technology announcement behaviour; those gaps are about test *coverage*, not a confirmed defect (the underlying markup was independently confirmed to use only real semantic interactive elements with a global, unsuppressed focus-visible style — see the accessibility sweep below). Worth a future addition, not a confirmed bug to fix now.

### 9. Focus styling is uniform/global rather than component-tailored
A global `:focus-visible { outline: 2px solid var(--color-signal); outline-offset: 2px; }` rule (`index.css:49-52`) is applied everywhere and never suppressed — this is a correct, working baseline — but almost no component adds its own tailored focus treatment on top of it. Not a defect; noted only because a manual visual check (not performed here) would be worth doing to confirm the teal outline reads clearly against every button's own background (e.g. the selected endpoint button's dark fill).

## 🟢 POLISH

None identified. Visual polish was explicitly out of scope for this pass and was not reviewed.

---

## Independent accessibility & responsive sweep (supporting evidence for the above)

A dedicated pass (separate from the direct component reads above) checked eight specific areas against the actual rendered markup:

| Area | Verdict |
|---|---|
| Keyboard navigation (every interactive control is a real `<button>`/`<a>`/`<input>`, none is a `<div onClick>`) | PASS |
| Visible focus states (global, unsuppressed `:focus-visible` rule) | PASS |
| Form labels (both real inputs in the app have a proper `<label htmlFor>`) | PASS |
| Color-only signaling (every status color is paired with text, never color alone) | PASS |
| Screen-reader-friendly result cards (`role="status"`/`role="alert"`/`aria-label`/`aria-labelledby` used consistently) | PASS |
| Responsive layout | CONCERN — item 5 above (fixed) |
| Existing a11y test coverage | Strong axe-core coverage; see item 8 above |
| Contrast | CONCERN — item 6 above (fixed) |

No location was found anywhere in the codebase where color is the sole signal for a status, and no interactive element was found that would be unreachable by keyboard.
