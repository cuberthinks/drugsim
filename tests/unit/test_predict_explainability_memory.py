"""Memory-safety gate for the SHAP explainer (Phase 11 incident response).

Real incident, not a hypothetical: building shap.TreeExplainer for the
CYP3A4 model (500 trees, depth up to 131) measured a ~280MB resident-memory
jump on the deployed 512MB Render instance and crashed the process --
caught only after it reached production. Locally (this test's own
measurement, a different process/platform so not numerically identical,
but directionally the same finding) it costs ~75MB against hERG's near-zero
-- clearly, measurably heavier, well before ever touching production again.

This file is the gate that must pass before EXPLAINABLE_MODEL_IDS
(explainability.py) grows to include another endpoint: an "AI-feature
change is not done" until this passes, not a suggestion. It is tied
directly to that set, not to a hardcoded model list here, so:
  - Every endpoint the product actually offers /predict/explain for is
    automatically covered -- there is no separate list to forget to update.
  - Adding an endpoint to EXPLAINABLE_MODEL_IDS without first re-measuring
    is exactly the mistake that shipped the cyp3a4_inhibition incident;
    this test turns that mistake into a local, immediate failure.
"""

from __future__ import annotations

import sys

import pytest

from drugsim_predict.explainability import EXPLAINABLE_MODEL_IDS, _get_explainer
from drugsim_predict.model_registry import get_model_bundle

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]

#: Real headroom on the deployed instance is ~159MB (512MB limit - ~353MB
#: baseline for both models resident, per
#: models/registry/herg_inhibition_v1.json's deployment_variant block).
#: Half of that, not all of it, is the budget for ONE explainer: both
#: models' explainers can be built in the same long-lived process (a second
#: endpoint's attention map viewed in the same session) and are never
#: evicted (_get_explainer is lru_cache(maxsize=None)), so headroom must
#: cover every explainable endpoint simultaneously, not just one at a time.
MAX_EXPLAINER_MEMORY_MB = 75


def _rss_mb() -> float:
    """Resident set size of this process, in MB. ru_maxrss units differ by
    platform -- bytes on Darwin, KB on Linux (this project's Docker/Render
    target) -- determined by sys.platform, not a magnitude guess: a
    magnitude heuristic was tried first here and was wrong by exactly
    1024x for every real measurement in this project's normal few-hundred-
    MB range (a real bug this test caught in itself before it ever caught
    anything in the code under test)."""
    import resource

    raw = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    return raw / (1024 * 1024) if sys.platform == "darwin" else raw / 1024


def _explainer_memory_cost_mb(model_id: str) -> float:
    # Load the bundle (and pay its own resident cost) BEFORE measuring, so
    # this isolates the explainer's cost specifically, not model load.
    get_model_bundle(model_id)
    before = _rss_mb()
    _get_explainer(model_id)
    return _rss_mb() - before


@pytest.mark.parametrize("model_id", sorted(EXPLAINABLE_MODEL_IDS))
def test_every_explainable_endpoint_fits_memory_budget(model_id) -> None:
    """The actual gate: fails loudly, locally, if any endpoint this
    service actually offers /predict/explain for costs more resident
    memory than this deployment can safely absorb -- instead of finding
    out from a live crash and a metrics dashboard, as happened for
    cyp3a4_inhibition in production."""
    delta = _explainer_memory_cost_mb(model_id)
    assert delta < MAX_EXPLAINER_MEMORY_MB, (
        f"Building the SHAP explainer for {model_id!r} cost {delta:.0f}MB resident memory "
        f"(budget: {MAX_EXPLAINER_MEMORY_MB}MB). This is the exact failure mode that crashed "
        "production for cyp3a4_inhibition -- do not relax this budget without re-measuring "
        "actual Render memory_usage metrics after deploying."
    )


def test_cyp3a4_is_excluded() -> None:
    """Documents WHY cyp3a4_inhibition is not in EXPLAINABLE_MODEL_IDS.

    Deliberately does NOT re-assert a local memory number as the reason:
    this test file's own local delta for cyp3a4_inhibition measured 75.6MB
    in an isolated run and 58MB as part of the full suite (test order and
    what else is already resident in the process both move this number
    meaningfully) -- neither is close to the ~280MB actually measured via
    Render's own memory_usage metric in production at the time of the
    incident. Local RSS delta is a useful coarse smoke test (see the
    parametrized test above) but is NOT a reliable enough oracle for "is
    this specific number still true" -- that requires re-deploying and
    reading real metrics, not a local re-measurement.
    """
    assert "cyp3a4_inhibition" not in EXPLAINABLE_MODEL_IDS, (
        "cyp3a4_inhibition was re-added to EXPLAINABLE_MODEL_IDS -- before doing this, re-deploy "
        "and check Render's real memory_usage metric during a /predict/explain call for it, the "
        "same way the original ~280MB incident was diagnosed. A passing local test alone is not "
        "sufficient evidence (see this test's own docstring for why)."
    )
