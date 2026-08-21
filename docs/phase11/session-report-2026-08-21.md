# DrugSim — Session Report, 2026-08-21

## Summary

Three things landed live today: a per-prediction memory optimization, a
real double-model-load bug fix, and endpoint-specific scientific
limitations content. A fourth — an "AI attention map" explainability
feature — is built, hardened, and fully tested locally, but is **not
currently live**, pending your go-ahead below.

---

## 1. Shipped and live: reliability fixes

- **Applicability-domain memory fix.** The per-prediction check was
  recomputing the entire training-set fingerprint/descriptor arrays on
  every single request. Cached once per model at startup instead:
  **53MB → 2MB transient memory per prediction** (measured with
  tracemalloc, verified bit-identical predictions).
- **Found and fixed a real pre-existing bug while investigating the
  above**: the backend's own internal health check loaded the hERG model
  *twice* into memory permanently, because Python's `functools.lru_cache`
  treats a bare call and an explicit-default call as different cache
  entries. Confirmed with a minimal reproduction before fixing. Never
  affected real `/predict` traffic — only the health check's own code
  path.
- **Rate limit raised** from 30 to 100 requests/minute per client.

All verified live against production with the real API key, not just
locally.

## 2. Shipped and live: scientific transparency

The Limitations page and each endpoint's own "what does this mean"
copy now name specific, documented weaknesses instead of only general
disclaimers:

- CYP3A4's real specificity (40.5% — a genuine false-positive tendency),
  sourced from `docs/phase10/final-scientific-audit.md`.
- hERG's lack of independent external validation (TDC's download endpoint
  was unreachable during training).
- The 10 µM active/inactive threshold's status as a literature screening
  convention, not a clinical boundary.

One claim from the brief that prompted this — "mixed binding/functional
assay types" — was checked against this repo's actual docs and dataset
scripts, found nowhere, and deliberately left out rather than asserted.

## 3. Built, tested, NOT yet live: AI attention map (SHAP explainability)

**What it does:** for a hERG prediction, shows which atoms and which
physicochemical properties pushed the prediction toward or away from its
outcome, via SHAP over the actual trained model — not a new measurement,
not invented data.

**Real technical finding during development:** SHAP's default exact
algorithm failed its own internal correctness check on both models,
traced to these models' unusually deep trees (max depth up to 131).
Switched to a different SHAP mode designed for this exact situation;
verified the fix numerically (the explanation's parts now sum back to
the *exact* same probability `/predict` independently computes, to five
decimal places) rather than assuming it fixed anything.

**Incident history — two crashes, both real, both fixed:**

1. First deploy: CYP3A4's version of this feature (a much larger, 500-tree
   model) required ~280MB of additional memory to compute, on a server
   with a 512MB limit. Crashed the process. **Fix:** restricted the
   feature to hERG only, and added an automated test that measures actual
   memory cost for every endpoint the feature claims to support, so this
   can't silently regress again.
2. Second deploy (the fix above): the restriction check itself had a bug
   — it loaded CYP3A4's full model into memory *before* checking whether
   CYP3A4 was allowed to use the feature, defeating the point of the
   restriction. Crashed the process a second time, same way. **Fix:**
   reordered the check to run before any model loading at all, and added
   a test that reproduces the exact failing sequence (hERG explained
   successfully, then CYP3A4 requested in the same running process) to
   make sure it can't happen a third time.

**Current status:** fixed, and now verified against the *specific*
sequence that broke it twice — not just "seems fine," an actual
regression test for it. 648/648 backend tests, 119/119 frontend tests,
39/39 end-to-end tests all pass. **Not yet redeployed** — after two real
crashes on this exact feature today, I'd rather confirm with you before a
third attempt than push it silently again.

## 4. Retention (part of #3)

Once a user views the attention map for a prediction, the result is
cached in their browser (same private, local-only pattern as the existing
prediction history) so revisiting it doesn't recompute the SHAP call
again.

## 5. Automated safety gate (part of #3)

A new, permanent test
(`tests/unit/test_predict_explainability_memory.py`) measures real
resident-memory cost for every endpoint the attention-map feature
supports, and fails the test suite if any of them exceed a safe budget.
It's tied directly to the feature's own support list, so adding an
endpoint back without re-checking memory first breaks this test locally,
before a deploy — which is exactly the check that was missing the first
time.

---

## What's changed on the live site right now

Both memory/reliability fixes and the new Limitations/endpoint content
are live — see the [changelog](/) on the site itself. The attention map
feature is built and ready but held back per above.

## Open question

Want me to deploy the (now twice-fixed, newly regression-tested) hERG-only
attention map feature?
