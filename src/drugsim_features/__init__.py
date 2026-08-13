"""DrugSim feature store: content-addressed descriptor storage.

Features are immutable Parquet keyed by ``compound_uid`` and addressed by::

    feature_set_id = sha256(descriptor_spec_version || rdkit_version
                            || standardization_pipeline_version
                            || sorted(descriptor_names))

Content addressing is not a convenience. RDKit descriptor values change between
releases, so features computed under different toolchains are not interchangeable.
Without the toolchain in the feature identity, models drift silently and results
stop being reproducible (ADR-005).

Only :func:`compute_feature_set_id` — the identity computation itself — is
implemented here in Phase 2. It exists now because ``descriptor_spec.feature_set_id``
is a NOT NULL UNIQUE column the bulk loader (Sprint 2.7) must populate before any
``compound_descriptor`` row can reference that spec version; the Parquet-backed
feature store this module is named for is ML infrastructure and out of Phase 2's
scope (deferred to Phase 3).
"""

from __future__ import annotations

import hashlib

__all__ = ["compute_feature_set_id"]


def compute_feature_set_id(
    *,
    descriptor_spec_version: str,
    rdkit_version: str,
    standardization_pipeline_version: str,
    descriptor_names: list[str],
) -> str:
    """Compute the content-addressed feature-set identifier (ADR-005).

    Pure and deterministic: identical inputs always produce the identical id,
    which is the entire point — it lets a mismatch between a model's training
    feature set and a serving-time feature set be detected as a hard equality
    check rather than inferred.

    Args:
        descriptor_spec_version: The ``descriptor_spec`` row's version string.
        rdkit_version: RDKit version descriptors were computed under.
        standardization_pipeline_version: ``drugsim_chem`` standardisation
            pipeline version descriptors were computed under.
        descriptor_names: The descriptor columns this spec covers. Sorted
            internally so caller-side ordering never affects the id.

    Returns:
        A 64-character lowercase hex SHA-256 digest, matching the
        ``sha256_hex`` domain (``database/ddl/01_domains_and_types.sql``).
    """
    digest_input = "||".join(
        [
            descriptor_spec_version,
            rdkit_version,
            standardization_pipeline_version,
            *sorted(descriptor_names),
        ]
    )
    return hashlib.sha256(digest_input.encode("utf-8")).hexdigest()
