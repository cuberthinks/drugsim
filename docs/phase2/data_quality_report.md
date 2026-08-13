# DrugSim Phase 2 — Data Quality Report

Generated: 2026-08-08T15:13:40+00:00
Toolchain: `rdkit-2025.03.3__python-3.9.6__stdpipe-v1`
RDKit: 2025.03.3 · Standardisation pipeline: v1 · Descriptor spec: v1

## Dataset processed

- Reference compound set: `datasets/golden/compounds.csv` (28 records, hand-curated for edge-case coverage — not an external licensed source)
- No large-scale external source (ChEMBL/BindingDB/PDB bulk) was ingested end-to-end in this environment (no Docker/Postgres available to load into); Sprint 2.4's downloader was verified against one real file (RCSB `1CRN.pdb`) over a live network connection, but that is a mechanism check, not a dataset ingest.

## ETL outcome

- Records attempted: 28
- Processed successfully: 28
- Quarantined (StructureError): 0

## Standardisation

- Flagged mixtures (no descriptors computed): 0
- Whole-salt structures (no organic parent): 1
- Salt-stripped to a single parent: 3
- Charge-neutralised: 4

## Duplicate detection

- Duplicate InChIKey groups found: 0 (expected 0 — the reference set is curated to be distinct)

## Descriptors & drug-likeness (n=28, mixtures excluded)

- MW (g/mol): mean 140.4, min 16.0, max 563.1
- LogP (Crippen): mean 1.25, min -5.99, max 15.85
- Lipinski pass: 27/28
- PAINS-flagged: 1/28
- Brenk-flagged: 5/28

## Licence audit

- Sources checked: 11
- Result: PASS
- Errors: 0, Warnings: 2
  - WARN: LC-04 drugcentral: marked stale — Site indicates 2023 as current release; cadence appears to have slowed
  - WARN: dailymed: figures unverified — Verify SPL record count on an unfiltered network

## Not exercised this run

- **Measurement aggregation / discordance flags** (`drugsim_quality.aggregation`) — implemented and unit-tested (`tests/unit/test_aggregation.py`), but no real bioactivity measurement dataset was ingested this phase to run it against.
- **Empirical unit verification** (`drugsim_quality.unit_verification`) — same reason: no measurement dataset to verify units on.
- **Bulk load into PostgreSQL** — `src/drugsim_db/bulk_load.py` is implemented and unit-tested against real pipeline output; the insert path is exercised in `tests/constraints/test_bulk_load_integration.py`, which requires Docker and did not run in this environment.

