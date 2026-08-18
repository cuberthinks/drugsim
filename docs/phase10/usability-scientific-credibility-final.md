# DrugSim — Usability & Scientific Credibility Improvement Pass: Final Report

This pass follows the immediately preceding v1.0 critical-blocker audit. Its scope was different and narrower: not "is DrugSim scientifically correct and secure" (already answered) but "can someone with a biomedical background but no cheminformatics experience actually use it and understand what they're looking at, without oversimplifying the science." No model was retrained, no validated calculation was changed, no new endpoint was added, and no scientifically important information was removed — every change below either adds a missing explanation or fixes a genuine clarity/accessibility gap in existing information.

---

## Problems identified

See `docs/phase10/usability-scientific-credibility-audit.md` for the full findings with evidence. Six 🟠 IMPORTANT gaps were found and fixed; three 🟡 IMPROVEMENT items were found and consciously deferred (with reasoning, not neglect). No 🟢 polish items were identified — visual polish was out of scope for this pass.

---

## Changes made

### Usability

- **`MoleculeInput.tsx`**: added a collapsible "Don't know what SMILES is?" explanation — a plain-language definition, one worked example, and a concrete path to obtaining a real SMILES string (search the compound on PubChem, copy its SMILES). Also reworded the field label from "Molecule (SMILES)" to "Enter a chemical structure — paste a SMILES string," matching the brief's suggested structure, and tightened "Supported format" to "Accepted format" (the format is not merely supported alongside others — it is the only one accepted).
- **`PredictPage.tsx`**: added a lightweight, always-visible, non-interruptive three-step guide ("Enter a molecule / Run a prediction / Review prediction + reliability") above the input form. It is not a modal, has no dismiss button, and blocks nothing — a returning user simply scrolls past it, satisfying the brief's "skippable" requirement without adding interaction overhead.

### Scientific communication

- **`HomePage.tsx`**: spelled out ADMET (Absorption, Distribution, Metabolism, Excretion, Toxicity) at its first, most prominent use — the hero paragraph every visitor reads first.
- **`ApplicabilityDomainGauge.tsx`**: added a one-line, self-contained definition of what applicability domain measures ("How closely this molecule resembles the chemistry the model was actually trained on — not whether the prediction itself is correct"), directly under the heading, so the concept is defined at its own point of use rather than requiring the reader to find it in a different section further down the page.

### Accessibility

- **`index.css`**: darkened `--color-caution` from `#a6631b` (4.54:1 contrast against the page background — technically passing WCAG AA's 4.5:1 floor but with no real margin, the one color in the palette without one) to `#875014` (6.3:1), same amber hue, comfortable margin above both AA and closer to AAA.
- **`EndpointProfileCard.tsx`**: added a responsive breakpoint (`grid-cols-1 sm:grid-cols-3`) to the Prediction/Uncertainty/Reliability result grid, matching every other multi-column layout in the app, so it doesn't cram onto three narrow columns on a mobile viewport.

---

## Usability improvements

The two most consequential fixes are the SMILES help block and the applicability-domain definition — both were genuine points where the target audience (biomedical background, no cheminformatics experience) would plausibly have stalled: one before they could even attempt a prediction, one after receiving a result they couldn't fully interpret without hunting for an explanation elsewhere on the page.

## Scientific communication improvements

ADMET being spelled out closes the last unexplained piece of core terminology on the homepage — every other term flagged by the brief (hERG, calibration-adjacent concepts, uncertainty, applicability domain) already had either an inline explanation or a dedicated methodology page reference from the prior session's work; ADMET was the one gap.

## Accessibility improvements

Both fixes (contrast margin, responsive grid) came from direct, evidence-based findings, not speculative hardening — the contrast issue was a measured 4.54:1 (real WCAG-floor risk), and the grid issue was a genuine inconsistency against every other layout pattern already established in the codebase.

---

## User-testing findings

No external users were available in this environment, so — consistent with this project's own established precedent for exactly this situation (Phase 7's "disclosed heuristic walkthrough" substitute) — I performed the brief's own seven-question walkthrough myself, reading only the actual rendered user-facing copy as it exists after the fixes above, from the stated persona (biomedical background, no cheminformatics experience). This is explicitly a substitute for real user testing, not a replacement for it, and is reported as such.

| Question | Where the answer comes from | Result |
|---|---|---|
| 1. What does DrugSim do? | Homepage hero paragraph (now with ADMET spelled out) | Clear — computational estimates of specific ADMET endpoints from a molecule's structure, explicitly not clinical validation |
| 2. Enter a molecule | `MoleculeInput`'s label, example, and new "Don't know what SMILES is?" help | Previously a likely stumbling point for this persona; now has a concrete path (PubChem lookup) |
| 3. Run a prediction | Validate → Predict buttons, Predict disabled with a tooltip until validated | Already clear before this pass |
| 4. What the result means | `PredictionResults`' labelled prediction + `ScientificExplanation`'s "The Prediction" section | Clear |
| 5. What uncertainty means | `UncertaintyPanel`'s p-values + "What is a p-value here?" disclosure (added in the prior session) | Clear |
| 6. Applicability domain | `ApplicabilityDomainGauge`'s new self-contained definition + verdict-specific explanation + simple-molecule note | Previously required reading a different section of the page first; now self-contained |
| 7. Does this prove a drug is safe? | Repeated, consistent disclaimers across the hero, `ScientificExplanation`, Limitations, and Terms pages | Clear and consistent — confirmed by the full 43-file copy audit in the prior session |

**Conclusion of the walkthrough**: after this pass's fixes, a biomedical student with no cheminformatics background should be able to complete the full workflow and correctly answer all seven questions without external explanation. The two points where this walkthrough would plausibly have failed before this pass (questions 2 and 6) are exactly the two most substantial fixes made.

---

## Remaining issues

### 🟡 IMPROVEMENT
- Frontend only exposes SMILES input, though the backend contract supports `molblock`/`inchi` too. Not a false claim (the UI never claims broader support) and deliberately deferred — adding format-switching risks over-complicating the interface for a persona better served by one simple, well-explained path than three options.
- `accessibility.spec.ts`'s axe-core coverage is strong (every page, every dynamic state) but doesn't include a scripted keyboard-only traversal or real assistive-technology simulation. Worth adding in a future pass; not a confirmed defect today.
- Focus styling relies on one global, unsuppressed rule rather than per-component tailoring. Confirmed working as a baseline; a manual visual check of the outline against every button background was not performed.

### 🟢 POLISH
None identified this pass.

---

## Testing

Ran after every change in this pass:

- Backend (predict service + security + golden/scientific-regression suite): **172/172 pass**, unchanged from before this pass — confirms no scientific result changed unintentionally, per the brief's explicit requirement.
- Frontend unit (`vitest`): **78/78 pass** (74 before this pass + 4 new regression tests added this pass).
- Typecheck (`tsc --noEmit`): clean.
- Production build (`vite build`): clean.
- Lint (`oxlint`) on every changed file: clean.
- E2E (`playwright`, includes the full WCAG 2.1 AA axe-core scan across every page and dynamic state, plus mobile no-horizontal-overflow checks): **32/32 pass** — confirms the contrast and responsive-grid fixes didn't introduce new accessibility violations, and nothing else regressed.

**New regression tests added this pass** (all confirmed to exercise the actual fix, not just cosmetically pass):
- `MoleculeInput.test.tsx`: explains what SMILES is and links to PubChem; only claims the format DrugSim actually accepts.
- `PredictPage.test.tsx`: the three-step "How this works" guide is present and scoped correctly (avoiding a false match against the header's own descriptive sentence).
- `ApplicabilityDomainGauge.test.tsx`: applicability domain is defined at its own point of use, not only elsewhere on the page.

Two pre-existing test suites (`MoleculeInput.test.tsx`, `PredictPage.test.tsx`, and all four Playwright E2E spec files) needed a mechanical update to their label-text query after the intentional field-label reword ("Molecule (SMILES)" → "Enter a chemical structure — paste a SMILES string") — this was a query-string update to match the new (better) wording, not a weakening of what any test actually verifies. No test was deleted, and no test's assertion was loosened.

---

## Final audit

Re-asking this document's own framing questions against the current state:

- **Can a biomedical student understand DrugSim without someone explaining it?** Yes, per the heuristic walkthrough above — the homepage now self-contains its own key terminology (ADMET spelled out), and the workflow overview orients a first-time visitor before they touch the input form.
- **Can they understand what the prediction means?** Yes — unchanged from the prior session's work, confirmed still intact.
- **Can they understand whether the prediction is reliable?** Yes — the p-value disclosure and reliability rating (from the prior session) remain, and applicability domain is now self-explanatory at first contact.
- **Can they understand applicability domain?** Yes — this was the pass's central fix.
- **Can they distinguish a computational prediction from clinical evidence?** Yes — reconfirmed via the full prior-session copy audit; this pass changed nothing that would weaken that distinction and, if anything, strengthened it (the ADMET/validated wording tightened in the immediately preceding pass).
- **Can they use the core workflow without confusion?** Yes, with the SMILES-help and onboarding additions closing the two gaps that would most plausibly have stopped this specific persona.
