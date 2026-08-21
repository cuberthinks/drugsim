"""Per-atom SHAP explainability (Phase 11), opt-in only.

Not part of the mandatory /predict path -- see api.py's ``POST
/predict/explain`` docstring for why. Measured on the real, deployed models:
one call costs ~55-200ms of CPU (dominated by ``shap.TreeExplainer``'s exact
computation over a 200-500-tree ensemble, not something to pay on every
prediction under this service's concurrency limits).

Method: ``shap.TreeExplainer`` with ``feature_perturbation="interventional"``
against a fixed background sample of the model's own training data. The
default "tree_path_dependent" algorithm was tried first and rejected: it
failed its own additivity check on both real models (off by ~2e11 against an
actual output of ~0.69) because these trees are unusually deep (max depth up
to 131, ~3,000+ nodes each, per Phase 3's deliberately unconstrained
``max_depth=None``) -- deep enough that the exact path-dependent algorithm's
combinatorial path-weighting suffers real floating-point blowup. The
interventional method does not have this failure mode (verified: additivity
holds to ~1e-9 relative error on both models) because it estimates
contributions via expectation over background samples rather than an exact
recursive formula over tree paths.

A fingerprint bit has no fixed identity a chemist can act on -- "bit 1042
mattered" means nothing without knowing which atoms set it. This module
closes that gap by recomputing the query molecule's fingerprint WITH RDKit's
bit-info map (bit -> which atom-centred environments set it) and distributing
each bit's SHAP value across the atoms in those environments, so the output
is a per-atom contribution a 2D depiction can actually colour.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache

import numpy as np
import shap
from rdkit import Chem
from rdkit.Chem import rdFingerprintGenerator

from drugsim_chem import DEFAULT_N_BITS, DEFAULT_RADIUS
from drugsim_predict.model_registry import ModelBundle, get_model_bundle

__all__ = ["AtomContribution", "DescriptorContribution", "ExplainabilityResult", "compute_atom_contributions"]

#: Fixed, not tunable per-request -- reproducibility (TDS Sec 6.6's own
#: standard, applied here) requires the same query to always yield the same
#: explanation. Size chosen the same way conformal's calibration set size
#: was chosen for this project: large enough for the expectation estimate to
#: be stable, small enough that construction stays under ~50ms (measured).
_BACKGROUND_SAMPLE_SIZE = 100
_BACKGROUND_RANDOM_SEED = 42  # Matches this project's established convention (every model's random_seed: 42).

#: Index into shap's per-class output that always corresponds to the
#: POSITIVE class (blocker/inhibitor), matching bundle.sklearn_model.classes_
#: == [0, 1] and the exact convention run_inference's own predicted_label
#: logic already relies on (class_probabilities[1] >= 0.5).
_POSITIVE_CLASS_INDEX = 1


@dataclass(frozen=True)
class AtomContribution:
    """One heavy atom's total SHAP contribution, in the standardised
    molecule's own atom ordering (the same ``mol`` a caller gets from
    ``parse_molecule(standardized_smiles)``)."""

    atom_index: int
    contribution: float


@dataclass(frozen=True)
class DescriptorContribution:
    """One physicochemical descriptor's SHAP contribution -- not atom-
    mappable (there is no single atom "responsible" for molecular weight),
    shown as its own list instead."""

    name: str
    value: float
    contribution: float


@dataclass(frozen=True)
class ExplainabilityResult:
    """``base_value + sum(atom_contributions) + sum(descriptor_contributions)
    + absent_substructure_contribution`` reconstructs the model's predicted
    probability of ``positive_class_label`` exactly (verified in tests) --
    the same additivity guarantee SHAP itself makes, preserved all the way
    through the atom-mapping step rather than silently dropped by it.
    """

    positive_class_label: str
    base_value: float
    atom_contributions: list[AtomContribution]
    descriptor_contributions: list[DescriptorContribution]
    #: SHAP attributes real weight to fingerprint bits that are ABSENT from
    #: the query (a substructure's absence is still evidence, under the
    #: interventional method's background-expectation definition) -- but an
    #: absent substructure has no atom to highlight. Rather than silently
    #: drop this from the total (breaking additivity) or force it onto some
    #: arbitrary atom (misattributing it), it is surfaced honestly as its
    #: own number: how much of this prediction is explained by chemistry
    #: this molecule does NOT contain.
    absent_substructure_contribution: float
    method: str = "shap_tree_explainer_interventional"


@lru_cache(maxsize=None)
def _get_explainer(model_id: str) -> "shap.TreeExplainer":
    """Built once per process per endpoint, not once per request -- the
    same "pay a fixed cost once, not on every call" fix already applied to
    the applicability-domain reference arrays (model_registry.py). Keyed
    ONLY on ``model_id`` (never called with a different signature anywhere
    else in this codebase) specifically to avoid the functools.lru_cache
    bare-call-vs-explicit-default double-cache-key bug found and fixed
    elsewhere in this service (api.py's health_ready): a second call site
    with a different default would silently build and permanently cache a
    second explainer for the same model.
    """
    bundle = get_model_bundle(model_id)
    rng = np.random.RandomState(_BACKGROUND_RANDOM_SEED)
    n_train = bundle.train_fingerprints.shape[0]
    size = min(_BACKGROUND_SAMPLE_SIZE, n_train)
    idx = rng.choice(n_train, size=size, replace=False)
    background = np.concatenate(
        [bundle.train_descriptors[idx], bundle.train_fingerprints[idx].astype(np.float64)], axis=1
    )
    return shap.TreeExplainer(bundle.sklearn_model, data=background, feature_perturbation="interventional")


def _bit_environment_atoms(mol: Chem.Mol, center_atom: int, radius: int) -> set[int]:
    """The set of atom indices covered by one Morgan bit's environment.
    Radius 0 is just the centre atom itself (no bonds to walk)."""
    if radius == 0:
        return {center_atom}
    atoms = {center_atom}
    for bond_idx in Chem.FindAtomEnvironmentOfRadiusN(mol, radius, center_atom):
        bond = mol.GetBondWithIdx(bond_idx)
        atoms.add(bond.GetBeginAtomIdx())
        atoms.add(bond.GetEndAtomIdx())
    return atoms


def compute_atom_contributions(
    mol: Chem.Mol,
    descriptors_vec: np.ndarray,
    fingerprint_vec: np.ndarray,
    descriptor_fields: list[str],
    bundle: ModelBundle,
) -> ExplainabilityResult:
    """SHAP-attribute one already-featurised query back to descriptors and
    atoms. ``mol``/``descriptors_vec``/``fingerprint_vec`` must be the exact
    output of ``pipeline._validate_and_featurize`` for the same structure
    this is meant to explain (never recomputed independently -- see this
    module's docstring on why that would risk explaining a different
    feature vector than the one actually predicted on).
    """
    explainer = _get_explainer(bundle.model_id)
    feature_vec = np.concatenate([descriptors_vec, fingerprint_vec]).reshape(1, -1)
    shap_values = explainer.shap_values(feature_vec, check_additivity=True)
    per_feature = shap_values[0, :, _POSITIVE_CLASS_INDEX]

    n_desc = len(descriptor_fields)
    descriptor_contributions = [
        DescriptorContribution(name=name, value=float(descriptors_vec[i]), contribution=float(per_feature[i]))
        for i, name in enumerate(descriptor_fields)
    ]
    fingerprint_shap = per_feature[n_desc:]

    # Recompute the query's fingerprint WITH bit-info, matching
    # drugsim_chem.fingerprints.compute_morgan_fingerprint's exact generator
    # settings (same radius/bit count) -- see that module for why
    # includeChirality=True is load-bearing there; not needed for the bit
    # index numbering itself, so left at the generator default here.
    generator = rdFingerprintGenerator.GetMorganGenerator(radius=DEFAULT_RADIUS, fpSize=DEFAULT_N_BITS)
    additional_output = rdFingerprintGenerator.AdditionalOutput()
    additional_output.AllocateBitInfoMap()
    generator.GetFingerprint(mol, additionalOutput=additional_output)
    bit_info = additional_output.GetBitInfoMap()

    set_bits = set(bit_info.keys())
    atom_totals = np.zeros(mol.GetNumAtoms(), dtype=np.float64)
    for bit, environments in bit_info.items():
        bit_shap = float(fingerprint_shap[bit])
        if bit_shap == 0.0:
            continue
        # A bit set by more than one environment (symmetry-equivalent atoms)
        # splits evenly across them; each environment's own atoms then split
        # that share evenly again -- the same "distribute, don't duplicate"
        # rule applied twice, so the atom totals still sum to the bit's full
        # SHAP value (verified in tests).
        share_per_environment = bit_shap / len(environments)
        for center_atom, radius in environments:
            atoms = _bit_environment_atoms(mol, center_atom, radius)
            share_per_atom = share_per_environment / len(atoms)
            for atom_idx in atoms:
                atom_totals[atom_idx] += share_per_atom

    atom_contributions = [
        AtomContribution(atom_index=i, contribution=float(v)) for i, v in enumerate(atom_totals)
    ]

    # Every bit NOT in bit_info is absent from this molecule -- see
    # ExplainabilityResult.absent_substructure_contribution's docstring for
    # why this is surfaced rather than dropped.
    absent_contribution = float(sum(v for i, v in enumerate(fingerprint_shap) if i not in set_bits))

    return ExplainabilityResult(
        positive_class_label=bundle.positive_class_label,
        base_value=float(explainer.expected_value[_POSITIVE_CLASS_INDEX]),
        atom_contributions=atom_contributions,
        descriptor_contributions=descriptor_contributions,
        absent_substructure_contribution=absent_contribution,
    )
