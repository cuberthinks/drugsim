"""Live-serving wrapper around the psychiatric screening research pipeline.

Bridges `models/psychiatric/screening_profile.py` (a research pipeline
built and evaluated outside `src/`) into the live API's response schema.
This crosses the normal `src/`/`models/` boundary deliberately, in one
direction only: `screening_profile.py` already imports from
`drugsim_predict` (`model_registry`, `applicability_domain`,
`conformal`, `pipeline.run_inference`) to reuse validated production
logic instead of reimplementing it; this module closes the loop so that
same pipeline can be called FROM the live service. There is no proper
installable-package boundary between `src/` and `models/` in this repo
(mirroring how every `models/**/*.py` script already reaches into `src/`
via `sys.path.insert`), so this is a `sys.path` bridge, not a real
dependency -- documented here rather than silently done.

**Why this bypasses `run_inference`'s promotion gate, by design**: three
of this pipeline's six signals (DRD2, HRH1, CYP2D6, BBB) are
`EXPERIMENTAL` -- none has independent external validation. Routing them
through `run_inference` would either (a) fail closed
(`EndpointNotAvailableError`, exactly as verified for CYP2D6/BBB), which
would make this endpoint non-functional, or (b) require weakening
`run_inference`'s own promotion gate, which would ALSO silently let
these same experimental models start being served through the primary,
implicitly-trusted `/predict` route -- a much bigger, unintended change.
Instead, this endpoint is its own explicitly-labelled surface
(`POST /v1/psychiatric-screening`), and every signal in its response
carries its own real `reliability_tier` (`"validated"` for hERG only,
`"experimental"` for the other four) so a caller cannot mistake this for
the same guarantee `/predict` makes.
"""

from __future__ import annotations

import sys
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from drugsim_predict.psychiatric_schemas import (
    ClassificationSignalSchema,
    PsychiatricScreeningResponse,
    RegressionSignalSchema,
)

_MODELS_PSYCHIATRIC = Path(__file__).resolve().parents[2] / "models" / "psychiatric"
if str(_MODELS_PSYCHIATRIC) not in sys.path:
    sys.path.insert(0, str(_MODELS_PSYCHIATRIC))

from screening_profile import screen_compound  # noqa: E402

__all__ = ["run_psychiatric_screening"]


def run_psychiatric_screening(smiles: str) -> PsychiatricScreeningResponse:
    """Run the full six-signal psychiatric screening profile on one SMILES.

    Raises:
        drugsim_core.errors.StructureError: Unparseable/invalid input --
            propagated from `screen_compound`, same rejection semantics
            `run_inference` uses for `/predict`.
    """
    profile = screen_compound(smiles)

    return PsychiatricScreeningResponse(
        smiles=profile.smiles,
        drd2=RegressionSignalSchema(**asdict(profile.drd2)),
        hrh1=RegressionSignalSchema(**asdict(profile.hrh1)),
        selectivity_index_log10=profile.selectivity_index_log10,
        selectivity_fold_for_drd2=profile.selectivity_fold_for_drd2,
        selectivity_interpretation=profile.selectivity_interpretation,
        selectivity_domain_status=profile.selectivity_domain_status,
        cyp2d6=ClassificationSignalSchema(**asdict(profile.cyp2d6)),
        bbb=ClassificationSignalSchema(**asdict(profile.bbb)),
        herg=ClassificationSignalSchema(**asdict(profile.herg)),
        overall_caveats=profile.overall_caveats,
        inference_timestamp=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
