# DrugSim — Phase 1, Step 4
## Compound Information Schema

**Document status:** Draft for approval
**Date:** 2026-08-05
**Depends on:** Steps 1–3 (approved), Step 2 regulatory addendum
**Amends:** `step3-relational-schema.md` §4.2 — see §1

---

## 0. Scope

Steps 2 and 3 already specified compound identity (dictionary §D, ERD §4.1) and the core descriptor set (dictionary §E–§F, ERD §4.2–§4.3). This step does four things rather than restate them:

1. **Corrects a boundary violation** in the Step 3 DDL (§1)
2. **Completes the descriptor catalogue** — the brief asked for "additional descriptors commonly used in medicinal chemistry", and the Step 2 set was the core, not the whole (§3)
3. **Fills three genuine gaps**: ionisation state, 3D descriptors, structural alerts (§4–§6)
4. **Extends the drug-likeness rule catalogue** with verified thresholds and an honest account of their reliability (§7)

---

## 1. Correction to Step 3 §4.2

`compound_descriptor` in the Step 3 DDL includes `logd_74` and `logs_mol_l` as nullable columns. That is wrong, and it violates principle P4 (measurements and predictions never co-mingle).

The distinction that matters:

| Property | Nature | Correct home |
|---|---|---|
| `logp_crippen` | **Computed** — deterministic function of structure via Wildman–Crippen | `compound_descriptor` ✓ |
| `logd_74` | **Measured or predicted** — depends on pKa and pH; no closed-form derivation from structure | `measurement` / `prediction` |
| `logs_mol_l` | **Measured or predicted** — solubility is an experimental quantity | `measurement` / `prediction` |

Left as-is, a predicted logD would sit in a table whose whole purpose is version-pinned deterministic computation, with no model attribution, no applicability domain, and no uncertainty. It would also be indistinguishable from an experimental value — exactly the confusion P4 exists to prevent.

**Fix:** drop both columns from `compound_descriptor`. LogD and LogS flow through the existing `measurement`/`prediction` machinery with `endpoint_class = 'physicochemical'`. No new tables needed — the Step 3 design already handles this correctly; the columns were a leak from the Step 2 dictionary's descriptor table, where they were listed with a note that they are "experimental or predicted."

```sql
ALTER TABLE compound_descriptor DROP COLUMN logd_74;
ALTER TABLE compound_descriptor DROP COLUMN logs_mol_l;

INSERT INTO endpoint (endpoint_id, endpoint_class, display_name, canonical_unit,
                      is_categorical, expected_min, expected_max, higher_is_worse,
                      species_specific, unit_verified_method) VALUES
  ('logd_74','physicochemical','Distribution coefficient, pH 7.4','dimensionless',
   FALSE, -10, 15, NULL, FALSE, 'documented'),
  ('logs',   'physicochemical','Aqueous solubility','log10(mol/L)',
   FALSE, -14,  2, NULL, FALSE, 'range_assertion');
```

`higher_is_worse` is `NULL` for both — neither is directionally good or bad in isolation, which is why the Step 3 CHECK permits `NULL` only for non-categorical endpoints where direction is genuinely undefined. That constraint needs a small relaxation:

```sql
ALTER TABLE endpoint DROP CONSTRAINT ck_direction;
ALTER TABLE endpoint ADD CONSTRAINT ck_direction CHECK (
    is_categorical
    OR higher_is_worse IS NOT NULL
    OR endpoint_class = 'physicochemical'
);
```

**Consequence worth stating:** a chemist asking "what is this compound's logD?" now needs a resolution rule across experimental and predicted sources. §8 defines it.

---

## 2. Compound Identity — Consolidated

Fully specified in dictionary §D and ERD §4.1. Three points the brief's identification list does not cover, which matter in practice.

### 2.1 The brief's list maps as follows

| Brief field | Schema field | Note |
|---|---|---|
| Compound ID | `compound_uid` | ULID surrogate (ADR-008) |
| SMILES | `source_smiles` | Verbatim as received |
| Canonical SMILES | `canonical_smiles` | RDKit canonical, stereo stripped |
| Isomeric SMILES | `isomeric_smiles` | RDKit canonical, stereo retained |
| InChI | `inchi` | Standard InChI |
| InChIKey | `inchikey_full` | Plus `inchikey_skeleton`, `parent_inchikey` (§5 of dictionary) |

### 2.2 Multi-component structures
Salts, solvates, mixtures and co-crystals arrive as disconnected SMILES. Policy:

- `source_smiles` retains all components
- `standardized_smiles` retains the parent after salt/solvate stripping
- `component_count` records how many were present
- **Genuine mixtures (two active components, no clear parent) are flagged and excluded from descriptor computation**, not silently reduced to their largest fragment

```sql
ALTER TABLE compound ADD COLUMN component_count SMALLINT NOT NULL DEFAULT 1
    CHECK (component_count > 0);
ALTER TABLE compound ADD COLUMN is_mixture BOOLEAN NOT NULL DEFAULT FALSE;
ALTER TABLE compound ADD CONSTRAINT ck_mixture_no_parent
    CHECK (NOT is_mixture OR parent_inchikey IS NULL);
```

Silently taking the largest fragment of a true mixture produces descriptors for a molecule that was never tested. It is a small, common, and entirely avoidable error.

### 2.3 Undefined stereocentres — an unresolved policy question
`stereo_completeness` records the state, but the schema does not yet say what DrugSim *does* with a compound having undefined centres. Three options, none free:

| Policy | Consequence |
|---|---|
| Predict on the structure as given | Fast; ignores that stereoisomers can differ by orders of magnitude in potency and toxicity |
| Enumerate isomers, predict each, report a range | Scientifically honest; multiplies compute and complicates the UI |
| Refuse and require specification | Rigorous; likely unacceptable to users uploading early-stage designs |

**Recommendation: enumerate up to a bounded count (say 8 isomers), predict each, and report the range with the worst case highlighted** — consistent with a prioritisation/triage product. Above the bound, flag and predict on the given structure with an explicit caveat. This needs your decision; it affects the prediction API contract, so I have not baked it into the schema.

---

## 3. Complete Descriptor Catalogue

Dictionary §E covers the core. Below is the full set, organised by family. All computed under a pinned `descriptor_spec_version` (R2).

### 3.1 Constitutional (counts)
| Descriptor | Unit | RDKit provenance |
|---|---|---|
| `heavy_atom_count` | count | `Descriptors.HeavyAtomCount` |
| `heteroatom_count` | count | `Lipinski.NumHeteroatoms` |
| `n_count`, `o_count`, `s_count`, `p_count` | count | Atom iteration |
| `halogen_count` | count | F+Cl+Br+I |
| `n_radical_electrons` | count | `Descriptors.NumRadicalElectrons` |
| `n_valence_electrons` | count | `Descriptors.NumValenceElectrons` |
| `formal_charge` | e | `Chem.GetFormalCharge` |
| `amide_bond_count` | count | `rdMolDescriptors.CalcNumAmideBonds` |
| `quaternary_carbon_count` | count | SMARTS |

### 3.2 Ring & topology
| Descriptor | Unit | RDKit provenance |
|---|---|---|
| `ring_count` | count | `CalcNumRings` |
| `aromatic_rings` | count | `CalcNumAromaticRings` |
| `aliphatic_rings` | count | `CalcNumAliphaticRings` |
| `saturated_rings` | count | `CalcNumSaturatedRings` |
| `aromatic_heterocycles` | count | `CalcNumAromaticHeterocycles` |
| `aromatic_carbocycles` | count | `CalcNumAromaticCarbocycles` |
| `spiro_atoms` | count | `CalcNumSpiroAtoms` |
| `bridgehead_atoms` | count | `CalcNumBridgeheadAtoms` |
| `largest_ring_size` | count | Ring info |
| `fused_ring_count` | count | Ring-system analysis |

### 3.3 Physicochemical
Core set in dictionary §E, plus:

| Descriptor | Unit | RDKit provenance |
|---|---|---|
| `labute_asa` | Å² | `Descriptors.LabuteASA` |
| `balaban_j` | dimensionless | `Descriptors.BalabanJ` |
| `bertz_ct` | dimensionless | `Descriptors.BertzCT` — molecular complexity |
| `hall_kier_alpha` | dimensionless | `Descriptors.HallKierAlpha` |
| `kappa1`, `kappa2`, `kappa3` | dimensionless | Kier shape indices |
| `chi0v` … `chi4v` | dimensionless | Connectivity indices |
| `fraction_aromatic_atoms` | ratio 0–1 | Derived |
| `rotatable_bond_fraction` | ratio 0–1 | `rotatable_bonds / heavy_atom_count` |

### 3.4 VSA descriptor families
`SlogP_VSA1–12`, `SMR_VSA1–10`, `PEOE_VSA1–14`, `EState_VSA1–11` — approximately 47 descriptors partitioning surface area by contribution to logP, molar refractivity, partial charge and electrotopological state.

**Storage decision: these live in the feature store, not Postgres.** They are numerous, individually uninterpretable, used only as ML input, and never queried by a human. Persisting ~47 low-value columns on a 3M-row table would bloat the system of record for no query benefit. This is the general rule: **Postgres holds descriptors a scientist would ask about; the feature store holds descriptors a model consumes.**

### 3.5 Complexity & novelty
| Descriptor | Range | Note |
|---|---|---|
| `fraction_csp3` | 0–1 | `CalcFractionCSP3` — a widely used complexity proxy |
| `sa_score` | 1–10 | Ertl & Schuffenhauer synthetic accessibility |
| `np_likeness_score` | −5…5 | Natural-product likeness |
| `bertz_ct` | ≥0 | Graph complexity |
| `mce_18` | ≥0 | **Medicinal Chemistry Evolution 2018** — scores novelty by *cumulative sp³ complexity*, combining aromatic/aliphatic ring presence, chirality, spiro content, and the sp³ fraction split between cyclic and acyclic carbons. Distinct from plain sp³ count in that it weights the *nature and quality* of sp³-rich frameworks. Requires a third-party implementation; not in core RDKit |

---

## 4. Gap 1 — Ionisation State

Not covered in Steps 2–3, and it matters more for ADMET than most of the descriptors above.

**Why it matters:** absorption, distribution, permeability and protein binding are governed by the ionisation state at physiological pH, not by the neutral structure. LogD *is* LogP corrected for ionisation. A basic amine with pKa 9 is >99% protonated at pH 7.4 and behaves nothing like its neutral form. Predicting ADMET from neutral-molecule descriptors alone discards a first-order effect.

**The problem: RDKit does not predict pKa.** Options, none ideal:

| Tool | Licence | Assessment |
|---|---|---|
| **OPERA** (US EPA) | Public domain | Green tier, CC-compatible, QSAR-based. Best licence fit; moderate accuracy |
| **MolGpKa** / **pkasolver** | Open source (MIT/BSD) | ML-based, reasonable accuracy, active maintenance |
| **ChemAxon Marvin** | Commercial | Industry reference accuracy; a paid dependency and a licence-tier complication |
| Omit | — | Cheapest; leaves a known scientific gap in the ADMET modules |

**Recommendation: OPERA or an open ML predictor for Phase 1**, revisiting if accuracy proves limiting. Given the strict commercial-safe posture (Step 2 addendum §1), introducing a commercial dependency at the data-foundation layer is a decision to take deliberately rather than by default.

**Schema:** pKa is *predicted*, so it uses the prediction machinery — not a descriptor column.

```sql
INSERT INTO endpoint (endpoint_id, endpoint_class, display_name, canonical_unit,
                      is_categorical, expected_min, expected_max, higher_is_worse,
                      species_specific, unit_verified_method) VALUES
  ('pka_most_acidic','physicochemical','Most acidic pKa','pKa units',
   FALSE, -5, 20, NULL, FALSE, 'documented'),
  ('pka_most_basic', 'physicochemical','Most basic pKa','pKa units',
   FALSE, -5, 20, NULL, FALSE, 'documented');
```

Derived ionisation state, however, *is* deterministic given pKa, so it belongs with descriptors:

```sql
ALTER TABLE compound_descriptor
    ADD COLUMN n_acidic_groups   SMALLINT CHECK (n_acidic_groups >= 0),
    ADD COLUMN n_basic_groups    SMALLINT CHECK (n_basic_groups >= 0),
    ADD COLUMN charge_state_ph74 SMALLINT,
    ADD COLUMN fraction_neutral_ph74 NUMERIC(6,5)
        CHECK (fraction_neutral_ph74 BETWEEN 0 AND 1);
```

Acidic/basic group counts come from SMARTS matching (deterministic); `charge_state_ph74` and `fraction_neutral_ph74` derive from predicted pKa via Henderson–Hasselbalch and are therefore **only populated when a pKa prediction exists**, with the source prediction recorded in `descriptor_spec`.

---

## 5. Gap 2 — 3D Descriptors and a Reproducibility Hazard

3D descriptors (PMI, radius of gyration, molecular volume, PBF, NPR1/NPR2) require a generated conformer. This introduces a problem the rest of the schema is specifically designed to avoid.

**The hazard: conformer generation is stochastic.** RDKit's ETKDG embedding uses a random seed. Without a fixed seed, the same molecule yields different conformers on different runs, and therefore different 3D descriptors — silently, with no error. Every reproducibility guarantee in Step 2 §7 would be void for any model consuming them.

**Mitigation, mandatory if 3D descriptors are used at all:**

```sql
ALTER TABLE descriptor_spec
    ADD COLUMN conformer_seed        INTEGER,
    ADD COLUMN conformer_method      TEXT CHECK (conformer_method IN ('ETKDGv3','ETKDGv2','KDG','none')),
    ADD COLUMN conformer_n_attempts  SMALLINT CHECK (conformer_n_attempts > 0),
    ADD COLUMN conformer_ff          TEXT CHECK (conformer_ff IN ('MMFF94','MMFF94s','UFF','none')),
    ADD CONSTRAINT ck_conformer_seed_required
        CHECK (conformer_method = 'none' OR conformer_seed IS NOT NULL);
```

`ck_conformer_seed_required` makes seedless conformer generation impossible to configure. The constraint is trivial; the class of bug it prevents is not.

**Recommendation: defer 3D descriptors to Phase 3+.** For ADMET on datasets of 475–13,130 compounds (Step 1 [V]), 2D descriptors and graph representations are competitive with 3D approaches, and the conformer pipeline adds substantial cost and a reproducibility surface for uncertain gain. The schema is ready when they are justified.

---

## 6. Gap 3 — Structural Alerts

Referenced as `structural_alert_hit` in the Step 3 domain map but never defined. It matters more now than it did before the regulatory decision: **ICH M7's mandated expert rule-based methodology is, in substance, structural alert matching.** This table is what a rule-based mutagenicity model reads.

```sql
CREATE TABLE structural_alert (
    alert_uid       ulid PRIMARY KEY,
    alert_set       TEXT NOT NULL CHECK (alert_set IN (
        'PAINS_A','PAINS_B','PAINS_C','BRENK','NIH','CHEMBL',
        'GENOTOXIC','REACTIVE','LEAD_LIKE_EXCLUSION')),
    alert_name      TEXT NOT NULL,
    smarts          TEXT NOT NULL,
    description     TEXT NOT NULL,
    mechanism       TEXT,
    severity        TEXT CHECK (severity IN ('informational','caution','high_concern')),
    is_genotoxic_alert BOOLEAN NOT NULL DEFAULT FALSE,
    literature_ref  TEXT,
    source_id       TEXT NOT NULL REFERENCES data_source(source_id) ON DELETE RESTRICT,
    license_tier    license_tier_t NOT NULL,
    CONSTRAINT uq_alert UNIQUE (alert_set, alert_name)
);

CREATE TABLE compound_structural_alert (
    compound_uid    ulid NOT NULL REFERENCES compound(compound_uid) ON DELETE RESTRICT,
    alert_uid       ulid NOT NULL REFERENCES structural_alert(alert_uid) ON DELETE RESTRICT,
    descriptor_spec_version TEXT NOT NULL
        REFERENCES descriptor_spec(descriptor_spec_version) ON DELETE RESTRICT,
    match_count     SMALLINT NOT NULL CHECK (match_count > 0),
    matched_atom_indices INTEGER[] NOT NULL,
    PRIMARY KEY (compound_uid, alert_uid, descriptor_spec_version)
);
CREATE INDEX ix_alert_genotoxic ON compound_structural_alert (compound_uid)
    WHERE alert_uid IN (SELECT alert_uid FROM structural_alert WHERE is_genotoxic_alert);
CREATE INDEX ix_alert_by_alert  ON compound_structural_alert (alert_uid);
```

**`matched_atom_indices` supports the interpretability OECD Principle 5 asks for** — a rule-based prediction can point at the specific atoms triggering the alert, which is exactly what an expert reviewer needs under ICH M7 and what a regulator will expect to see.

**`is_genotoxic_alert`** partitions the DNA-reactivity alerts (aromatic nitro, aromatic amine, alkyl halide, epoxide, Michael acceptor, N-nitroso, azo, aldehyde) that feed the ICH M7 rule-based arm from the general-purpose promiscuity filters. Conflating PAINS with genotoxicity alerts would be a category error with regulatory consequences.

**Caveat retained from Step 2 §F:** alerts are advisory. PAINS in particular has well-documented false-positive rates and flags legitimate chemotypes. Automated rejection on alert count is not supported by the evidence; surfacing them for chemist review is.

---

## 7. Extended Drug-Likeness Rule Catalogue

Thresholds below verified 2026-08-05. Core rules (Lipinski, Veber, Ghose, Egan, Muegge, Ro3) are in Step 3 §4.3; these extend it.

| Rule | Criteria | Purpose | Reliability |
|---|---|---|---|
| **Pfizer 3/75** | Flag if cLogP > 3 **AND** TPSA < 75 Å² | In vivo tox risk. Original study: 245 Pfizer development compounds; those with LogP>3 & TPSA<75 were **~6× more likely** to show adverse events in rat or dog safety studies (24× for basic compounds) | ⚠️ **Not reproduced.** Later analyses do not confirm the original effect. Store as advisory only |
| **GSK 4/400** | Flag if cLogP > 4 **AND** MW > 400 | Higher risk of toxicity, off-target activity, development difficulty | Widely used heuristic |
| **Golden Triangle** | Favourable if 200 < MW < 500 **AND** −2 ≤ logD ≤ 5 | Balanced permeability/clearance | Heuristic; note it needs **logD**, so per §1 it depends on a measurement or prediction, not a computed descriptor |
| **Lead-likeness (Teague)** | MW ≤ 450; −3.5 ≤ logP ≤ 4.5; HBD ≤ 5; HBA ≤ 8; RotB ≤ 10; rings ≤ 4 | Starting points for optimisation, not final candidates | Established |
| **REOS** | MW 200–500; logP −5…5; HBD ≤ 5; HBA ≤ 10; charge −2…2; RotB ≤ 8; heavy atoms 15–50 | HTS library filtering | Established |
| **BBB likelihood** | TPSA < 90 Å²; MW < 450; HBD ≤ 3; 1 < logP < 4 | CNS penetration heuristic | Heuristic; CNS MPO is better |

```sql
ALTER TABLE compound_drug_likeness
    ADD COLUMN pfizer_3_75_flag   BOOLEAN,
    ADD COLUMN gsk_4_400_flag     BOOLEAN,
    ADD COLUMN golden_triangle_pass BOOLEAN,
    ADD COLUMN lead_like_pass     BOOLEAN,
    ADD COLUMN reos_pass          BOOLEAN,
    ADD COLUMN bbb_likelihood_pass BOOLEAN,
    ADD COLUMN mce_18             NUMERIC(8,3),
    ADD COLUMN rule_catalogue_version TEXT NOT NULL DEFAULT 'v1';
```

**`pfizer_3_75_flag` and `gsk_4_400_flag` are named `_flag`, not `_pass`.** They mark elevated risk, not failure; the naming is deliberate so a downstream developer cannot invert the semantics by assuming the `_pass` convention.

**`golden_triangle_pass` is nullable** because it requires logD, which may be absent. A rule that cannot be evaluated must return `NULL`, never `FALSE` — treating "unknown" as "failed" would silently penalise compounds for missing data.

**`rule_catalogue_version`** exists because these thresholds are literature conventions that get revised. Pfizer 3/75 is the cautionary case: it is widely cited, widely implemented, and its original finding has not held up. Versioning the catalogue means a future correction does not silently change historical verdicts.

### 7.1 A note on presenting these
Every rule in this section is a **heuristic derived from historical drug sets**, not a physical law. Novel chemotypes — macrocycles, PROTACs, covalent binders, peptidomimetics — routinely and successfully violate them. Reporting should present rule outcomes as descriptive context alongside the underlying property values, never as a verdict. Given Step 1's positioning of DrugSim as triage rather than gatekeeping, this is a consistency requirement, not just good manners.

---

## 8. Property Resolution View

The §1 correction creates a practical need: a chemist asking for logD should not have to know whether it is experimental or predicted. Precedence rule — **experimental beats predicted; among experimental, higher confidence and more recent; among predicted, in-domain beats out-of-domain, then higher quality score.**

```sql
CREATE VIEW compound_property_resolved AS
WITH exp AS (
    SELECT m.compound_uid, m.endpoint_id, m.canonical_value, m.canonical_unit,
           'experimental'::TEXT AS provenance,
           m.confidence_score AS score, m.ingested_at AS as_of,
           NULL::ad_verdict_t AS ad_verdict, m.license_tier,
           1 AS precedence
    FROM measurement m
    WHERE m.measurement_status = 'measured'
      AND m.value_relation = '='
      AND NOT m.is_deleted
), pred AS (
    SELECT p.compound_uid, p.endpoint_id, p.predicted_value, p.predicted_unit,
           'predicted'::TEXT, p.quality_score, p.predicted_at,
           p.ad_verdict, NULL::license_tier_t,
           2
    FROM prediction p
)
SELECT DISTINCT ON (compound_uid, endpoint_id) *
FROM (SELECT * FROM exp UNION ALL SELECT * FROM pred) u
ORDER BY compound_uid, endpoint_id, precedence,
         (ad_verdict IS DISTINCT FROM 'out_of_domain') DESC,
         score DESC NULLS LAST, as_of DESC;
```

**The `provenance` column is mandatory in any consumer.** A resolved property view is a convenience that makes it easy to forget whether a number was measured or guessed — precisely the confusion P4 guards against. Consumers must surface `provenance` and, where predicted, `ad_verdict`. This is a review checkpoint for any UI or report built on this view, not merely a recommendation.

---

## 9. Revised `compound_descriptor` — Final Column Set

Net changes from Step 3 §4.2: **removed** `logd_74`, `logs_mol_l`; **added** the constitutional, ring, topology and ionisation columns above. Full definition:

```sql
-- Core identity/mass
mw_g_mol, mw_parent_g_mol, exact_mass_g_mol, molecular_formula (on compound)
-- Lipophilicity (computed only)
logp_crippen, molar_refractivity
-- Polarity & H-bonding
tpsa_a2, hbd_lipinski, hba_lipinski, hbd_strict, hba_strict, labute_asa
-- Constitutional
heavy_atom_count, heteroatom_count, n_count, o_count, s_count, p_count,
halogen_count, formal_charge, n_radical_electrons, amide_bond_count,
quaternary_carbon_count
-- Rings & topology
ring_count, aromatic_rings, aliphatic_rings, saturated_rings,
aromatic_heterocycles, aromatic_carbocycles, spiro_atoms, bridgehead_atoms,
largest_ring_size, fused_ring_count, rotatable_bonds
-- Shape & complexity
fraction_csp3, fraction_aromatic_atoms, rotatable_bond_fraction,
num_stereocentres, bertz_ct, balaban_j, hall_kier_alpha, kappa1..3, chi0v..chi4v
-- Ionisation (populated only when pKa prediction exists)
n_acidic_groups, n_basic_groups, charge_state_ph74, fraction_neutral_ph74
```

VSA families and fingerprints beyond Morgan are **not** here — feature store, per §3.4.

---

## 10. Fingerprints

Only **Morgan r2 2048** persists in Postgres, as `compound.morgan_fp_r2_2048`, because the RDKit cartridge needs it for indexed similarity search (ADR-003).

All other fingerprint types — MACCS(166), RDKit FP, Atom Pair, Topological Torsion, Avalon, Morgan at other radii/lengths, count-based Morgan — live in the feature store, addressed by `feature_set_id`.

**Why not persist them all:** each is 2048 bits × 3M compounds ≈ 750 MB per fingerprint type, they are never human-queried, and they are cheap to recompute deterministically. Persisting them would inflate the system of record for no query benefit — the same principle as §3.4.

---

## 11. Open Decisions

1. **Stereoisomer enumeration policy** (§2.3) — affects the prediction API contract. My recommendation: enumerate ≤8, report range, highlight worst case.
2. **pKa predictor choice** (§4) — OPERA (public domain), open ML predictor, or a commercial dependency. Affects licence posture, which the addendum set to strict-commercial-safe.
3. **MCE-18 implementation** — not in core RDKit; needs a third-party dependency or in-house implementation. Low priority.
4. **3D descriptors** — recommend deferring to Phase 3+; schema is ready with the seed constraint.

---

## 12. Coverage Against the Brief

| Requested | Status |
|---|---|
| Compound ID, SMILES, Canonical, Isomeric, InChI, InChIKey | §2.1 — plus skeleton and parent layers |
| Molecular Formula, MW, Exact Mass | §9 |
| LogP | §9 (computed) |
| LogD, LogS | **§1 — relocated to measurement/prediction, with rationale** |
| TPSA, Rotatable Bonds, Aromatic Rings, Heavy Atom Count, Formal Charge, HBD, HBA | §9 |
| Lipinski, Veber, Ghose | Step 3 §4.3 |
| Bioavailability Score, Synthetic Accessibility, QED | Step 3 §4.3 |
| **Additional medicinal chemistry descriptors** | §3 (constitutional, ring, topology, VSA, complexity), §4 (ionisation), §5 (3D), §6 (structural alerts), §7 (extended rules) |

---

*End Step 4. Awaiting approval before Step 5 (ADMET Database Design).*
