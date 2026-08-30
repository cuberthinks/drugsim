"""Compound identity resolution: name a structure without inventing anything.

**Never a live third-party call in the request path.** DrugSim's live
`/predict` service has an existing, tested, audited guarantee that no
third-party service ever receives a submitted structure
(`docs/privacy/confidentiality-audit.md` Sec 8). This package preserves
that: identity data is fetched once, offline, by
`scripts/build_compound_identity_snapshot.py`, for compounds already in
DrugSim's own approved datasets, and written to the committed
`data/compound_identity_snapshot.json`. The live service only ever does a
local, in-memory dictionary lookup keyed by InChIKey -- no network, no new
runtime dependency.

A compound absent from the snapshot is reported as `identity_status =
"unidentified"`, never guessed at. This is the expected, normal outcome
for a genuinely novel molecule, not a failure -- prediction proceeds
exactly as if the compound had been identified.
"""

from __future__ import annotations

from drugsim_identity.snapshot import (
    CompoundIdentityRecord,
    CompoundIdentityResult,
    load_identity_snapshot,
    resolve_identity,
)

__all__ = [
    "CompoundIdentityRecord",
    "CompoundIdentityResult",
    "load_identity_snapshot",
    "resolve_identity",
]
