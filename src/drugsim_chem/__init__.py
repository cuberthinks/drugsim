"""DrugSim chemistry: standardisation, descriptors, identity, alerts.

**This package is the single implementation of every chemistry operation in
DrugSim.** It is imported unchanged by the ETL pipeline, by model training, and by
the inference path. It is not a library that inference reimplements or ports.

That property is what structurally prevents training/serving skew (TDS §6.6, risk
R5). Two enforcement mechanisms back it up:

* A lint rule prohibits importing ``rdkit`` anywhere outside this package
  (TDS §8.2, rule 3).
* ``CODEOWNERS`` requires cheminformatics review for any change here.

Every function that computes a value from a structure is deterministic given a
pinned ``descriptor_spec_version``, and its output is therefore reproducible only
within a fixed toolchain. See :mod:`drugsim_core.version` for why.

Modules:
    parsing: Structure parsing/sanitisation with real, capturable RDKit
        diagnostics.
    standardize: Salt stripping, charge neutralisation, tautomer
        canonicalisation.
    identity: InChI/InChIKey, canonical/isomeric SMILES, scaffolds.
    descriptors: Physicochemical descriptor computation.
    drug_likeness: Lipinski/Veber/Ghose/Egan/Muegge/Ro3, QED, SA score, alerts.
    pipeline: ``process_structure`` — the single ETL entry point tying the
        above together in order.
"""

from __future__ import annotations

from rdkit import rdBase

# Module-level, one-time side effect, deliberately placed in the PACKAGE
# __init__ rather than in any one submodule: Python guarantees __init__.py
# runs before any submodule is imported, so this configuration is guaranteed
# to be in effect regardless of which submodule a caller imports first —
# relying on it being set as a side effect of importing `parsing` specifically
# would silently stop working for any caller that imports `standardize` or
# `descriptors` directly without going through `parsing` or `pipeline` first.
#
# Covers all three RDKit log categories: verified directly that `standardize`
# (via rdMolStandardize's Cleanup/Uncharger) prints "Initializing X / Running
# X" at INFO level, which `rdApp.error`/`rdApp.warning` suppression alone
# (sufficient for parsing.py's failure-message capture) does not silence.
rdBase.DisableLog("rdApp.error")
rdBase.DisableLog("rdApp.warning")
rdBase.DisableLog("rdApp.info")
rdBase.LogToPythonStderr()

from drugsim_chem.descriptors import (  # noqa: E402  (after RDKit logging setup)
    DESCRIPTOR_SPEC_VERSION,
    PhysicochemicalDescriptors,
    compute_descriptors,
)
from drugsim_chem.drug_likeness import DrugLikenessAssessment, assess_drug_likeness  # noqa: E402
from drugsim_chem.fingerprints import (  # noqa: E402
    DEFAULT_N_BITS,
    DEFAULT_RADIUS,
    compute_morgan_fingerprint,
)
from drugsim_chem.identity import MolecularIdentity, compute_identity, stereo_completeness  # noqa: E402
from drugsim_chem.parsing import StructureFormat, parse_molecule  # noqa: E402
from drugsim_chem.pipeline import ProcessedCompound, process_structure  # noqa: E402
from drugsim_chem.standardize import (  # noqa: E402
    STANDARDIZATION_PIPELINE_VERSION,
    FragmentClassification,
    StandardizedStructure,
    classify_fragments,
    standardize,
)

__all__ = [
    "DEFAULT_N_BITS",
    "DEFAULT_RADIUS",
    "DESCRIPTOR_SPEC_VERSION",
    "STANDARDIZATION_PIPELINE_VERSION",
    "DrugLikenessAssessment",
    "FragmentClassification",
    "MolecularIdentity",
    "PhysicochemicalDescriptors",
    "ProcessedCompound",
    "StandardizedStructure",
    "StructureFormat",
    "assess_drug_likeness",
    "classify_fragments",
    "compute_descriptors",
    "compute_identity",
    "compute_morgan_fingerprint",
    "parse_molecule",
    "process_structure",
    "standardize",
    "stereo_completeness",
]
