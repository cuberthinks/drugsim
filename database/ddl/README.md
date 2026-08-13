# DrugSim Canonical DDL

**Status:** Sprint 2.2 initial schema. Mirrors Phase 1 Step 3 (relational schema),
with the Step 4 §1 correction applied and the Step 4/6/7 *extension* tables
deliberately deferred — see "Scope decisions" below.

## Relationship to `database/migrations/`

For this initial release, the SQL in this directory and the SQL embedded in
`database/migrations/versions/000*.py` are **byte-identical by construction** — the
migration files were generated from these files at authoring time.

**This is a one-time bootstrapping arrangement, not the ongoing workflow.** Migrations
must be immutable once applied (forward-only, TDS §8.4): a migration's content must
never depend on a file that could change after the migration ships, or replaying
migration history on a fresh database would silently apply different SQL than what
originally ran in production.

**From the next migration onward:** write the migration directly (SQL inline in the
`.py` file, self-contained). Regenerate `database/ddl/*.sql` **after** the migration
lands, as a schema snapshot (`pg_scripts/regenerate_schema_snapshot.sh`, `pg_dump
--schema-only`), so this directory remains a human-readable "what does the schema
look like now" reference without ever being a runtime dependency of the migration
history.

## Files

| File | Domain | Phase 1 reference |
|---|---|---|
| `00_extensions.sql` | PostgreSQL extensions | ADR-003 |
| `01_domains_and_types.sql` | Shared domains and enums | Step 3 §2 |
| `02_governance.sql` | Sources, snapshots, toolchain, users, audit, signatures | Step 3 §3, regulatory addendum |
| `03_chemistry.sql` | Compound identity, descriptors, drug-likeness, splits | Step 3 §4, Step 4 §1 correction |
| `04_biology.sql` | Proteins, genes, targets, diseases, pathways, drug classes | Step 3 §5 |
| `05_evidence.sql` | Endpoints, assays, measurements (partitioned) | Step 3 §6 |
| `06_models_and_predictions.sql` | Models, validation, predictions, ICH M7 | Step 3 §7 |
| `07_relations.sql` | Drug-target interactions, pathway/disease links, adverse events | Step 3 §8 |
| `08_views.sql` | `compound_property_resolved` | Step 4 §8 |
| `09_triggers.sql` | Audit capture, feature-set consistency, ICH M7 pairing | Step 3 §10 |

## Scope decisions for Sprint 2.2

The following are **explicitly deferred**, not silently dropped. Each is additive
(new tables / new columns) and lands as its own migration once the code that
populates it exists — adding an empty column ahead of the computation that fills it
provides no value and adds maintenance surface.

| Deferred | Source | Lands with |
|---|---|---|
| `structural_alert`, `compound_structural_alert` | Step 4 §6 | Sprint 2.5 (ETL / descriptor generation) |
| Ionisation columns (`n_acidic_groups`, pKa endpoints, …) | Step 4 §4 | Pending pKa predictor decision (Step 4 §11 open item) |
| 3D conformer settings | Step 4 §5 | Phase 3+, per Phase 1's own recommendation |
| `endpoint_protein`, `pk_consistency_check` | Step 5 §3, §5 | Sprint 2.5 |
| `transporter_property`, `protein_ortholog`, `protein_tissue_expression`, `ontology_relation`/`ontology_closure`, `protein_classification`, `gene_disease_association` | Step 6 | Sprint 2.9 (Knowledge Integration) |
| `ames_panel_result`, `aop*`, `safety_margin`, `literature_reference`/`entity_reference` | Step 7 | Sprint 2.9 / when toxicology data is ingested |
| ADMET domain views (`admet_absorption`, etc.) | Step 5 §1 | Trivial to add once `endpoint` rows exist; deferred to avoid views over empty tables |

## Implementation notes (decided during Sprint 2.2, not in Phase 1)

Phase 1 specified these tables at the level of "what constraints must hold." Two
points needed a concrete decision to actually write runnable SQL:

**`audit_log.audit_uid` is `UUID DEFAULT gen_random_uuid()`, not the `ulid` domain.**
Every other `_uid` column in the schema is application-generated (Python
`drugsim_core.ids.generate_ulid`), because entities are created by application code.
Audit rows are the one case created *by the database itself*, in response to a
trigger — there is no application call site to generate a ULID from. Hand-rolling
Crockford base32 bit-packing in PL/pgSQL to keep the format uniform was considered
and rejected: it cannot be tested without a live database in this environment, and a
subtle bit-packing bug in an audit-trail primary key is a bad place to discover one.
`gen_random_uuid()` is standard, requires only `pgcrypto`, and audit rows are
identified in practice by `occurred_at` (part of the partition key) rather than by
parsing the identifier. This is a narrow implementation detail, not an architectural
change — the *purpose* of `audit_uid` (a unique row identifier) is unchanged.

**The generic audit trigger is attached to a named subset of tables**, not every
governed table. Bulk scientific data (`measurement`, `compound_descriptor`,
`compound_drug_likeness`) already carries per-row provenance
(`source_id`/`snapshot_id`/`pipeline_version`/`ingested_at`) — that *is* its audit
trail, and it is populated by ETL, not by ad-hoc row edits. `audit_log` is for
entities that are interactively created or mutated by a person: `compound` (for
soft-delete/restore), `system_user`, `model`, `model_version`, `data_source`, and
`ich_m7_assessment`. More tables can be added to the trigger additively later.

**Validation triggers (feature-set consistency, ICH M7 pairing) are `BEFORE`, not
`AFTER`.** Step 3 §10 named the category without prescribing timing. `BEFORE`
aborts the write before it happens rather than writing then rolling back — the more
standard idiom for pure validation triggers with no side effects on other rows.
