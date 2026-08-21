"""Regression test for a real incident: rejecting an unexplainable
endpoint must never load that endpoint's model bundle as a side effect.

The first attempt at this restriction checked ``bundle.model_id`` AFTER
calling ``get_model_bundle(model_id)`` -- so refusing to explain
cyp3a4_inhibition still fully loaded the CYP3A4 model into memory before
raising, and crashed the process a second time in production (see
explainability.py's module docstring and pipeline.explain_prediction's
own docstring for the incident). This test asserts the actual fix: the
model bundle is never touched at all when the endpoint is rejected.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from drugsim_predict.explainability import UnexplainableEndpointError
from drugsim_predict.pipeline import explain_prediction

pytestmark = [pytest.mark.unit, pytest.mark.model_artifact]


def test_rejecting_an_unsupported_endpoint_never_loads_its_model_bundle() -> None:
    with patch("drugsim_predict.pipeline.get_model_bundle") as mock_get_bundle:
        with pytest.raises(UnexplainableEndpointError):
            explain_prediction("CCO", "smiles", model_id="cyp3a4_inhibition")
        mock_get_bundle.assert_not_called()


def test_rejection_message_names_the_endpoint_and_what_is_supported() -> None:
    with pytest.raises(UnexplainableEndpointError) as exc_info:
        explain_prediction("CCO", "smiles", model_id="cyp3a4_inhibition")
    assert "cyp3a4_inhibition" in str(exc_info.value)
    assert "herg_inhibition" in str(exc_info.value)
