"""DrugSim raw data acquisition: download, checksum, immutable landing.

Implements the Z1 landing zone from Phase 1 Step 2 §3: bytes acquired from an
external source are written once, checksummed, and never edited. A correction is
a new snapshot, replayable from the original bytes — never an in-place edit.

Modules:
    checksums: Streaming SHA-256, so multi-gigabyte files never load into memory
        whole just to be verified.
    downloader: HTTP download with retry and streaming checksum computation.
    landing: The immutable, write-once object-storage abstraction (Z1).
    snapshot: Glue between a completed download and an ``ingestion_snapshot`` row.
"""

from __future__ import annotations

__all__: list[str] = []
