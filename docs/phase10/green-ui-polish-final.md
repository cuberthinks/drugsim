# DrugSim — 🟢 Final UI/UX Polish Pass

Scope: visual and interaction polish only, on top of an already-functional, already-audited system (🔴 blocker audit, 🟠 usability pass, 🟡 product-improvement pass). Nothing in the model, preprocessing, API contract, or database was touched. This document is honest about what was actually broken versus what was already fine — a large fraction of the checklist items in the brief were already well-executed from the prior passes, since those were built with these same principles in mind throughout. This pass looked for genuine gaps rather than inventing changes to justify the exercise.

---

# Visual Improvements

**Favicon was completely missing in practice.** An SVG file existed at `public/favicon.svg`, but `index.html` never linked it (`grep` across the whole frontend found zero references) — browsers were falling back to a generic/blank tab icon. Worse, the pre-existing file itself was off-brand: a bright purple gradient blob with heavy glow effects, directly contradicting this app's own established design principle (`index.css`'s own header comment: "not saturated/flashy... a scientific evidence gauge, not a pass/fail alarm"). Replaced it with a minimal mark built from DrugSim's actual design tokens (`--color-ink`, `--color-signal`, `--color-paper`) — two connected circles suggesting a molecular bond, simple enough to stay legible at 16px — and wired it into `index.html` with a proper `<link rel="icon">`.

**Metadata was incomplete.** `index.html` had a title and meta description (already good — no overclaiming, consistent with the rest of the app's copy) but no Open Graph tags and no theme-color. Added `og:site_name`, `og:type`, `og:title`, `og:description`, and `theme-color` (matching `--color-ink`, so mobile browser chrome tints consistently with the app rather than defaulting to white).

**Removed dead weight.** `public/icons.svg` was a Bluesky social-icon sprite sheet, entirely unrelated to DrugSim, with zero references anywhere in the codebase — confirmed via a full-repo grep before deleting. Pure repo hygiene; it cost nothing at runtime (Vite only serves `public/` assets that are actually linked), but there's no reason for it to exist.

---

# UX Polish

**Hover/focus transitions were inconsistent.** Of 17 files with `hover:` states, only 3 had any `transition-` class at all — most buttons, links, and inputs across the app snapped instantly on hover rather than animating. Added a single global CSS rule (`a, input, textarea, select`) rather than hand-editing dozens of individual className strings — automatically consistent everywhere, present and future, with no risk of missing an element. See the Accessibility section below for why `<button>` was deliberately excluded from this rule.

**Audited, and confirmed correct rather than changed:** card padding varies between `p-5` and `p-6` across the app. Traced every instance — this is a real, consistent, already-intentional two-tier system (`p-6` for standalone/singular cards, `p-5` for repeated list/grid items like history entries and per-endpoint result cards), not accidental drift. Left as-is; this is what "avoid excessive variation" already looks like when done correctly, not a violation of it.

---

# Accessibility Improvements

**Caught a real regression from this pass's own first attempt, and reverted it properly rather than accepting the risk.** The first version of the transition rule above included `<button>`. This app has at least one button that fully inverts its color pairing between states — the Compound Profile view-mode toggle swaps `border-ink bg-ink text-paper` (active) for `border-line bg-white text-ink` (inactive) when `aria-pressed` flips. Animating that swap over 150ms necessarily passes through a genuinely low-contrast intermediate frame partway through the interpolation — not a false positive: the existing `e2e/accessibility.spec.ts` axe-core WCAG scan caught it as a real `color-contrast` violation (4.06:1 measured mid-transition, against the 4.5:1 AA floor). Rather than accept that risk or try to suppress the finding, `<button>` was removed from the rule entirely — this app's toggle buttons keep their existing instant hover feedback. Per the brief's own rule ("do not sacrifice accessibility for aesthetics"), this was the correct call, not a compromise.

**Re-verified, not re-built:** reduced-motion support (`index.css`'s existing `prefers-reduced-motion` block, forcing all transitions/animations to 0.001ms) automatically covers the new transition rule — nothing additional was needed. Every other accessibility property from the prior usability pass (keyboard navigation, semantic HTML, form labels, color-never-alone signaling, contrast) was re-verified clean via the full E2E accessibility suite after this pass's changes, not assumed.

---

# Responsive Improvements

None newly needed. The prior product-improvement and usability passes already brought every page — including the three newest (`/history`, `/compare`, `/changelog`) — through the mobile no-horizontal-overflow check. Re-ran the full responsive E2E suite after this pass's changes to confirm no regression; all pages still pass.

---

# Performance Improvements

Measured, not assumed:

| | Before this pass | After |
|---|---|---|
| JS (gzip) | 149.80 kB | 149.80 kB (unchanged — no component logic touched) |
| CSS (gzip) | 4.53 kB | 4.56 kB (+0.03 kB for the transition rule) |

Removed one unused static asset (`icons.svg`) as repo hygiene, per the brief's "remove obvious waste where safe" — zero measured runtime impact since it was never linked, but no reason to keep it. No new dependencies were introduced anywhere in this pass.

---

# Dark Mode Improvements

Not applicable — confirmed via direct inspection (`grep` for `dark:` variants and `prefers-color-scheme` across the entire frontend) that DrugSim has no dark-mode implementation; `index.css` explicitly declares `color-scheme: light`. Per the brief's own conditional wording ("if DrugSim supports dark mode"), and its explicit rule against adding major new functionality in a polish-only pass, building a dark mode from scratch was correctly out of scope. Noted honestly rather than silently skipped.

---

# Remaining Cosmetic Issues

🟢 **Optional polish, not implemented this pass:**
- The homepage hero's primary CTA button (`px-6 py-3`) is slightly larger than the in-workspace Predict button (`px-5 py-2.5`). This may be intentional hierarchy (a landing page's primary action deserving more visual weight than a repeated workspace action) rather than a bug — left untouched without stronger evidence either way; worth a deliberate visual call by whoever owns the design system next, not a guess made here.
- Buttons have hover and focus states but no distinct `active:` (pressed) state. Skipped this pass specifically because it's the same class of risk just found and fixed above (color-swap animations on buttons need individual verification against a WCAG scan, not a blanket rule) — a real addition here, done properly, would need to be checked one button at a time rather than applied globally.
- This pass relied on code-level audit plus the automated E2E/axe-core suite (no interactive browser tooling was available in this session) rather than direct pixel-level screenshots across breakpoints. The automated checks are real and passing, but a human visual pass at some point would still be worthwhile to catch anything purely aesthetic that automated tooling can't judge (e.g. whether the hero CTA size difference above reads as intentional or not).

---

# Testing

- Frontend unit (`vitest`): **110/110 pass**, unchanged from before this pass (no test logic touched — this was a CSS/HTML/asset-only pass).
- Typecheck (`tsc --noEmit`): clean.
- Production build (`npm run build`, the real CI command): clean.
- Lint (`oxlint`): clean.
- E2E (`playwright`, 38 tests): **38/38 pass**, including the full WCAG 2.1 AA axe-core scan across every page and dynamic state, and mobile no-overflow checks — this suite is what caught the transition-on-button regression described above, and confirmed the fix.
- Backend (predict service + security + scientific-regression suite): **172/172 pass**, unchanged — no backend file was touched in this pass.

---

# Scientific Safety Check

Re-confirmed after every change in this pass: the prediction, uncertainty, applicability domain, reliability, model information, limitations, and scientific disclaimer are all still visibly present and unmodified in every result view. Nothing in this pass touched `PredictionResults.tsx`, `UncertaintyPanel.tsx`, `ApplicabilityDomainGauge.tsx`, `ReliabilityBadge.tsx`, `ModelEvidencePanel.tsx`, `ScientificExplanation.tsx`, or any backend file — every change was confined to `index.html`, `index.css`, and `public/`. No visual change in this pass could plausibly have de-emphasized or hidden any of the required scientific information, since none of the components that render it were modified.

---

# Final UI Readiness Assessment

DrugSim's UI was already close to release-ready going into this pass — most of the brief's checklist (typography hierarchy, spacing discipline, restrained color use, honest loading/error/empty states, card consistency, accessible semantics) was already correctly built from the prior passes. This pass closed the remaining concrete gaps (missing favicon/metadata, unused asset, inconsistent hover feedback) and, in the process of adding the last of those, caught and correctly reverted a genuine accessibility regression rather than shipping it. The interface reads as a professional scientific tool, not a generic AI landing page — restrained palette, serif/sans/mono type hierarchy for display/body/technical content respectively, text-and-color (never color-alone) status signaling throughout, and no decorative animation beyond subtle, reduced-motion-respecting hover transitions on non-risk elements.
