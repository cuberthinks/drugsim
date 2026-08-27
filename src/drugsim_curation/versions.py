"""Version constants for the curation pipeline.

Bumped whenever a rule in :mod:`drugsim_curation` changes in a way that
would produce different output for the same raw input — the same
discipline as ``drugsim_chem.standardize.STANDARDIZATION_PIPELINE_VERSION``.
Every ledger row and curation report records the version that produced it,
so a change in output can always be attributed to a specific rule change
rather than left ambiguous.
"""

from __future__ import annotations

__all__ = ["CURATION_PIPELINE_VERSION"]

CURATION_PIPELINE_VERSION = "v1"
