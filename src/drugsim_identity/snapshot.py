"""Load and query the offline compound-identity snapshot.

Deliberately the only file the live `/predict` path touches from this
package: `load_identity_snapshot` does one file read at process start
(mirroring `ModelBundle`'s load-once-and-cache pattern), and
`resolve_identity` after that is a plain dict lookup -- no I/O, no
exceptions to catch, safe to call inline in the request path.

The snapshot itself is built offline by
`scripts/build_compound_identity_snapshot.py`, which is the only place in
this feature that ever calls PubChem.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

__all__ = [
    "CompoundIdentityRecord",
    "CompoundIdentityResult",
    "build_skeleton_index",
    "load_identity_snapshot",
    "resolve_identity",
]


@dataclass(frozen=True)
class CompoundIdentityRecord:
    """One compound's verified identity, exactly as PubChem returned it.

    Every field traces back to a real API response captured by the build
    script -- nothing here is written by hand for a specific compound.
    """

    inchikey_full: str
    pubchem_cid: str
    preferred_name: str
    synonyms: tuple[str, ...]
    description: Optional[str]
    description_source: Optional[str]
    retrieved_at: str
    license_spdx: str


@dataclass(frozen=True)
class CompoundIdentityResult:
    """The identity outcome attached to one prediction.

    ``identity_status == "unidentified"`` is the expected, non-error
    outcome for a compound outside the snapshot -- every other field is
    ``None`` in that case, never a guess.
    """

    identity_status: str  # "identified" | "unidentified"
    compound_name: Optional[str] = None
    synonyms: Optional[tuple[str, ...]] = None
    identifiers: Optional[dict[str, str]] = None
    description: Optional[str] = None
    description_source: Optional[str] = None
    source: Optional[str] = None
    retrieved_at: Optional[str] = None
    #: How the match was made: ``"exact"`` (full InChIKey) or ``"skeleton"``
    #: (connectivity-only). ``None`` when unidentified. A skeleton match is
    #: deliberately reported as a *different kind* of match, never merged into
    #: the exact case -- see ``match_caveat``.
    match_type: Optional[str] = None
    #: Present only for skeleton matches: the reason this identity is weaker
    #: than an exact one. Never generated text -- a fixed, reviewed string.
    match_caveat: Optional[str] = None


_UNIDENTIFIED = CompoundIdentityResult(identity_status="unidentified")

#: Fixed, reviewed caveat text for connectivity-only matches. The InChIKey
#: skeleton encodes constitution but not stereochemistry, isotopic labelling
#: or protonation state, and enantiomers can differ sharply in pharmacology.
_SKELETON_CAVEAT = (
    "Matched on molecular connectivity only. Stereochemistry, isotopic "
    "labelling and protonation state were not confirmed, and may differ from "
    "the named compound."
)


def load_identity_snapshot(path: Path) -> dict[str, CompoundIdentityRecord]:
    """Load the committed snapshot into an InChIKey-keyed dict.

    Args:
        path: Path to the snapshot JSON (see ``data/compound_identity_
            snapshot.json`` for the shape).

    Returns:
        An empty dict if the file does not exist -- a missing snapshot
        means every compound resolves as unidentified, never an error at
        startup (the feature degrades gracefully, it does not crash the
        service).
    """
    if not path.exists():
        return {}
    raw = json.loads(path.read_text(encoding="utf-8"))
    records: dict[str, CompoundIdentityRecord] = {}
    for entry in raw.get("compounds", []):
        record = CompoundIdentityRecord(
            inchikey_full=entry["inchikey_full"],
            pubchem_cid=entry["pubchem_cid"],
            preferred_name=entry["preferred_name"],
            synonyms=tuple(entry.get("synonyms", [])),
            description=entry.get("description"),
            description_source=entry.get("description_source"),
            retrieved_at=entry["retrieved_at"],
            license_spdx=entry["license_spdx"],
        )
        records[record.inchikey_full] = record
    return records


def build_skeleton_index(
    snapshot: dict[str, CompoundIdentityRecord],
) -> dict[str, tuple[CompoundIdentityRecord, ...]]:
    """Index snapshot records by InChIKey skeleton (first 14 characters).

    Built once per process alongside the snapshot itself. Skeletons that map
    to more than one record are kept as multi-element tuples on purpose:
    ``resolve_identity`` must be able to *see* the ambiguity in order to
    refuse it, rather than silently receiving one arbitrary winner.

    Measured on the committed snapshot (see
    ``docs/scientific-coverage/compound-identity-coverage.md``): 960 compounds
    span 952 skeletons, and all 7 collisions are stereoisomer sets.
    """
    index: dict[str, list[CompoundIdentityRecord]] = {}
    for record in snapshot.values():
        index.setdefault(record.inchikey_full[:14], []).append(record)
    return {skeleton: tuple(records) for skeleton, records in index.items()}


def _identified(record: CompoundIdentityRecord, match_type: str) -> CompoundIdentityResult:
    return CompoundIdentityResult(
        identity_status="identified",
        compound_name=record.preferred_name,
        synonyms=record.synonyms or None,
        identifiers={"pubchem_cid": record.pubchem_cid},
        description=record.description or "Verified description unavailable.",
        description_source=record.description_source,
        source="PubChem",
        retrieved_at=record.retrieved_at,
        match_type=match_type,
        match_caveat=_SKELETON_CAVEAT if match_type == "skeleton" else None,
    )


def resolve_identity(
    inchikey_full: str,
    snapshot: dict[str, CompoundIdentityRecord],
    skeleton_index: Optional[dict[str, tuple[CompoundIdentityRecord, ...]]] = None,
) -> CompoundIdentityResult:
    """Resolve one structure's identity against the loaded snapshot.

    Resolution order:

    1. exact full-InChIKey match -- ``match_type="exact"``;
    2. **unambiguous** skeleton match, only when ``skeleton_index`` is
       supplied -- ``match_type="skeleton"``, carrying ``match_caveat``;
    3. otherwise unidentified.

    A skeleton shared by more than one record resolves as **unidentified**,
    not as a guess between them. Reporting the wrong enantiomer's name would
    be worse than reporting no name: "unidentified" is an honest, expected
    outcome, and the compound still predicts either way.

    ``skeleton_index`` is optional so existing two-argument callers keep
    exact-match-only behaviour unchanged.

    Pure, synchronous, zero I/O -- safe to call for every prediction.
    """
    record = snapshot.get(inchikey_full)
    if record is not None:
        return _identified(record, "exact")

    if skeleton_index:
        candidates = skeleton_index.get(inchikey_full[:14])
        if candidates and len(candidates) == 1:
            return _identified(candidates[0], "skeleton")

    return _UNIDENTIFIED
