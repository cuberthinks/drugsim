"""Chemical structure standardisation.

Implements the fixed pipeline order from Phase 1 Step 8 §S4: cleanup/normalise
→ strip salts/solvates → neutralise charges → canonical tautomer (stored
separately, never overwriting the standardised structure) → identity.

**Salt stripping does not use RDKit's ``FragmentParent`` or
``LargestFragmentChooser``.** Verified directly while writing this module:
both pick ``[Cl-]`` as "the parent" of plain ``[Na+].[Cl-]`` (arbitrary
tie-breaking with no organic parent to prefer) and arbitrarily pick one
fragment as "the parent" of a genuine two-organic-fragment mixture
(``CCO.CCN``) rather than flagging it as ambiguous. Both are exactly the
edge cases Phase 1 Step 4 §2.2 named as required special handling: a
molecule that *is* a salt must not be reduced to one ion, and a genuine
mixture must be flagged, not silently resolved by picking one component.
This module's :func:`classify_fragments` implements the classification Phase 1
called for; RDKit's ``Uncharger``, ``CanonicalTautomer`` and ``Normalize`` are
reused as-is for the steps where they are not the wrong tool.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from rdkit import Chem, rdBase
from rdkit.Chem.MolStandardize import rdMolStandardize
from rdkit.Chem.SaltRemover import SaltRemover

from drugsim_core.errors import StructureError

__all__ = [
    "STANDARDIZATION_PIPELINE_VERSION",
    "FragmentClassification",
    "StandardizedStructure",
    "classify_fragments",
    "standardize",
]

#: Version of this standardisation pipeline. Bump on ANY behavioural change —
#: it participates in toolchain_id and therefore feature_set_id (ADR-005).
STANDARDIZATION_PIPELINE_VERSION = "v1"

_SALT_REMOVER = SaltRemover()
_UNCHARGER = rdMolStandardize.Uncharger()
_CLEANUP_PARAMS = rdMolStandardize.CleanupParameters()


@dataclass(frozen=True)
class FragmentClassification:
    """The result of classifying a multi-fragment structure's components.

    Attributes:
        parent: The identified single organic parent, or ``None`` if none
            could be identified (either every fragment is a recognised salt,
            or multiple non-salt fragments remain).
        is_mixture: True when two or more non-salt fragments remain — a
            genuine mixture, not a salt form of a single active component.
        component_count: Total fragment count in the original structure.
        salt_fragment_count: How many fragments were recognised salts.
    """

    parent: Chem.Mol | None
    is_mixture: bool
    component_count: int
    salt_fragment_count: int


def _is_recognised_salt(fragment: Chem.Mol) -> bool:
    """Whether a fragment matches one of RDKit's default salt/counterion patterns.

    Args:
        fragment: A single connected component, unsanitised is acceptable.

    Returns:
        True if the fragment matches a salt pattern exactly (same atom
        count — a substructure match alone would also flag a salt pattern
        that merely appears WITHIN a larger, non-salt fragment).
    """
    for pattern in _SALT_REMOVER.salts:
        if fragment.GetNumAtoms() == pattern.GetNumAtoms() and fragment.HasSubstructMatch(pattern):
            return True
    return False


def classify_fragments(mol: Chem.Mol) -> FragmentClassification:
    """Classify a (possibly multi-component) structure's fragments.

    Args:
        mol: A sanitised molecule, possibly with multiple disconnected
            components (e.g. a salt or solvate).

    Returns:
        The classification. See Phase 1 Step 4 §2.2 for the policy this
        implements:

        * 1 fragment → trivially the parent, nothing to strip.
        * N fragments, exactly 1 non-salt → that fragment is the parent;
          the others are salts/solvates to strip.
        * N fragments, 0 non-salt (the whole structure is composed of
          recognised salts, e.g. plain NaCl) → no parent identified;
          **the original structure must be retained**, not reduced to one
          ion — this is the case RDKit's own ``FragmentParent`` gets wrong.
        * N fragments, ≥2 non-salt → genuine mixture; no single parent.
    """
    fragments = Chem.GetMolFrags(mol, asMols=True, sanitizeFrags=False)
    if len(fragments) == 1:
        return FragmentClassification(
            parent=mol, is_mixture=False, component_count=1, salt_fragment_count=0
        )

    salt_flags = [_is_recognised_salt(frag) for frag in fragments]
    non_salt_fragments = [frag for frag, is_salt in zip(fragments, salt_flags) if not is_salt]
    salt_count = sum(salt_flags)

    if len(non_salt_fragments) == 1:
        parent = non_salt_fragments[0]
        Chem.SanitizeMol(parent)
        return FragmentClassification(
            parent=parent, is_mixture=False, component_count=len(fragments), salt_fragment_count=salt_count
        )

    if len(non_salt_fragments) == 0:
        # Every fragment is a recognised salt/ion — there is no organic parent
        # to isolate. Retaining `mol` (the whole original structure) rather
        # than an arbitrary single ion is the point of this branch.
        return FragmentClassification(
            parent=None, is_mixture=False, component_count=len(fragments), salt_fragment_count=salt_count
        )

    # Two or more non-salt fragments: a genuine mixture, not a salt form.
    return FragmentClassification(
        parent=None, is_mixture=True, component_count=len(fragments), salt_fragment_count=salt_count
    )


@dataclass(frozen=True)
class StandardizedStructure:
    """The output of the full standardisation pipeline.

    Attributes:
        standardized_mol: The structure after cleanup, salt stripping (if a
            single parent was found) and charge neutralisation. This is what
            downstream identity/descriptor computation should consume.
        parent_mol: Same as ``standardized_mol`` when a parent was
            identified; ``None`` if the structure is a mixture or is entirely
            composed of recognised salts.
        canonical_tautomer_mol: RDKit's canonical tautomer of
            ``standardized_mol``, computed but never substituted in place of
            it — tautomer canonicalisation is convention-dependent and
            changes between RDKit versions (Phase 1 Step 8 §S4); overwriting
            the standardised form would make disagreements unresolvable.
        is_mixture: See :class:`FragmentClassification`.
        component_count: Total fragment count in the original structure —
            matches ``compound.component_count`` (Phase 1 Step 4 §2.2), e.g.
            ``2`` for a hydrochloride salt or plain NaCl, ``1`` for a
            single-component structure.
        flags: Machine-readable record of which steps actually did something,
            matching ``compound.standardization_flags`` (Phase 1 Step 3 §4.1).
    """

    standardized_mol: Chem.Mol
    parent_mol: Chem.Mol | None
    canonical_tautomer_mol: Chem.Mol
    is_mixture: bool
    component_count: int
    flags: tuple[str, ...] = field(default_factory=tuple)


def standardize(mol: Chem.Mol) -> StandardizedStructure:
    """Run the full standardisation pipeline on a parsed, sanitised molecule.

    Fixed order (Phase 1 Step 8 §S4): cleanup/normalise functional groups →
    classify fragments and strip salts → neutralise charges → compute
    canonical tautomer (kept separate).

    Args:
        mol: A sanitised molecule (see
            :func:`drugsim_chem.parsing.parse_molecule`).

    Returns:
        The standardisation result.

    Raises:
        StructureError: If cleanup or charge neutralisation raises. Verified
            empirically that this is rare once a molecule has already
            survived :func:`~drugsim_chem.parsing.parse_molecule`'s
            sanitisation — but ``rdMolStandardize`` operations are not
            guaranteed to succeed on every sanitisable structure (certain
            organometallics in particular), so this is not treated as
            unreachable.

    Idempotency (a property this module's tests assert, not merely claim):
        ``standardize(standardize(mol).standardized_mol).standardized_mol``
        must be structurally identical to
        ``standardize(mol).standardized_mol`` — re-running standardisation on
        an already-standardised structure must not change it further. This is
        required because Sprint 2.5's golden-set regression and any future
        re-ingestion depend on the pipeline being a true idempotent function,
        not merely convergent after enough passes.
    """
    # rdMolStandardize prints "Initializing X / Running X" progress chatter for
    # Cleanup/Uncharger/CanonicalTautomer via a mechanism that bypasses the
    # rdApp.info category-based suppression configured in
    # drugsim_chem/__init__.py (verified directly: DisableLog("rdApp.info")
    # does not silence it). rdBase.BlockLogs() is the blunt instrument that
    # does — scoped to this call only, so it does not affect parsing.py's
    # unrelated need to actually CAPTURE (not suppress) real error text via
    # redirect_stderr elsewhere in this package.
    with rdBase.BlockLogs():
        return _standardize_impl(mol)


def _standardize_impl(mol: Chem.Mol) -> StandardizedStructure:
    """The actual standardisation logic, run inside :func:`standardize`'s
    ``BlockLogs`` scope. Kept as a separate function so that scope is exactly
    "all of standardisation", not accidentally narrower or broader.
    """
    flags: list[str] = []

    try:
        working = rdMolStandardize.Cleanup(mol)
    except Exception as exc:
        msg = "standardisation cleanup failed"
        raise StructureError(msg, detail=str(exc)) from exc
    if Chem.MolToSmiles(working) != Chem.MolToSmiles(mol):
        flags.append("normalized")

    classification = classify_fragments(working)

    if classification.is_mixture:
        # No further processing on an unresolved mixture: charge/tautomer
        # operations on a multi-component structure with no identified
        # parent would be operating on the wrong thing.
        return StandardizedStructure(
            standardized_mol=working,
            parent_mol=None,
            canonical_tautomer_mol=working,
            is_mixture=True,
            component_count=classification.component_count,
            flags=tuple([*flags, "flagged_as_mixture"]),
        )

    if classification.parent is not None and classification.salt_fragment_count > 0:
        working = classification.parent
        flags.append("salt_stripped")
    elif classification.parent is None and classification.component_count > 1:
        # Whole structure is composed of recognised salts (e.g. plain NaCl) —
        # retain the original multi-component structure rather than reducing
        # to a single arbitrary ion.
        flags.append("retained_whole_salt_no_organic_parent")

    try:
        neutralized = _UNCHARGER.uncharge(working)
    except Exception as exc:
        msg = "charge neutralisation failed"
        raise StructureError(msg, detail=str(exc)) from exc
    if Chem.MolToSmiles(neutralized) != Chem.MolToSmiles(working):
        flags.append("charge_neutralised")
    working = neutralized

    try:
        canonical_tautomer = rdMolStandardize.CanonicalTautomer(working)
    except Exception as exc:
        msg = "tautomer canonicalisation failed"
        raise StructureError(msg, detail=str(exc)) from exc
    if Chem.MolToSmiles(canonical_tautomer) != Chem.MolToSmiles(working):
        flags.append("tautomer_canonicalised_available")

    if not flags:
        flags.append("unchanged")

    return StandardizedStructure(
        standardized_mol=working,
        # A whole-salt structure (classification.parent is None, is_mixture is
        # False — e.g. plain NaCl) has no identified organic parent either, and
        # must report None here too. Using `not is_mixture` alone was WRONG: it
        # left this True for the whole-salt case, contradicting this class's
        # own docstring and silently giving compound.parent_smiles/
        # parent_inchikey a value for a structure that has no actual parent.
        parent_mol=working if classification.parent is not None else None,
        canonical_tautomer_mol=canonical_tautomer,
        is_mixture=False,
        component_count=classification.component_count,
        flags=tuple(flags),
    )
