#!/usr/bin/env python3
"""Multi-objective psychiatric compound screening profile.

Combines every endpoint built in this pipeline into one structured,
per-endpoint-honest report -- never a single blind pass/fail verdict.
Served live via `POST /v1/psychiatric-screening`
(`drugsim_predict.psychiatric_pipeline`), deliberately OUTSIDE the
promotion-gated `run_inference`/`/v1/predictions` path: this is an
explicitly-labelled research/screening tool, not a claim that every
signal in it has passed the same review hERG has. Three genuinely
different reuse strategies are used, by design, not by oversight:

1. **hERG** ("reuse existing infrastructure, never retrain"): called
   through the REAL, already-validated production path,
   `drugsim_predict.pipeline.run_inference`, exactly as `/v1/predictions`
   already does. hERG's own applicability-domain, conformal, and
   reliability output passes through unchanged -- this is the one
   signal in the profile with `reliability_tier: "validated"`.

2. **CYP2D6 and BBB**: both are classification endpoints, registered
   (`models/registry/{cyp2d6_activity,bbb_permeability}_v1.json`) into
   the SAME generic `drugsim_predict.model_registry` machinery hERG
   uses -- but their `final_report_status` is `EXPERIMENTAL`, so
   `run_inference`'s own promotion gate would correctly refuse to serve
   them as a *normal* prediction (verified: `EndpointNotAvailableError`).
   That gate protects `/v1/predictions` from serving an unreviewed model
   as if it were reviewed; it is not a reason to avoid the real,
   validated AD/conformal *logic* in a tool that is explicit about being
   experimental. This module therefore calls `model_registry.
   load_model_bundle` (the loader, not the gated wrapper) and then the
   exact same `applicability_domain.assess_applicability_domain` /
   `conformal.compute_conformal_set` functions `run_inference` would
   have called -- genuine reuse of validated logic, `reliability_tier:
   "experimental"`, never presented as equivalent to hERG's status.

3. **DRD2 and HRH1**: continuous binding-affinity regressions. No
   classification-shaped schema fits these, so they are scored directly
   against their own artifacts (compact inference-support npz + frozen
   conformal/AD thresholds from evaluation_report.json), also
   `reliability_tier: "experimental"`.

Usage (as a library):
    from models.psychiatric.screening_profile import screen_compound
    profile = screen_compound(smiles)

Usage (CLI demo): see demo_screening_profile.py.
Usage (live API): POST /v1/psychiatric-screening, see
    src/drugsim_predict/psychiatric_pipeline.py.
"""

from __future__ import annotations

import json
import sys
from dataclasses import dataclass, field
from functools import lru_cache
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
from drugsim_predict.model_registry import get_model_bundle  # noqa: E402
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
    reliability_tier: str  # "validated" | "experimental"
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
    reliability_tier: str
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


@lru_cache(maxsize=None)
def _load_regression_bundle(endpoint_dir: str) -> tuple[object, dict, np.ndarray]:
    """Load and cache one regression endpoint's model + evaluation report + train fingerprints.

    Loaded once per process, not per request -- DRD2's model.joblib alone
    is ~248MB (n_estimators=500, max_depth=None on a 2066-dim feature
    space); re-deserializing that from disk on every request would be
    both slow and wasteful. Mirrors `drugsim_predict.model_registry.
    get_model_bundle`'s own `lru_cache` pattern for the classification
    endpoints.
    """
    base = ROOT / "models" / "psychiatric" / f"{endpoint_dir}_activity"
    model = joblib.load(base / "artifact" / "model.joblib")
    evaluation = json.loads((base / "evaluation_report.json").read_text(encoding="utf-8"))
    support = np.load(base / "artifact" / "inference_support.npz", allow_pickle=True)
    train_fp = support["train_fingerprints"].astype(np.float32)
    return model, evaluation, train_fp


def _score_regression_endpoint(endpoint_dir: str, smiles: str, x: np.ndarray, fingerprint: np.ndarray) -> RegressionSignal:
    """DRD2/HRH1 -- direct artifact scoring against the compact serving artifact.

    Uses `artifact/inference_support.npz` (training-split fingerprints
    only, built by this endpoint's own `10_export_inference_support.py`)
    rather than the full `datasets/processed/*_features.npz` -- the
    latter is a training/eval artifact (also carries descriptors,
    labels, local_compound_id for the whole dataset) never meant to
    ship in a serving image.
    """
    model, evaluation, train_fp = _load_regression_bundle(endpoint_dir)

    pki = float(model.predict(x)[0])
    half_width = evaluation["conformal"]["interval_half_width_pki_units"]

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
        reliability_tier="experimental",
        predicted_pki=round(pki, 4),
        uncertainty_half_width_pki=round(half_width, 4),
        applicability_domain_verdict=ad_verdict,
        caveat=(
            "No independent external validation has been performed for this endpoint -- see "
            "docs/psychiatric-pipeline/limitations.md. Scored against a classical model "
            "(Random Forest/Gradient Boosting), evaluated on an internal scaffold-split test set only."
        ),
    )


def _score_classification_endpoint(model_id: str, x: np.ndarray, descriptors: np.ndarray, fingerprint: np.ndarray, scaffold: Optional[str]) -> ClassificationSignal:
    """CYP2D6/BBB -- real production bundle + AD + conformal logic (registered EXPERIMENTAL).

    Uses `get_model_bundle` (process-wide `lru_cache`), NOT the bare
    `load_model_bundle` loader -- the latter re-reads and re-verifies the
    full model + inference-support artifacts from disk on every call,
    which at live-request volume would mean deserializing a multi-tens-
    of-MB pickle on every single screening request. Same cache
    `run_inference`/`/predict` already relies on for hERG/CYP3A4.
    """
    bundle = get_model_bundle(model_id=model_id)
    probs = bundle.sklearn_model.predict_proba(x)[0]
    predicted_label = bundle.positive_class_label if probs[1] >= 0.5 else bundle.negative_class_label

    ad = assess_applicability_domain(fingerprint, descriptors, scaffold, bundle)
    conformal = compute_conformal_set(probs, bundle)

    return ClassificationSignal(
        endpoint=bundle.registry["endpoint"]["name"],
        reliability_tier="experimental",
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
            reliability_tier="unavailable",
            predicted_label="unknown",
            predicted_probability=0.0,
            conformal_set=(),
            conformal_is_singleton=False,
            applicability_domain_verdict="undeterminable",
            applicability_domain_rationale=str(exc),
        )
    return ClassificationSignal(
        endpoint="hERG (KCNH2/Kv11.1) inhibition",
        reliability_tier="validated",
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
        "Each endpoint's own reliability_tier is reported honestly -- only hERG is 'validated' "
        "(passed this project's own promotion review). DRD2, HRH1, CYP2D6, and BBB are all "
        "'experimental': real, evaluated models with disclosed uncertainty and applicability-domain "
        "checks, but none has had independent external validation. Do not treat all six signals as "
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
