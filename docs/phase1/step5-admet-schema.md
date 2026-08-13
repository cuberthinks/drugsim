# DrugSim — Phase 1, Step 5
## ADMET Database Design

**Document status:** Draft for approval
**Date:** 2026-08-05
**Depends on:** Steps 1–4 (approved)

---

## 1. On "Separate Schemas" for A / D / M / E / T

The brief asks for separate schemas per ADMET domain. I want to argue against separate *tables* while delivering exactly what separation is meant to achieve — because the reason matters for everything downstream.

**Why five tables would be the wrong shape:**

1. **They would be near-identical.** Absorption and excretion measurements share the same ~35 columns: value, unit, censoring, status, species, provenance, licence, conversion audit. Five copies means five places for a schema fix to be applied and four places to forget.
2. **Adding an endpoint would require DDL.** New ADMET endpoints appear constantly. Under a table-per-domain design, adding "MDCK permeability" means a migration; under an endpoint registry it is an `INSERT`. In a validated system (Step 2 addendum), a migration is a change-controlled event — so the design choice directly determines how expensive scientific iteration is.
3. **Cross-domain queries would fragment.** "Give me every measured property for compound X" becomes a five-way UNION that must be updated whenever a table is added.
4. **Domain boundaries are not clean.** Is P-gp efflux absorption or distribution? Is CYP3A4 inhibition metabolism, or a DDI liability? Is plasma protein binding distribution, or a determinant of clearance? Hard-coding a contested taxonomy into physical tables makes reclassification a migration.

**What is delivered instead:** the separation lives in the `endpoint` registry via `endpoint_class`, which is *data*. Each ADMET domain gets a fully specified endpoint set (§2), a view exposing it as a domain-specific interface, and domain-specific validation rules. Consumers see five schemas; the database keeps one integrity model.

```sql
CREATE VIEW admet_absorption AS
    SELECT m.*, e.display_name, e.canonical_unit AS endpoint_unit
    FROM measurement m JOIN endpoint e USING (endpoint_id)
    WHERE e.endpoint_class = 'absorption' AND NOT m.is_deleted;
-- analogous views: admet_distribution, admet_metabolism, admet_excretion, admet_toxicity
```

This is the same supertype/subtype reasoning as Step 3 §6.4, applied one level up.

---

## 2. ADMET Endpoint Registry

Seed data for the `endpoint` table. Units carry Step 2 verification tags — **[P]** entries remain provisional until gate G4 confirms them empirically, because TDC does not document units [V].

### 2.1 Absorption
| `endpoint_id` | Display | Canonical unit | Type | Envelope | Status |
|---|---|---|---|---|---|
| `caco2_papp` | Caco-2 permeability | log₁₀(cm/s) | reg | −7.8 … −3.5 | [P] |
| `pampa_permeability` | PAMPA permeability | log₁₀(cm/s) | reg | −8 … −3 | [P] |
| `mdck_papp` | MDCK permeability | log₁₀(cm/s) | reg | −8 … −3 | [P] |
| `hia` | Human intestinal absorption | binary | cls | — | [P] |
| `pgp_inhibition` | P-gp inhibition | binary | cls | — | [P] |
| `pgp_substrate` | P-gp substrate | binary | cls | — | [P] |
| `oral_bioavailability` | Oral bioavailability (F ≥ 20 %) | binary | cls | — | [P] |
| `f_percent` | Oral bioavailability, continuous | % | reg | 0 … 100 | [P] |
| `aqueous_solubility` | Aqueous solubility | log₁₀(mol/L) | reg | −13 … 2 | [P] |
| `logd_74` | Distribution coefficient pH 7.4 | dimensionless | reg | −10 … 15 | [V] |

### 2.2 Distribution
| `endpoint_id` | Display | Canonical unit | Type | Envelope | Status |
|---|---|---|---|---|---|
| `bbb_penetration` | BBB penetration | binary | cls | — | [P] |
| `logbb` | Brain/plasma partition | log₁₀ ratio | reg | −3 … 2 | [P] |
| `ppbr_percent` | Plasma protein binding | % bound | reg | 0 … 100 | [P] |
| `fraction_unbound` | Fraction unbound | fraction | reg | 0 … 1 | derived |
| `vdss` | Volume of distribution at steady state | L/kg | reg | 0.01 … 700 | [P] |
| `blood_plasma_ratio` | Blood-to-plasma ratio | ratio | reg | 0.3 … 5 | [P] |

### 2.3 Metabolism
| `endpoint_id` | Display | Unit | Type | Enzyme |
|---|---|---|---|---|
| `cyp1a2_inhibition` | CYP1A2 inhibition | binary | cls | CYP1A2 |
| `cyp2c9_inhibition` | CYP2C9 inhibition | binary | cls | CYP2C9 |
| `cyp2c19_inhibition` | CYP2C19 inhibition | binary | cls | CYP2C19 |
| `cyp2d6_inhibition` | CYP2D6 inhibition | binary | cls | CYP2D6 |
| `cyp3a4_inhibition` | CYP3A4 inhibition | binary | cls | CYP3A4 |
| `cyp2c9_substrate` | CYP2C9 substrate | binary | cls | CYP2C9 |
| `cyp2d6_substrate` | CYP2D6 substrate | binary | cls | CYP2D6 |
| `cyp3a4_substrate` | CYP3A4 substrate | binary | cls | CYP3A4 |
| `cyp3a4_induction` | CYP3A4 induction | binary | cls | CYP3A4 |
| `microsomal_stability` | Microsomal stability t½ | min | reg | — |

### 2.4 Excretion
| `endpoint_id` | Display | Canonical unit | Type | Note |
|---|---|---|---|---|
| `half_life` | Terminal half-life | **hours** | reg | [P] |
| `clearance_hepatocyte` | Hepatocyte intrinsic clearance | **µL/min/10⁶ cells** | reg | [P] ⚠️ |
| `clearance_microsome` | Microsomal intrinsic clearance | **mL/min/g protein** | reg | [P] ⚠️ |
| `clearance_systemic` | Systemic clearance | mL/min/kg | reg | [P] |
| `renal_clearance` | Renal clearance | mL/min/kg | reg | [P] |

**⚠️ The two intrinsic clearance endpoints are deliberately separate.** They use different denominators (per 10⁶ cells vs per g microsomal protein) and are **not interchangeable**. They are registered as distinct endpoints specifically so that pooling them requires writing an explicit UNION rather than happening by accident.

Toxicity endpoints are specified in Step 7.

---

## 3. Linking Metabolism Endpoints to Enzymes

`cyp3a4_inhibition` encodes its enzyme in a string. That is fragile: it cannot answer "which endpoints involve CYP2D6?" without pattern matching, and it cannot connect to the protein records in Domain C.

```sql
CREATE TABLE endpoint_protein (
    endpoint_id   TEXT NOT NULL REFERENCES endpoint(endpoint_id) ON DELETE RESTRICT,
    protein_uid   ulid NOT NULL REFERENCES protein(protein_uid) ON DELETE RESTRICT,
    interaction_role TEXT NOT NULL CHECK (interaction_role IN
        ('inhibitor','substrate','inducer','activator','transported_by')),
    PRIMARY KEY (endpoint_id, protein_uid, interaction_role)
);
```

**`interaction_role` distinguishes three clinically different things** that a naive schema collapses. A CYP3A4 *inhibitor* raises co-administered drug exposure; a CYP3A4 *substrate* has its own exposure raised by other inhibitors; a CYP3A4 *inducer* lowers exposure over days-to-weeks. Same enzyme, three different DDI consequences and three different clinical risks. Treating "CYP3A4 interaction" as one concept is a real and consequential modelling error.

This also makes the metabolism module queryable through the biology domain: *"show every compound predicted to inhibit any enzyme in the CYP2C subfamily"* becomes a join, not a hardcoded list.

---

## 4. Prediction Fields — Mapping the Brief

The brief requires each prediction to carry: predicted value, confidence, model version, prediction method, supporting evidence, source dataset, prediction date, quality score. All exist in Step 3 §7.3:

| Brief requirement | Schema field |
|---|---|
| Predicted Value | `prediction.predicted_value` + `predicted_unit` |
| Confidence Score | `confidence_score` (calibrated) + `interval_low/high` + `interval_coverage` |
| Model Version | `model_version_uid` → `model_version.version` |
| Prediction Method | `model_version.algorithm` + `model.methodology` |
| Supporting Evidence | `prediction_evidence` (ranked nearest neighbours with measured values) |
| Source Dataset | `model_version.training_snapshot_id` |
| Prediction Date | `predicted_at` |
| Quality Score | `quality_score` + `quality_formula_version` |

Beyond the brief, and required by Step 1's positioning: `ad_verdict`, `ad_max_tanimoto`, `ad_scaffold_seen`, `feature_set_id`, `training_license_tiers`, `is_commercial_ok`.

---

## 5. PK Parameter Consistency — a Validation Rule the Brief Does Not Ask For

This is the most important scientific addition in Step 5.

Half-life, volume of distribution and clearance are **not independent**. They are linked by a physical relationship:

$$t_{1/2} = \frac{\ln 2 \times V_{ss}}{CL}$$

If DrugSim predicts `half_life`, `vdss` and `clearance_systemic` with three separate models — which is exactly what training on three separate TDC datasets produces — **the three predictions can be mutually contradictory.** A compound might be assigned a 2-hour half-life, a 10 L/kg volume of distribution, and a clearance that together imply a 40-hour half-life. Each model is individually defensible; the set is physically impossible.

A DMPK scientist would notice this immediately. A model pipeline will not, and neither will a UI that renders three cards.

```sql
CREATE TABLE pk_consistency_check (
    check_uid       ulid PRIMARY KEY,
    compound_uid    ulid NOT NULL REFERENCES compound(compound_uid) ON DELETE RESTRICT,
    half_life_prediction_uid  ulid REFERENCES prediction(prediction_uid) ON DELETE RESTRICT,
    vdss_prediction_uid       ulid REFERENCES prediction(prediction_uid) ON DELETE RESTRICT,
    clearance_prediction_uid  ulid REFERENCES prediction(prediction_uid) ON DELETE RESTRICT,
    implied_half_life_h  NUMERIC(12,4),
    predicted_half_life_h NUMERIC(12,4),
    fold_discrepancy     NUMERIC(10,4) CHECK (fold_discrepancy >= 1),
    is_consistent        BOOLEAN NOT NULL,
    tolerance_fold       NUMERIC(4,2) NOT NULL DEFAULT 3.0,
    checked_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Tolerance is 3-fold by default**, reflecting that PK predictions are rarely better than 2–3× accurate and that the underlying datasets are small (half-life: 667 compounds [V]). Tighter tolerance would flag everything; looser would catch nothing.

**How an inconsistency should be handled:** flag it and surface it — do not silently reconcile by overwriting one prediction. An inconsistency is genuine information: it usually means at least one of the three is out of applicability domain. Reconciliation would hide the signal that the prediction set is unreliable for that compound, which is precisely the signal a triage product exists to give.

**Related consistency relationships worth encoding later:** `fraction_unbound = 1 − ppbr_percent/100` (deterministic, so should be derived rather than independently predicted), and hepatic clearance scaling from intrinsic clearance via the well-stirred model.

---

## 6. Deferred to Later Phases

| Capability | Why deferred |
|---|---|
| **Metabolite structure prediction** | A compound→compound relation needing a site-of-metabolism model. Substantial scope; Phase 4+ |
| **DDI risk scoring** | Derivable from CYP inhibition + substrate data, but clinically meaningful scoring needs exposure (Cmax) data DrugSim will not have in Phase 1 |
| **PBPK modelling** | Requires physiological parameter sets and a simulation engine, not a database. This is what "Virtual Drug Simulation" in the brief will eventually mean |
| **Transporter panel beyond P-gp** | BCRP, OATP1B1/1B3, OCT2, MATE — data availability is thin; add as sources appear |

---

*End Step 5.*
