#!/usr/bin/env python3
"""DRD2/HRH1 selectivity calculation -- direction-correct, uncertainty-aware.

Per `docs/psychiatric-pipeline/scientific-foundation.md`'s selectivity
section: the naive `SI = H1_affinity / D2_affinity` from the original
feature brief is wrong as stated, because it never specifies whether
"affinity" means a potency value (smaller = stronger, e.g. raw Ki in nM)
or an inverted value (larger = stronger, e.g. pKi). This module never
performs that naive ratio.

Both `drd2_activity` and `hrh1_activity` predict `pki` on the identical
scale: pki = 9 - log10(Ki in nM), so higher pki always means stronger
binding, for both targets. That shared convention is what makes a
direction-correct comparison possible without first re-deriving which
way "more selective" points.

Full methodology, worked examples, and the exact interpretation
guidance: `docs/psychiatric-pipeline/selectivity-methodology.md`.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, Optional

__all__ = ["SelectivityResult", "compute_selectivity"]

DomainStatus = Literal["in_domain", "out_of_domain", "unknown"]


@dataclass(frozen=True)
class SelectivityResult:
    """The outcome of one DRD2-vs-HRH1 selectivity comparison.

    `selectivity_index_log10` is pki_drd2 - pki_hrh1, in log10 units --
    positive means the compound is predicted to bind DRD2 (the
    therapeutic target) more strongly than HRH1 (the off-target);
    negative means the reverse. This is NEVER a raw Ki ratio -- see the
    module docstring for why that would be direction-ambiguous.
    """

    selectivity_index_log10: float
    fold_selectivity_for_drd2: float  # 10 ** selectivity_index_log10
    interpretation: str
    uncertainty_half_width_log10: float
    domain_status: DomainStatus
    domain_caveat: Optional[str]


def compute_selectivity(
    pki_drd2: float,
    pki_hrh1: float,
    *,
    drd2_uncertainty_half_width: float,
    hrh1_uncertainty_half_width: float,
    drd2_in_domain: Optional[bool],
    hrh1_in_domain: Optional[bool],
) -> SelectivityResult:
    """Compute a direction-correct, uncertainty-aware selectivity index.

    Args:
        pki_drd2: Predicted DRD2 pKi (higher = stronger binding).
        pki_hrh1: Predicted HRH1 pKi (higher = stronger binding), on the
            SAME scale -- both models use the identical pki = 9 -
            log10(Ki_nM) transform, which is what makes this
            subtraction meaningful rather than mixing incompatible units.
        drd2_uncertainty_half_width: The DRD2 model's own split-conformal
            interval half-width (pKi units) for this prediction.
        hrh1_uncertainty_half_width: Same, for HRH1.
        drd2_in_domain: Whether the DRD2 model considers this structure
            in its applicability domain. `None` if not evaluated.
        hrh1_in_domain: Same, for HRH1.

    Returns:
        The selectivity result. The answer to "how much more strongly is
        this predicted to interact with the therapeutic target relative
        to the off-target" -- never a claim about clinical safety or
        efficacy (see the module docstring's cross-reference to the
        scientific-foundation audit for why that line is not implied
        here).
    """
    index = pki_drd2 - pki_hrh1
    fold = 10.0**index

    # Conservative (not variance-reduced): sums the two independent
    # models' own interval half-widths rather than assuming a Gaussian
    # combination that would require an unjustified independence-and-
    # normality assumption. Documented explicitly, not silently chosen --
    # see selectivity-methodology.md's "uncertainty propagation" section.
    combined_half_width = drd2_uncertainty_half_width + hrh1_uncertainty_half_width

    if drd2_in_domain is False or hrh1_in_domain is False:
        domain_status: DomainStatus = "out_of_domain"
        domain_caveat = (
            "At least one of the two underlying predictions falls outside its model's applicability "
            "domain -- this selectivity value is an extrapolation and should be treated with reduced "
            "confidence, on top of the uncertainty interval already reported."
        )
    elif drd2_in_domain is None or hrh1_in_domain is None:
        domain_status = "unknown"
        domain_caveat = "Applicability-domain status was not supplied for at least one target."
    else:
        domain_status = "in_domain"
        domain_caveat = None

    if index > 0:
        interpretation = (
            f"Predicted to bind DRD2 (the therapeutic target) roughly {fold:.1f}x more strongly "
            f"than HRH1 (the off-target), i.e. {index:+.2f} log10 units."
        )
    elif index < 0:
        interpretation = (
            f"Predicted to bind HRH1 (the off-target) roughly {1 / fold:.1f}x more strongly than "
            f"DRD2 (the therapeutic target), i.e. {index:+.2f} log10 units."
        )
    else:
        interpretation = "Predicted binding strength is equal for both targets on this scale."

    interpretation += (
        " This describes relative predicted binding strength only -- it is not a claim about "
        "clinical efficacy, safety, or that selectivity prevents any specific side effect (e.g. "
        "weight gain has multiple contributing mechanisms; see scientific-foundation.md)."
    )

    return SelectivityResult(
        selectivity_index_log10=round(index, 4),
        fold_selectivity_for_drd2=round(fold, 4),
        interpretation=interpretation,
        uncertainty_half_width_log10=round(combined_half_width, 4),
        domain_status=domain_status,
        domain_caveat=domain_caveat,
    )
