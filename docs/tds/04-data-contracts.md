# TDS §4 — Data Contracts

---

## 4.1 Contracts Are Not the Database Schema

The most important architectural point in this section: **the API contract and the Core DB schema are separate surfaces with independent lifecycles.**

The Core DB (Phase 1 Step 3) has ULID primary keys, `license_tier` partition keys, audit columns, snapshot IDs and pipeline versions. None of that belongs in a public response, and coupling them would make every internal refactor a breaking API change — the single most common cause of API ossification in long-lived systems.

| Concern | Core DB | Contract |
|---|---|---|
| Identifiers | `compound_uid` (ULID) | `id` (prefixed public ID) |
| Licence | `license_tier`, `source_license` per record | Aggregated `data_licensing` block, enterprise only |
| Audit | `created_by`, `pipeline_version`, `snapshot_id` | Not exposed |
| Partitioning | `license_tier` in PK | Not exposed |
| Versioning | `core-db-vN.N.N` (SemVer) | `/v1/` path + `contract_version` |

**Rule: no contract field maps 1:1 to an internal column by accident.** Every exposed field is a deliberate decision recorded here.

### 4.1.1 Public identifiers
Prefixed, opaque, URL-safe — `cmp_01J8XK2M4N7P9QRSTVWXYZ0123`. The prefix makes IDs self-describing in logs and support tickets; opacity prevents clients from parsing structure out of them.

| Prefix | Entity | Prefix | Entity |
|---|---|---|---|
| `cmp_` | Compound | `usr_` | User |
| `prd_` | Prediction | `exp_` | Experiment |
| `mdl_` | Model version | `sim_` | Simulation |
| `dst_` | Dataset | `job_` | Job |
| `tgt_` | Target | `prot_` | Protein |

### 4.1.2 Common conventions

| Convention | Rule |
|---|---|
| Field naming | `snake_case` |
| Timestamps | RFC 3339, UTC, `Z` suffix, always TZ-aware |
| Numbers | JSON number; **every quantity carries an explicit `unit` sibling field** |
| Nulls | `null` means "not applicable"; absent means "not requested". A value that is unknown carries an explicit `status` |
| Enums | Lowercase snake_case strings; **additive only** within a contract version |
| Pagination | Cursor-based: `{data: [...], next_cursor, has_more}` |
| Money/precision | Decimals as strings where exactness matters |

**Enum additivity is a hard rule.** Clients must tolerate unknown enum values without failing. Adding `ad_verdict: "insufficient_reference_data"` in a minor release must not break an existing client — so clients treat unrecognised verdicts as `undeterminable` (fail-safe), never as `in_domain`.

---

## 4.2 Compound

Sourced from `compound`, `compound_descriptor`, `compound_drug_likeness` (Phase 1 Steps 3–4).

| Field | Type | Req | Unit | Validation | Description |
|---|---|---|---|---|---|
| `id` | string | ✔ | — | `^cmp_[0-9A-HJKMNP-TV-Z]{26}$` | Public compound ID |
| `object` | string | ✔ | — | `= "compound"` | Type discriminator |
| `smiles` | string | ✔ | — | 1–4000 chars, RDKit-parseable | Canonical SMILES (stereo stripped) |
| `isomeric_smiles` | string | ✔ | — | RDKit-parseable | Canonical SMILES with stereochemistry |
| `standardized_smiles` | string | ✔ | — | — | Post-standardisation structure |
| `inchi` | string | ✔ | — | starts `InChI=1S/` | Standard InChI |
| `inchikey` | string | ✔ | — | `^[A-Z]{14}-[A-Z]{10}-[A-Z]$` | Full InChIKey |
| `inchikey_skeleton` | string | ✔ | — | 14 uppercase | Connectivity block |
| `molecular_formula` | string | ✔ | — | Hill notation | — |
| `scaffold` | string\|null | ✔ | — | SMILES or null | Bemis-Murcko scaffold; null if acyclic |
| `stereo_completeness` | enum | ✔ | — | `fully_defined`\|`partially_defined`\|`undefined`\|`not_applicable` | — |
| `is_mixture` | boolean | ✔ | — | — | True → descriptors not computed |
| `standardization_applied` | string[] | ✔ | — | — | e.g. `["salt_stripped","charge_neutralised"]` |
| `properties` | object | ○ | — | §4.2.1 | Computed descriptors |
| `drug_likeness` | object | ○ | — | §4.2.2 | Rule evaluations |
| `structural_alerts` | array | ○ | — | §4.2.3 | Matched alerts |
| `created_at` | timestamp | ✔ | — | RFC 3339 | — |

**Relationships:** `predictions` (1:N, via `/v1/compounds/{id}/predictions`) · `experiments` (M:N) · `measurements` (1:N, public data only)

### 4.2.1 `properties`
Every numeric property is an object `{value, unit}` — never a bare number. This is not verbosity; it is the mechanism that prevents the unit errors Phase 1 identified as the highest-risk failure class.

| Field | Type | Unit | Validation |
|---|---|---|---|
| `molecular_weight` | {value, unit} | `g/mol` | > 0, < 10000 |
| `exact_mass` | {value, unit} | `g/mol` | > 0 |
| `logp` | {value, unit} | `dimensionless` | −10…15 |
| `tpsa` | {value, unit} | `angstrom_squared` | ≥ 0, < 1000 |
| `molar_refractivity` | {value, unit} | `cm3/mol` | ≥ 0 |
| `hbd` | {value, unit, convention} | `count` | ≥ 0; `convention ∈ {lipinski, strict}` |
| `hba` | {value, unit, convention} | `count` | ≥ 0; `convention ∈ {lipinski, strict}` |
| `rotatable_bonds` | {value, unit, strict} | `count` | 0–200 |
| `aromatic_rings`, `ring_count`, `heavy_atom_count`, `heteroatom_count` | {value, unit} | `count` | ≥ 0 |
| `formal_charge` | {value, unit} | `elementary_charge` | −20…20 |
| `fraction_csp3` | {value, unit} | `ratio` | 0–1 |
| `descriptor_spec_version` | string | — | Pins toolchain and conventions |

**`hbd`/`hba` carry `convention` because RDKit's two definitions disagree** and the difference changes Lipinski verdicts (Phase 1 Step 4 §E.1). Omitting it makes a drug-likeness result unfalsifiable.

**`logd` and `logs` are deliberately absent from `properties`.** They are measured or predicted, not computed, and appear under `predictions` or `measurements` with full provenance (Phase 1 Step 4 §1).

### 4.2.2 `drug_likeness`

| Field | Type | Validation | Note |
|---|---|---|---|
| `lipinski` | {violations: int, passes: bool, criteria: object} | 0–4 | Component detail always included |
| `veber`, `ghose`, `egan`, `muegge`, `rule_of_three`, `lead_like`, `reos` | {passes: bool\|null, criteria: object} | — | **`null` = not evaluable**, never `false` |
| `golden_triangle` | {passes: bool\|null, ...} | — | Requires logD; null when unavailable |
| `qed` | {value: number, unit: "score_0_1"} | 0–1 | — |
| `synthetic_accessibility` | {value, unit: "score_1_10"} | 1–10 | 1 = easy |
| `pfizer_3_75` | {flagged: bool, ...} | — | **`flagged`, not `passes`** — elevated risk, not failure |
| `gsk_4_400` | {flagged: bool, ...} | — | As above |
| `rule_catalogue_version` | string | — | Thresholds are conventions and get revised |
| `interpretation_note` | string | ✔ | Fixed advisory text — see below |

`interpretation_note` is a **required** field carrying: *"Drug-likeness rules are heuristics derived from historical drug sets, not physical laws. Novel chemotypes routinely and successfully violate them."* It is in the contract, not just the UI, so every client surfaces it. Phase 1 verified that Pfizer 3/75's original finding has not been reproduced — the naming and this note both follow from that.

### 4.2.3 `structural_alerts`
`{alert_set, alert_name, description, severity, is_genotoxic, match_count, matched_atoms: int[]}`

`matched_atoms` supports highlighting in the UI and satisfies OECD Principle 5 interpretability. `is_genotoxic` separates DNA-reactivity alerts (ICH M7 relevant) from general promiscuity filters — conflating them would be a category error with regulatory consequences.

---

## 4.3 Prediction — the Envelope

**The central contract of the system.** Its structure encodes §1.4: a prediction without uncertainty is not a scientific result.

| Field | Type | Req | Validation | Description |
|---|---|---|---|---|
| `id` | string | ✔ | `prd_...` | — |
| `object` | string | ✔ | `= "prediction"` | — |
| `compound_id` | string | ✔ | `cmp_...` | FK |
| `endpoint` | object | ✔ | §4.3.1 | What was predicted |
| `estimate` | object | ✔ | §4.3.2 | Value **and** interval — inseparable |
| `reliability` | object | ✔ | §4.3.3 | AD, confidence, quality |
| `evidence` | object | ○ | §4.3.4 | Nearest neighbours |
| `provenance` | object | ✔ | §4.3.5 | Model, features, training data |
| `must_display` | string[] | ✔ | non-empty | §4.3.6 — client conformance |
| `warnings` | array | ✔ | may be empty | Structured advisories |
| `created_at` | timestamp | ✔ | RFC 3339 | — |

### 4.3.1 `endpoint`
`{id, name, category, canonical_unit, task_type, higher_is_worse: bool|null}`

`higher_is_worse` is exposed because clients must colour and sort correctly. Getting it wrong for LD50 — where higher means *safer* in mg/kg — inverts the safety display. Phase 1 identified this as the highest-risk conversion in the system.

### 4.3.2 `estimate`

| Field | Type | Req | Description |
|---|---|---|---|
| `value` | number\|string\|null | ✔ | Point estimate; string for categorical; **null when not predictable** |
| `unit` | string | ✔ | Must equal `endpoint.canonical_unit` |
| `interval` | object\|null | ✔ | `{low, high, coverage, method}` |
| `probability` | number\|null | ○ | Classification only, 0–1, calibrated |
| `status` | enum | ✔ | `predicted`\|`refused_out_of_domain`\|`insufficient_model_support` |

**`value` is nested inside `estimate` alongside `interval` deliberately.** A client reading `prediction.estimate.value` has already traversed the object containing the interval. This does not make misuse impossible — JSON cannot — but it removes the accident of a flat `{value: 3.2}` that reads as complete.

`status = refused_out_of_domain` returns `value: null`. **DrugSim may decline to give a number.** This is a supported outcome (P12), not an error, and returns HTTP 200.

### 4.3.3 `reliability` — never null, never omitted

| Field | Type | Req | Validation | Description |
|---|---|---|---|---|
| `applicability_domain` | enum | ✔ | `in_domain`\|`borderline`\|`out_of_domain`\|`undeterminable` | — |
| `ad_rationale` | string | ✔ | non-empty | Human-readable basis |
| `max_similarity_to_training` | number | ✔ | 0–1 | Max Tanimoto |
| `scaffold_in_training` | boolean | ✔ | — | — |
| `confidence` | number | ✔ | 0–1 | Calibrated |
| `calibration_method` | string\|null | ✔ | — | `null` = uncalibrated, and clients must say so |
| `quality_score` | number | ✔ | 0–1 | Composite |
| `quality_formula_version` | string | ✔ | — | Versioned; scores are not comparable across versions |
| `training_set_size` | integer | ✔ | > 0 | **Exposed deliberately** |

**`training_set_size` is exposed because it is the single most honest number in the response.** A user seeing "trained on 475 compounds" for hepatotoxicity calibrates their trust correctly in a way no confidence score achieves. Hiding it would be the most consequential omission available to us.

### 4.3.4 `evidence`
`{nearest_neighbours: [{compound_id, smiles, tanimoto, measured_value, measured_unit, source, reference}], count}`

Nearest neighbours with *measured* values let a chemist assess the prediction directly — often more persuasive than the confidence score. Only public-data compounds appear here; **another tenant's structures are never exposed as evidence** (§7).

### 4.3.5 `provenance`
`{model_id, model_name, model_version, methodology, algorithm, feature_set_id, training_snapshot_id, training_data_sources: string[], core_db_release, predicted_at, is_validated, validation_summary}`

Sufficient to reconstruct the prediction (P2). `is_validated` reports whether OECD five-principle records are complete — relevant to any regulatory use.

### 4.3.6 `must_display` — client conformance

An array naming the fields a conforming client is **required** to render whenever it renders `estimate.value`. Typically:

```json
["estimate.interval", "reliability.applicability_domain",
 "reliability.training_set_size", "warnings"]
```

Rationale: a JSON API cannot force a client to render anything. The realistic options are to hope, or to make the requirement explicit and testable. `must_display` makes it machine-readable, and the conformance suite (§5.9 / §8) asserts that the frontend renders every named field. When AD is `out_of_domain`, the array additionally includes `estimate.status`.

This is the mechanism behind rule PR-05 ("OOD verdicts structurally unsuppressible") at the API layer.

---

## 4.4 Model

| Field | Type | Req | Description |
|---|---|---|---|
| `id`, `object`, `name`, `version` | string | ✔ | SemVer |
| `endpoint_id` | string | ✔ | What it predicts |
| `methodology` | enum | ✔ | `expert_rule_based`\|`statistical_based`\|`hybrid`\|`read_across` |
| `algorithm` | string | ✔ | e.g. `gradient_boosting`, `message_passing_nn` |
| `status` | enum | ✔ | `development`\|`champion`\|`challenger`\|`deprecated`\|`withdrawn` |
| `training` | object | ✔ | `{snapshot_id, n_compounds, split_strategy, data_sources[]}` |
| `performance` | object | ✔ | §4.4.1 |
| `applicability_domain` | object | ✔ | `{method, parameters, description}` |
| `validation` | object | ✔ | `{is_validated, oecd_principles: {...}, qmrf_available}` |
| `is_commercial_use_permitted` | boolean | ✔ | Derived from consumed licence tiers |
| `created_at`, `deployed_at` | timestamp | ✔/○ | — |

### 4.4.1 `performance` — dual-split reporting, mandatory

```json
{
  "global_split": { "metric": "rmse", "value": 0.71, "n_test": 181,
                    "split_strategy": "global_scaffold" },
  "benchmark_split": { "metric": "rmse", "value": 0.58, "n_test": 181,
                       "split_strategy": "tdc_canonical" },
  "gap_explanation": "Global scaffold splitting prevents cross-dataset leakage; benchmark figures are leaderboard-comparable but optimistic for novel chemotypes."
}
```

**Both must be present.** Phase 1 (ADR-009) established that global splits give lower but honest numbers while TDC splits give leaderboard comparability. Reporting only the favourable one would be the easiest and most damaging misrepresentation available — so the contract requires both and a required `gap_explanation`.

---

## 4.5 Dataset

| Field | Type | Req | Description |
|---|---|---|---|
| `id`, `object`, `name`, `source_id` | string | ✔ | Registry key |
| `version` | string | ✔ | Upstream version, e.g. `chembl_37` |
| `snapshot_id` | string | ✔ | Our acquisition |
| `description`, `homepage` | string | ✔ | — |
| `record_count` | integer | ✔ | — |
| `endpoints_covered` | string[] | ✔ | — |
| `licence` | object | ✔ | `{spdx, name, url, commercial_use_permitted, share_alike, attribution_text}` |
| `verification` | object | ✔ | `{status, date, method}` — Phase 1 [V]/[S]/[U] carried through |
| `cadence` | object | ✔ | `{expected_days, last_updated, is_stale}` |
| `unit_documentation_available` | boolean | ✔ | **False for TDC** |

`licence.tier` is **not** exposed — it is an internal governance concept. `commercial_use_permitted` and `share_alike` are exposed because enterprise customers legitimately need them for their own compliance.

`unit_documentation_available` and `verification` exist so downstream users inherit Phase 1's epistemic honesty rather than a false impression of uniform quality.

---

## 4.6 Target and Protein

**Target** — `{id, object, name, target_type, organism: {taxon_id, name}, components: [{protein_id, accession, gene_symbol}], classification: {level_1..5}, external_ids: {chembl_target_id}}`

**Protein** — `{id, object, uniprot_accession, entry_name, is_reviewed, gene: {symbol, ensembl_id}, organism, sequence_length, ec_number, protein_class, roles: {is_enzyme, is_transporter, is_drug_target}, transporter: {direction, family, ...}|null, orthologs: [{protein_id, organism, relationship, sequence_identity_pct}]}`

Two exposures are deliberate:

**`is_reviewed`** distinguishes Swiss-Prot from TrEMBL. Only reviewed entries are ground truth (Phase 1 Step 1 §3.6), and consumers must be able to tell.

**`orthologs`** carries `relationship: "no_ortholog"` as a real value. When DrugSim reasons from rodent toxicity to human risk, the orthology basis is part of the answer — and "there is no rodent ortholog" is exactly the case where that inference must not be made silently.

---

## 4.7 User

New in the TDS; extends `system_user` with tenancy.

| Field | Type | Req | Validation | Description |
|---|---|---|---|---|
| `id`, `object` | string | ✔ | `usr_...` | — |
| `email` | string | ✔ | RFC 5322, unique | Also the Part 11 unique identifier |
| `full_name` | string | ✔ | 1–200 | Required for signature manifestation (§11.50) |
| `tenant_id` | string | ✔ | `tnt_...` | **Isolation boundary** |
| `roles` | string[] | ✔ | ⊆ `{admin, curator, scientist, reviewer, readonly}` | — |
| `is_active` | boolean | ✔ | — | Soft deactivation only |
| `mfa_enabled` | boolean | ✔ | — | Required for `reviewer`/`admin` |
| `can_sign` | boolean | ✔ | — | Part 11 signing authority |
| `password_last_changed_at` | timestamp | ○ | — | Part 11 ageing |
| `last_login_at`, `created_at` | timestamp | ○/✔ | — | — |

**`tenant_id` is the isolation boundary for customer IP** and appears in every authorisation decision and every row-level security policy (§7). It is never client-supplied — always derived from the authenticated token.

Users are **never hard-deleted** (P8): `is_active = false`, with the audit trail preserved. Under Part 11 an account whose actions are recorded cannot be removed.

---

## 4.8 Experiment

New entity. A user-defined grouping of compounds and predictions — a project, a series, a screening campaign.

| Field | Type | Req | Description |
|---|---|---|---|
| `id`, `object`, `name` | string | ✔ | `exp_...` |
| `description` | string | ○ | — |
| `tenant_id`, `owner_id` | string | ✔ | — |
| `status` | enum | ✔ | `draft`\|`running`\|`complete`\|`archived` |
| `compound_ids` | string[] | ✔ | Members |
| `endpoints_requested` | string[] | ✔ | — |
| `prediction_ids` | string[] | ✔ | Results |
| `core_db_release`, `model_versions_used` | string / string[] | ✔ | **Frozen at execution** |
| `summary` | object | ○ | Aggregate stats incl. OOD count |
| `created_at`, `completed_at` | timestamp | ✔/○ | — |

**`core_db_release` and `model_versions_used` are frozen when the experiment runs**, so results remain interpretable after models are retrained. An experiment is a scientific record, not a live view — re-running it later against newer models is a *new* experiment, and the contract makes that distinction visible.

`summary.out_of_domain_count` is deliberately part of the summary: an experiment where 80% of compounds were OOD needs that fact prominent, not buried per-row.

---

## 4.9 Simulation

**Placeholder contract, Phase 5+.** Defined now so the namespace and shape are reserved and clients can be built against a stable expectation.

| Field | Type | Req | Description |
|---|---|---|---|
| `id`, `object` | string | ✔ | `sim_...` |
| `compound_id` | string | ✔ | — |
| `simulation_type` | enum | ✔ | `pbpk_single_dose`\|`pbpk_multi_dose`\|`exposure_projection` |
| `status` | enum | ✔ | `queued`\|`running`\|`complete`\|`failed` |
| `inputs` | object | ✔ | `{dose, dose_unit, route, species, body_weight_kg, dosing_interval_h, n_doses}` |
| `parameter_sources` | object | ✔ | Per PK parameter: measured, predicted (with `prediction_id`), or assumed |
| `results` | object\|null | ✔ | `{cmax, tmax, auc, css, concentration_profile[]}` each with units |
| `reliability` | object | ✔ | Same shape as §4.3.3 |
| `assumptions` | string[] | ✔ | non-empty |

**`parameter_sources` is the critical field.** A PBPK simulation built on predicted clearance and predicted volume of distribution inherits both models' uncertainty, and the output can look far more precise than its inputs justify. Recording which parameters were measured, which predicted, and which assumed makes that inheritance visible rather than laundered.

`assumptions` is required and non-empty — a simulation with no stated assumptions is not a scientific artefact.

---

## 4.10 Contract Versioning

| Change | Version impact | Client action |
|---|---|---|
| New optional field | MINOR — same `/v1/` | None; clients ignore unknown fields |
| New enum value | MINOR | Must tolerate; fail safe |
| New endpoint | MINOR | None |
| Field removed / renamed | **MAJOR — `/v2/`** | Migration required |
| Type or unit changed | **MAJOR** | Migration required |
| Required→optional | MINOR | None |
| Optional→required | **MAJOR** | — |

**Support policy:** the previous major version is supported for 12 months after a new one ships, with a deprecation header on every response. Under a regulatory path, a customer may have validated their own workflow against a specific version, and pulling it out from under them invalidates their validation — which makes the support window a contractual matter, not merely a courtesy.

---

*End §4.*
