"""Duplicate detection.

Phase 1 Step 8 §3: intra-source duplicates merge on exact InChIKey; cross-source
duplicates (chiefly ChEMBL vs BindingDB, which overlap heavily) match on
parent InChIKey + target + endpoint + shared literature reference. Neither
case deletes a record — duplicates are grouped and one is marked
representative, preserving every source row for provenance (P8).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import Optional

__all__ = ["DuplicateGroup", "find_compound_duplicates", "find_measurement_duplicates"]


@dataclass(frozen=True)
class DuplicateGroup:
    """A set of records identified as referring to the same underlying entity.

    Attributes:
        key: The identity key duplicates were grouped on.
        record_ids: All record identifiers in the group, in input order.
        representative_id: The chosen representative — see
            :func:`find_measurement_duplicates` for the selection rule.
    """

    key: str
    record_ids: tuple[str, ...]
    representative_id: str


def find_compound_duplicates(
    records: list[tuple[str, str]],
) -> list[DuplicateGroup]:
    """Group compound records sharing an exact InChIKey.

    Args:
        records: ``(record_id, inchikey_full)`` pairs. Only records with 2+
            entries sharing a key are returned as groups — singletons are not
            duplicates and are omitted.

    Returns:
        One :class:`DuplicateGroup` per InChIKey with more than one record.
        The first-seen record is the representative — arbitrary but
        deterministic, since compound records carry no inherent quality
        ranking the way measurements do (Phase 1 Step 8 §8.2: "merge into one
        compound_uid, retaining all source_record_id values").
    """
    by_key: dict[str, list[str]] = defaultdict(list)
    for record_id, inchikey in records:
        by_key[inchikey].append(record_id)

    return [
        DuplicateGroup(key=key, record_ids=tuple(ids), representative_id=ids[0])
        for key, ids in by_key.items()
        if len(ids) > 1
    ]


@dataclass(frozen=True)
class MeasurementRecord:
    """The fields needed to detect a cross-source measurement duplicate.

    Attributes:
        record_id: Unique identifier for this measurement row.
        parent_inchikey: Compound identity, salt-stripped.
        target_or_endpoint: Target accession (bioactivity) or endpoint id
            (ADMET/toxicology) — whichever applies.
        reference: DOI or PMID, if known. A shared reference is the strongest
            duplicate signal — it usually means both sources abstracted the
            same publication.
        license_tier: Used to prefer the least-restrictive representative
            when a duplicate group spans tiers (a free reduction in
            ShareAlike exposure, since the values are identical).
        confidence_score: Used as a tiebreaker among same-tier candidates.
    """

    record_id: str
    parent_inchikey: str
    target_or_endpoint: str
    reference: Optional[str] = None
    license_tier: str = "red"
    confidence_score: float = 0.0


_TIER_RESTRICTIVENESS = {"green": 0, "amber": 1, "red": 2, "black": 3}


def find_measurement_duplicates(records: list[MeasurementRecord]) -> list[DuplicateGroup]:
    """Group measurement records referring to the same underlying fact.

    Matches on ``parent_inchikey + target_or_endpoint + reference`` when a
    reference is present (the strong signal), or
    ``parent_inchikey + target_or_endpoint`` alone when it is not (a weaker
    signal, used because ChEMBL and BindingDB's overlap is large enough that
    grouping by structure+target alone still catches most of it — Phase 1
    Step 1 verified this overlap is substantial).

    Args:
        records: Candidate measurement records.

    Returns:
        Duplicate groups. The representative is chosen by the **least
        restrictive licence tier** first (a free reduction in ShareAlike
        exposure when values are identical), then by highest confidence
        score.
    """
    with_reference: dict[str, list[MeasurementRecord]] = defaultdict(list)
    without_reference: dict[str, list[MeasurementRecord]] = defaultdict(list)

    for record in records:
        if record.reference:
            key = f"{record.parent_inchikey}|{record.target_or_endpoint}|{record.reference}"
            with_reference[key].append(record)
        else:
            key = f"{record.parent_inchikey}|{record.target_or_endpoint}"
            without_reference[key].append(record)

    groups: list[DuplicateGroup] = []
    for key, group_records in [*with_reference.items(), *without_reference.items()]:
        if len(group_records) <= 1:
            continue
        representative = min(
            group_records,
            key=lambda r: (_TIER_RESTRICTIVENESS.get(r.license_tier, 99), -r.confidence_score),
        )
        groups.append(
            DuplicateGroup(
                key=key,
                record_ids=tuple(r.record_id for r in group_records),
                representative_id=representative.record_id,
            )
        )
    return groups
