"""Assay-context enrichment: organism, cell type, and paradigm classification.

Section 7 of the curation spec asks for assay context (organism, cell type,
assay type, tissue, concentration, temperature, pH, exposure duration,
method) to be preserved where available, and *not* combined across
materially different experimental contexts just because the endpoint name
matches. Two things are true about ChEMBL activity data for these targets,
verified directly against the raw pulls rather than assumed:

* ``assay_type`` (ChEMBL's own B/F/T/A code), ``assay_chembl_id``,
  ``document_chembl_id``/``document_year`` are already present on every raw
  activity row.
* Organism, cell type, and a genuine assay-paradigm classification (binding
  displacement vs. functional electrophysiology vs. functional flux, etc.)
  require one bulk ``assay.json`` call per target, keyed by
  ``assay_chembl_id`` -- these are not in the activity-level pull.

This module re-derives that second lookup (the exact pattern
``models/admet/herg_inhibition/audit_assay_heterogeneity.py`` already
proved out as a one-off Phase 3.5 audit) as reusable, cached, generic-over-
target code. ``audit_assay_heterogeneity.py`` itself is left untouched --
duplicating ~40 lines is the accepted tradeoff for not modifying a working,
already-shipped script.

**Fields that are genuinely never available from ChEMBL for these
targets -- tissue, exact concentration, temperature, pH, exposure
duration, detailed method -- are never fabricated.** Callers should surface
:data:`ASSAY_CONTEXT_UNAVAILABLE_FIELDS` directly rather than inventing
empty-looking columns for them.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

__all__ = [
    "ASSAY_CONTEXT_UNAVAILABLE_FIELDS",
    "AssayMetadata",
    "classify_assay_paradigm",
    "fetch_assay_metadata",
    "load_assay_cache",
]

#: Experimental context dimensions this module does not extract today,
#: beyond the coarse paradigm classification and ``assay_tissue`` below.
#: Verified empirically against every hERG-target assay (CHEMBL240, 4,829
#: assays), not assumed: none of these are top-level fields on ChEMBL's
#: assay record. A structured ``assay_parameters`` array can occasionally
#: carry a dose/concentration/temperature-style value (35/4829 = 0.7% of
#: hERG assays had any entry at all, and most of those were an in-vivo
#: DOSE value, not an in-vitro assay condition) -- parsing that sparse,
#: heterogeneously-typed array is a real future extension, not attempted
#: in this version. Documented explicitly rather than represented as
#: silently-empty columns, and not conflated with "impossible to obtain."
ASSAY_CONTEXT_UNAVAILABLE_FIELDS = (
    "concentration",
    "temperature",
    "pH",
    "exposure_duration",
    "method",
)


def classify_assay_paradigm(description: Optional[str]) -> str:
    """Classify an assay's experimental paradigm from its free-text description.

    Re-derived verbatim from
    ``audit_assay_heterogeneity.py::_classify`` -- ChEMBL's own
    ``assay_type`` field is not a reliable paradigm partition (a "Binding
    affinity" assay can be filed as type T), so paradigm is determined from
    the description text instead.

    Args:
        description: The assay's ``description`` field from ChEMBL, or
            ``None``.

    Returns:
        One of ``"functional_electrophysiology"``,
        ``"functional_flux_fluorescence"``, ``"binding_displacement"``,
        ``"ambiguous_generic_inhibition"``, or ``"other_unclassified"``.
    """
    text = (description or "").lower()
    if any(kw in text for kw in ["patch clamp", "patch-clamp", "voltage clamp", "ikr current", "delayed rectifying"]):
        return "functional_electrophysiology"
    if any(kw in text for kw in ["flipr", "flux assay", "thallium", "fluorescence", "rb+ flux", "86rb"]):
        return "functional_flux_fluorescence"
    if any(kw in text for kw in ["binding", "displacement", "radioligand", "[3h]", "mk499", "mk-499", "astemizole binding"]):
        return "binding_displacement"
    if any(kw in text for kw in ["inhibition", "activity", "block"]):
        return "ambiguous_generic_inhibition"
    return "other_unclassified"


@dataclass(frozen=True)
class AssayMetadata:
    """Enriched context for one ``assay_chembl_id``.

    Attributes:
        assay_chembl_id: The ChEMBL assay identifier.
        assay_organism: The assay's organism, if ChEMBL reports one.
        assay_cell_type: The assay's cell type, if reported.
        assay_tissue: The assay's tissue, if reported. Genuinely present on
            ChEMBL's schema but populated for well under 1% of hERG-target
            assays in practice (verified: 4 of 4,829) -- carried through
            when present rather than omitted as though the field did not
            exist.
        confidence_score: ChEMBL's own target-assignment confidence score.
        paradigm: This module's classification, see
            :func:`classify_assay_paradigm`.
    """

    assay_chembl_id: str
    assay_organism: Optional[str]
    assay_cell_type: Optional[str]
    assay_tissue: Optional[str]
    confidence_score: Optional[int]
    paradigm: str


def load_assay_cache(cache_path: Path) -> dict[str, dict[str, Any]]:
    """Load a previously-written assay-metadata cache, or an empty dict.

    Args:
        cache_path: Path to a JSON file mapping ``assay_chembl_id`` to the
            raw ChEMBL assay record.

    Returns:
        The cached mapping, or ``{}`` if the file does not exist yet.
    """
    if not cache_path.exists():
        return {}
    return json.loads(cache_path.read_text(encoding="utf-8"))


def fetch_assay_metadata(
    target_chembl_id: str,
    assay_ids: set[str],
    *,
    cache_path: Path,
    http_client: Any = None,
) -> dict[str, AssayMetadata]:
    """Resolve assay metadata for ``assay_ids``, using and updating a local cache.

    Args:
        target_chembl_id: The ChEMBL target these assays belong to (a bulk
            fetch is scoped to one target at a time, matching how ChEMBL's
            ``assay.json`` endpoint is paginated).
        assay_ids: The ``assay_chembl_id`` values actually referenced by the
            raw pull being curated -- only these are returned, even though
            the bulk fetch retrieves every assay for the target.
        cache_path: Where to read/write the local JSON cache. Passing a
            pre-populated cache and no live network access (see
            ``http_client``) makes this function usable offline in tests.
        http_client: An ``httpx``-compatible client with a ``.get(url,
            params=..., timeout=...)`` method returning a response whose
            ``.json()`` matches ChEMBL's assay-list shape. If ``None``,
            only the cache is consulted -- any requested ``assay_ids`` not
            already cached are simply absent from the result, never
            fabricated.

    Returns:
        A mapping from ``assay_chembl_id`` to :class:`AssayMetadata`,
        containing only the subset of ``assay_ids`` that were resolvable
        from the cache and/or a live fetch.
    """
    cache = load_assay_cache(cache_path)
    missing = {aid for aid in assay_ids if aid not in cache}

    if missing and http_client is not None:
        offset = 0
        while True:
            resp = http_client.get(
                "https://www.ebi.ac.uk/chembl/api/data/assay.json",
                params={"target_chembl_id": target_chembl_id, "limit": 1000, "offset": offset},
                timeout=30.0,
            )
            page = resp.json()
            for record in page["assays"]:
                cache[record["assay_chembl_id"]] = record
            if page["page_meta"]["next"] is None:
                break
            offset += 1000
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(cache, indent=2, sort_keys=True), encoding="utf-8")

    result: dict[str, AssayMetadata] = {}
    for aid in assay_ids:
        record = cache.get(aid)
        if record is None:
            continue
        result[aid] = AssayMetadata(
            assay_chembl_id=aid,
            assay_organism=record.get("assay_organism"),
            assay_cell_type=record.get("assay_cell_type"),
            assay_tissue=record.get("assay_tissue"),
            confidence_score=record.get("confidence_score"),
            paradigm=classify_assay_paradigm(record.get("description")),
        )
    return result
