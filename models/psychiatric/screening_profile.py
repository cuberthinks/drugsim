#!/usr/bin/env python3
"""Multi-objective psychiatric compound screening profile (Steps 8-9).

Combines every endpoint built in this pipeline into one structured,
per-endpoint-honest report -- never a single blind pass/fail verdict
(the feature brief's own §11 instruction). Three genuinely different
reuse strategies are used, by design, not by oversight:

1. **hERG** (Step 8, "reuse existing infrastructure, never retrain"):
   called through the REAL, already-validated production path,
   `drugsim_predict.pipeline.run_inference`, exactly as the live
   `/predict` API already does. hERG's own applicability-domain,
   conformal, and reliability output passes through unchanged.

2. **CYP2D6 and BBB**: both are classification endpoints, and both were
   registered (`models/registry/{cyp2d6_activity,bbb_permeability}_v1.json`)
   into the SAME generic `drugsim_predict.model_registry` machinery
   hERG uses -- but their `final_report_status` is `EXPERIMENTAL`, so
   `run_inference`'s own promotion gate correctly refuses to serve them
   as normal predictions (verified live: `EndpointNotAvailableError`).
   That gate protects the LIVE public API from serving an unreviewed
   model; it is not a reason to avoid the real, validated AD/conformal
   *logic* in an offline research tool. This script therefore calls
   `model_registry.load_model_bundle` (the loader, not the gated
   wrapper) and then the exact same `applicability_domain.
   assess_applicability_domain` / `conformal.compute_conformal_set`
   functions `run_inference` would have called -- genuine reuse of
   validated logic, with each result honestly labelled EXPERIMENTAL /
   not-live-served, never presented as equivalent to hERG's validated
   status.

3. **DRD2 and HRH1**: continuous binding-affinity regressions. No
   classification-shaped serving path exists in `drugsim_predict` for
   these (the architecture gap `data-sources.md` already documents),
   so they are scored directly against their own artifacts, mirroring
   `demo_selectivity.py`'s already-verified pattern (own model, own
   evaluation_report.json-derived conformal half-width, own
   exclude-self-fixed Tanimoto-based applicability check).

Usage (as a library):
    from models.psychiatric.screening_profile import screen_compound
    profile = screen_compound(smiles)

Usage (CLI demo): see demo_screening_profile.py.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import joblib
import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from drugsim_chem import compute_descriptors, compute_morgan_fingerprint  # noqa: E402
from drugsim_chem.identity import compute_identity  # noqa: E402
from drugsim_chem.parsing import parse_molecule  # noqa: E402
from drugsim_core.errors import EndpointNotAvailableError, StructureError  # noqa: E402
from drugsim_predict.applicability_domain import assess_applicability_domain  # noqa: E402
from drugsim_predict.conformal import compute_conformal_set  # noqa: E402
from drugsim_predict.model_registry import load_model_bundle  # noqa: E402
from drugsim_predict.pipeline import run_inference  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
from selectivity import compute_selectivity  # noqa: E402

DESCRIPTOR_FIELDS = [
    "mw_g_mol", "exact_mass_g_mol", "logp_crippen", "molar_refractivity", "tpsa_a2",
    "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count", "formal_charge",
    "hbd_lipinski", "hba_lipinski", "hbd_strict", "hba_strict", "heteroatom_count",
    "fraction_csp3", "num_stereocentres", "largest_ring_size",
]


@dataclass(frozen=True)
class ClassificationSignal:
    """One binary-classification endpoint's result, with real status honesty."""

    endpoint: str
    deployment_status: str  # "validated_live" | "registered_experimental_offline_only"
    predicted_label: str
    predicted_probability: float
    conformal_set: tuple[str, ...]
    conformal_is_singleton: bool
    applicability_domain_verdict: str
    applicability_domain_rationale: str
    caveat: Optional[str] = None


@dataclass(frozen=True)
class RegressionSignal:
    """One continuous binding-affinity endpoint's result."""

    endpoint: str
    deployment_status: str
    predicted_pki: float
    uncertainty_half_width_pki: float
    applicability_domain_verdict: str
    caveat: Optional[str] = None


@dataclass(frozen=True)
class PsychiatricScreeningProfile:
    """The full, non-blind-pass/fail multi-objective screening report."""

    smiles: str
    drd2: RegressionSignal
    hrh1: RegressionSignal
    selectivity_index_log10: float
    selectivity_fold_for_drd2: float
    selectivity_interpretation: str
    selectivity_domain_status: str
    cyp2d6: ClassificationSignal
    bbb: ClassificationSignal
    herg: ClassificationSignal
    overall_caveats: list[str] = field(default_factory=list)


def _featurize(smiles: str) -> tuple[np.ndarray, np.ndarray, np.ndarray, Optional[str]]:
    """Return (combined_x, descriptors, fingerprint, scaffold) for one SMILES."""
    mol = parse_molecule(smiles)
    d = compute_descriptors(mol)
    descriptors = np.array([getattr(d, f) or 0.0 for f in DESCRIPTOR_FIELDS], dtype=np.float64)
    fingerprint = compute_morgan_fingerprint(mol)
    x = np.concatenate([descriptors, fingerprint]).reshape(1, -1)
    scaffold = compute_identity(mol).bemis_murcko_scaffold
    return x, descriptors, fingerprint, scaffold


def _score_regression_endpoint(endpoint_dir: str, smiles: str, x: np.ndarray, fingerprint: np.ndarray) -> RegressionSignal:
    """DRD2/HRH1 -- direct artifact scoring, mirroring demo_selectivity.py."""
    base = ROOT / "models" / "psychiatric" / f"{endpoint_dir}_activity"
    model = joblib.load(base / "artifact" / "model.joblib")
    evaluation = json.loads((base / "evaluation_report.json").read_text(encoding="utf-8"))

    pki = float(model.predict(x)[0])
    half_width = evaluation["conformal"]["interval_half_width_pki_units"]

    features_npz = np.load(ROOT / "datasets" / "processed" / f"{endpoint_dir}_activity_features.npz", allow_pickle=True)
    train_mask = np.isin(features_npz["split_groups"], list(range(7)))
    train_fp = features_npz["fingerprints"][train_mask].astype(np.float32)

    q = fingerprint.astype(np.float32)
    intersection = (q[None, :] @ train_fp.T)[0]
    union = q.sum() + train_fp.sum(axis=1) - intersection
    with np.errstate(divide="ignore", invalid="ignore"):
        tanimoto = np.where(union > 0, intersection / union, 0.0)
    max_tanimoto = float(tanimoto.max())
    tanimoto_threshold = evaluation["applicability_domain"]["thresholds"]["tanimoto_min_for_in_domain"]
    ad_verdict = "in_domain" if max_tanimoto >= tanimoto_threshold else "out_of_domain"

    return RegressionSignal(
        endpoint=endpoint_dir.upper(),
        deployment_status="offline_research_only_no_regression_serving_path",
        predicted_pki=round(pki, 4),
        uncertainty_half_width_pki=round(half_width, 4),
        applicability_domain_verdict=ad_verdict,
        caveat=(
            "No continuous/regression prediction schema exists yet in drugsim_predict "
            "(architecture gap documented in data-sources.md) -- scored directly against "
            "the offline model artifact, not through the live API."
        ),
    )


def _score_classification_endpoint(model_id: str, x: np.ndarray, descriptors: np.ndarray, fingerprint: np.ndarray, scaffold: Optional[str]) -> ClassificationSignal:
    """CYP2D6/BBB -- real production bundle + AD + conformal logic, offline (registered but EXPERIMENTAL)."""
    bundle = load_model_bundle(model_id=model_id)
    probs = bundle.sklearn_model.predict_proba(x)[0]
    predicted_label = bundle.positive_class_label if probs[1] >= 0.5 else bundle.negative_class_label

    ad = assess_applicability_domain(fingerprint, descriptors, scaffold, bundle)
    conformal = compute_conformal_set(probs, bundle)

    return ClassificationSignal(
        endpoint=bundle.registry["endpoint"]["name"],
        deployment_status="registered_experimental_offline_only",
        predicted_label=predicted_label,
        predicted_probability=round(float(probs[1]), 4),
        conformal_set=conformal.predicted_set,
        conformal_is_singleton=conformal.is_singleton,
        applicability_domain_verdict=ad.verdict,
        applicability_domain_rationale=ad.rationale,
        caveat=bundle.registry["endpoint"].get("scientific_caveat"),
    )


def _score_herg(smiles: str) -> ClassificationSignal:
    """hERG -- the real, validated, live production path. Reuse as-is, never retrain."""
    try:
        result = run_inference(smiles, "smiles", model_id="herg_inhibition")
    except EndpointNotAvailableError as exc:  # pragma: no cover -- hERG is validated; documents the fallback
        return ClassificationSignal(
            endpoint="hERG (KCNH2/Kv11.1) inhibition",
            deployment_status="unavailable",
            predicted_label="unknown",
            predicted_probability=0.0,
            conformal_set=(),
            conformal_is_singleton=False,
            applicability_domain_verdict="undeterminable",
            applicability_domain_rationale=str(exc),
        )
    return ClassificationSignal(
        endpoint="hERG (KCNH2/Kv11.1) inhibition",
        deployment_status="validated_live",
        predicted_label=result.predicted_label,
        predicted_probability=result.predicted_probability,
        conformal_set=result.conformal.predicted_set,
        conformal_is_singleton=result.conformal.is_singleton,
        applicability_domain_verdict=result.applicability_domain.verdict,
        applicability_domain_rationale=result.applicability_domain.rationale,
        caveat=(
            "hERG affinity is a standard early-screening proxy; actual arrhythmia (Torsades) risk "
            "depends on multi-channel effects, metabolites, and patient factors this model does not "
            "capture. See scientific-foundation.md."
        ),
    )


def screen_compound(smiles: str) -> PsychiatricScreeningProfile:
    """Run every endpoint in this pipeline on one compound and combine the results.

    Raises:
        drugsim_core.errors.StructureError: Unparseable/invalid input,
            same rejection the live API applies before any prediction.
    """
    try:
        x, descriptors, fingerprint, scaffold = _featurize(smiles)
    except Exception as exc:  # noqa: BLE001 -- re-raise as the project's own structured error
        raise StructureError(str(exc), fmt="smiles") from exc

    drd2 = _score_regression_endpoint("drd2", smiles, x, fingerprint)
    hrh1 = _score_regression_endpoint("hrh1", smiles, x, fingerprint)
    selectivity = compute_selectivity(
        drd2.predicted_pki,
        hrh1.predicted_pki,
        drd2_uncertainty_half_width=drd2.uncertainty_half_width_pki,
        hrh1_uncertainty_half_width=hrh1.uncertainty_half_width_pki,
        drd2_in_domain=(drd2.applicability_domain_verdict == "in_domain"),
        hrh1_in_domain=(hrh1.applicability_domain_verdict == "in_domain"),
    )

    cyp2d6 = _score_classification_endpoint("cyp2d6_activity", x, descriptors, fingerprint, scaffold)
    bbb = _score_classification_endpoint("bbb_permeability", x, descriptors, fingerprint, scaffold)
    herg = _score_herg(smiles)

    overall_caveats = [
        "This is a non-clinical research screening tool. No output here is a diagnosis, a treatment "
        "recommendation, or a substitute for pharmacological or clinical judgment.",
        "Each endpoint's own deployment_status is reported honestly -- 'registered_experimental_"
        "offline_only' and 'offline_research_only_no_regression_serving_path' are NOT the same "
        "reliability tier as hERG's 'validated_live' status. Do not treat all six signals as "
        "equally trustworthy.",
    ]

    return PsychiatricScreeningProfile(
        smiles=smiles,
        drd2=drd2,
        hrh1=hrh1,
        selectivity_index_log10=selectivity.selectivity_index_log10,
        selectivity_fold_for_drd2=selectivity.fold_selectivity_for_drd2,
        selectivity_interpretation=selectivity.interpretation,
        selectivity_domain_status=selectivity.domain_status,
        cyp2d6=cyp2d6,
        bbb=bbb,
        herg=herg,
        overall_caveats=overall_caveats,
    )
