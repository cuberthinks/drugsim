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


_UNIDENTIFIED = CompoundIdentityResult(identity_status="unidentified")


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


def resolve_identity(
    inchikey_full: str, snapshot: dict[str, CompoundIdentityRecord]
) -> CompoundIdentityResult:
    """Resolve one structure's identity against the loaded snapshot.

    Pure, synchronous, zero I/O -- safe to call for every prediction.
    """
    record = snapshot.get(inchikey_full)
    if record is None:
        return _UNIDENTIFIED
    return CompoundIdentityResult(
        identity_status="identified",
        compound_name=record.preferred_name,
        synonyms=record.synonyms or None,
        identifiers={"pubchem_cid": record.pubchem_cid},
        description=record.description or "Verified description unavailable.",
        description_source=record.description_source,
        source="PubChem",
        retrieved_at=record.retrieved_at,
    )
