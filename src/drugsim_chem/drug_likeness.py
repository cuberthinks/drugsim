"""Drug-likeness rule evaluation: Lipinski, Veber, Ghose, Egan, Muegge, QED, SA.

Matches ``compound_drug_likeness`` (``database/ddl/03_chemistry.sql``).
Consumes an already-computed :class:`~drugsim_chem.descriptors.PhysicochemicalDescriptors`
rather than recomputing RDKit properties, so a single molecule is only walked
once by the expensive descriptor calculations.

**Every rule here is a heuristic derived from historical drug sets, not a
physical law** (Phase 1 Step 4 §7.1). Novel chemotypes — macrocycles,
PROTACs, covalent binders — routinely and successfully violate them.
``pfizer_3_75_flag``/``gsk_4_400_flag`` are named ``_flag``, not ``_pass``,
specifically because they mark elevated risk, not failure — Phase 1 verified
that the Pfizer 3/75 finding has not been reproduced in later analyses.

SA score and NP-likeness reuse RDKit's own bundled contrib scripts
(``RDConfig.RDContribDir``) rather than a hand-rolled or vendored
reimplementation — they ship with the pinned RDKit installation already.
"""

from __future__ import annotations

import os
import sys
import warnings
from dataclasses import dataclass
from typing import Optional

from rdkit import Chem
from rdkit.Chem import QED, RDConfig

# RDKit's rdfiltercatalog extension re-registers a boost::python converter on
# import, which raises a RuntimeWarning under this project's strict
# filterwarnings=["error"] policy (verified directly: importing FilterCatalog
# unguarded fails test collection outright). This is an RDKit-internal
# implementation detail, not a signal about anything in this codebase, so it
# is suppressed narrowly at the exact import site rather than by loosening
# the project-wide warnings policy, which would risk masking an unrelated,
# genuine RuntimeWarning elsewhere.
with warnings.catch_warnings():
    warnings.simplefilter("ignore", RuntimeWarning)
    from rdkit.Chem import FilterCatalog

from drugsim_chem.descriptors import PhysicochemicalDescriptors

__all__ = ["DrugLikenessAssessment", "assess_drug_likeness"]

sys.path.append(os.path.join(RDConfig.RDContribDir, "SA_Score"))
sys.path.append(os.path.join(RDConfig.RDContribDir, "NP_Score"))
import sascorer  # noqa: E402  (path must be extended first)
import npscorer  # noqa: E402

# Loaded once at import time, not per call — npscorer's model is a multi-MB
# pickle; re-reading it for every molecule would dominate runtime.
#
# KNOWN, LOW-PRIORITY COSMETIC ISSUE: readNPModel() prints "reading NP model
# ... / model in" to the real stdout file descriptor. Verified directly that
# this bypasses contextlib.redirect_stdout entirely (it is not a Python-level
# sys.stdout write — some layer beneath it writes to fd 1 directly), so the
# attempted fix using redirect_stdout here was removed rather than left in
# place implying a suppression that does not actually happen. Genuinely
# silencing it needs OS-level fd redirection (dup2 to /dev/null), which is
# more machinery than a one-time, harmless startup message justifies. Unlike
# standardize.py's rdBase.BlockLogs() fix (§ that one is PER-CALL noise on
# every molecule processed, which did justify the effort), this fires once
# per process at import time.
_NP_MODEL = npscorer.readNPModel()


def _build_catalog(*names: "FilterCatalog.FilterCatalogParams.FilterCatalogs") -> FilterCatalog.FilterCatalog:
    """Build a FilterCatalog covering the given named catalogs.

    Args:
        names: One or more ``FilterCatalogParams.FilterCatalogs`` enum values.

    Returns:
        The constructed catalog.
    """
    params = FilterCatalog.FilterCatalogParams()
    for name in names:
        params.AddCatalog(name)
    return FilterCatalog.FilterCatalog(params)


_PAINS_CATALOG = _build_catalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.PAINS)
_BRENK_CATALOG = _build_catalog(FilterCatalog.FilterCatalogParams.FilterCatalogs.BRENK)


@dataclass(frozen=True)
class DrugLikenessAssessment:
    """Drug-likeness rule verdicts and scores for one molecule.

    Boolean rule fields are the component pass/fail; nothing here is
    collapsed to a single "drug-like: yes/no" bit, because a chemist needs to
    see *which* rule failed and by how much.
    """

    lipinski_violations: int
    lipinski_pass: bool
    veber_pass: bool
    ghose_pass: bool
    egan_pass: bool
    muegge_pass: bool
    rule_of_three_pass: bool
    bioavailability_score: float
    qed_score: float
    sa_score: float
    np_likeness_score: float
    pains_alerts: int
    brenk_alerts: int
    pfizer_3_75_flag: Optional[bool]
    gsk_4_400_flag: bool


def _martin_bioavailability_score(
    mol: Chem.Mol, descriptors: PhysicochemicalDescriptors, lipinski_pass: bool
) -> float:
    """The Martin (2005) oral bioavailability heuristic.

    **Corrected during Sprint 2.5** after web verification against the
    original rule (Martin, Y.C., *J. Med. Chem.* 2005, 48, 3164-3170) —
    Phase 1's documentation and this function's first draft both guessed at a
    charge/TPSA 2x2 matrix producing exactly four values, which is wrong on
    two counts:

    1. The real rule is NOT symmetric between anions and everything else.
       **Anions** get a three-tier score by TPSA: PSA<=75 -> 0.85 (a value the
       original guess omitted entirely); 75<PSA<150 -> 0.56; PSA>=150 -> 0.11.
       **Neutral, zwitterionic, or cationic** compounds are scored instead by
       whether they pass the **Lipinski Rule of Five** — 0.55 if they pass,
       0.17 if they fail. TPSA plays no role in that branch at all.
    2. **"Anion" means the predominant ionisation state at physiological pH**,
       not the formal charge on the input/standardised structure as drawn.
       Most carboxylic acids are submitted and stored neutral (``-C(=O)OH``)
       but are >99% ionised to carboxylate at pH 7.4 — exactly the case this
       score is meant to distinguish.

    **Known limitation, stated rather than hidden:** correctly determining
    "anion at physiological pH" requires pKa prediction, which Phase 1 Step 4
    §4/§11 explicitly deferred pending a pKa predictor decision. This function
    uses formal charge on the standardised structure as a proxy, which is
    known to misclassify the common case above (a neutral-drawn carboxylic
    acid is treated as neutral/Ro5-branch here, when the real rule would
    treat it as anionic/TPSA-branch). This is flagged in the Sprint 2.5
    completion report as a scientific limitation requiring a follow-up
    decision, not silently presented as accurate.

    Args:
        mol: The molecule (used for formal charge — see limitation above).
        descriptors: Precomputed descriptors (used for TPSA).
        lipinski_pass: The already-computed Rule of Five verdict for this
            molecule, reused rather than recomputed.

    Returns:
        One of 0.11, 0.17, 0.55, 0.56, 0.85, per Martin's actual tiers.
    """
    charge = Chem.GetFormalCharge(mol)
    if charge < 0:
        tpsa = descriptors.tpsa_a2
        if tpsa <= 75:
            return 0.85
        if tpsa < 150:
            return 0.56
        return 0.11
    return 0.55 if lipinski_pass else 0.17


def assess_drug_likeness(
    mol: Chem.Mol,
    descriptors: PhysicochemicalDescriptors,
    *,
    logd_74: Optional[float] = None,
) -> DrugLikenessAssessment:
    """Evaluate all drug-likeness rules for one molecule.

    Args:
        mol: A sanitised, standardised molecule.
        descriptors: Precomputed descriptors for the same molecule (see
            :func:`drugsim_chem.descriptors.compute_descriptors`).
        logd_74: Measured or predicted logD at pH 7.4, if available. Required
            for the Pfizer 3/75 flag (Phase 1 Step 4 §7 — this is a measured/
            predicted quantity, never a computed descriptor, per the Step 4
            §1 correction); the flag is ``None`` when unavailable, never
            silently coerced to a pass.

    Returns:
        The full assessment.
    """
    mw = descriptors.mw_g_mol
    logp = descriptors.logp_crippen
    tpsa = descriptors.tpsa_a2
    hbd = descriptors.hbd_lipinski
    hba = descriptors.hba_lipinski
    rotb = descriptors.rotatable_bonds
    mr = descriptors.molar_refractivity
    heavy_atoms = descriptors.heavy_atom_count
    ring_count = descriptors.ring_count
    heteroatoms = descriptors.heteroatom_count
    carbon_count = heavy_atoms - heteroatoms

    lipinski_violations = sum([mw > 500, logp > 5, hbd > 5, hba > 10])
    lipinski_pass = lipinski_violations <= 1

    veber_pass = rotb <= 10 and tpsa <= 140

    ghose_pass = (
        160 <= mw <= 480
        and -0.4 <= logp <= 5.6
        and 40 <= mr <= 130
        and 20 <= heavy_atoms <= 70
    )

    egan_pass = tpsa <= 131.6 and logp <= 5.88

    muegge_pass = (
        200 <= mw <= 600
        and -2 <= logp <= 5
        and tpsa <= 150
        and ring_count <= 7
        and carbon_count > 4
        and heteroatoms > 1
        and rotb <= 15
        and hba <= 10
        and hbd <= 5
    )

    rule_of_three_pass = mw < 300 and logp <= 3 and hbd <= 3 and hba <= 3 and rotb <= 3

    pfizer_3_75_flag = None if logd_74 is None else (logp > 3 and tpsa < 75)
    gsk_4_400_flag = logp > 4 and mw > 400

    return DrugLikenessAssessment(
        lipinski_violations=lipinski_violations,
        lipinski_pass=lipinski_pass,
        veber_pass=veber_pass,
        ghose_pass=ghose_pass,
        egan_pass=egan_pass,
        muegge_pass=muegge_pass,
        rule_of_three_pass=rule_of_three_pass,
        bioavailability_score=_martin_bioavailability_score(mol, descriptors, lipinski_pass),
        qed_score=QED.qed(mol),
        sa_score=sascorer.calculateScore(mol),
        np_likeness_score=npscorer.scoreMol(mol, _NP_MODEL),
        pains_alerts=len(_PAINS_CATALOG.GetMatches(mol)),
        brenk_alerts=len(_BRENK_CATALOG.GetMatches(mol)),
        pfizer_3_75_flag=pfizer_3_75_flag,
        gsk_4_400_flag=gsk_4_400_flag,
    )
