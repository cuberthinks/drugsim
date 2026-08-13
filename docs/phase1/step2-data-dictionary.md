# DrugSim — Phase 1, Step 2
## Master Data Dictionary

**Document status:** Draft for approval
**Date:** 2026-08-05
**Companion:** `step2-data-architecture.md`
**Authority:** This document is normative. Where it conflicts with an implementation, the implementation is wrong.

---

## A. Conventions

### A.1 Verification tags
Carried forward from Step 1.

| Tag | Meaning |
|---|---|
| **[V]** | Verified against primary source |
| **[S]** | Secondary source |
| **[P]** | **Provisional** — literature-derived expectation, to be confirmed empirically at gate G4 |

**Why [P] exists and why it matters.** TDC does not publish units for most ADME/Tox endpoints — verified 2026-08-05 against both `tdcommons.ai/single_pred_tasks/adme/` and `.../tox/`. Every unit marked **[P]** is therefore an expectation from the primary literature, **not a documented fact**, and must be confirmed by distribution assertion (§K.4) before any model consumes it. Treating these as settled is the most likely path to a silent, systematic, product-invalidating error.

### A.2 Type system

| Logical type | PostgreSQL | Parquet | Notes |
|---|---|---|---|
| Surrogate key | `BIGINT` / `ULID CHAR(26)` | `INT64` / `BYTE_ARRAY` | Never structure-derived (ADR-008) |
| Chemical structure | `mol` (RDKit cartridge) | `BYTE_ARRAY` (SMILES) | Cartridge type enables indexed search |
| Fingerprint | `bfp` / `sfp` (RDKit) | `BYTE_ARRAY` | GiST-indexed |
| Continuous measurement | `NUMERIC(12,4)` | `DOUBLE` | **`NUMERIC`, not `FLOAT`** — see A.3 |
| Count | `INTEGER` | `INT32` | `CHECK (>= 0)` |
| Probability / score 0–1 | `NUMERIC(6,5)` | `DOUBLE` | `CHECK BETWEEN 0 AND 1` |
| Boolean flag | `BOOLEAN` | `BOOLEAN` | Never `INTEGER` |
| Enum | `TEXT` + `CHECK` or native `ENUM` | `BYTE_ARRAY` + dict | §C |
| Timestamp | `TIMESTAMPTZ` | `INT64 (micros, UTC)` | **Always TZ-aware, always UTC** |
| Free JSON | `JSONB` | `BYTE_ARRAY` | Narrow use only (ADR-003) |

### A.3 Why `NUMERIC` for measurements
Binary floating point cannot represent common decimal measurement values exactly, and error accumulates through unit conversion. For a system whose credibility rests on numeric fidelity — and where a converted, re-converted logS must round-trip — `NUMERIC` is the correct default. `DOUBLE` is used only in the feature store, where descriptors are recomputed rather than accumulated and performance matters.

### A.4 Naming
`snake_case`; tables singular (`compound`, not `compounds`); FKs as `{referenced_table}_uid`; booleans prefixed `is_`/`has_`; units suffixed where ambiguity is possible (`mw_g_mol`); source-native values prefixed `source_`.

---

## B. Cross-Cutting Metadata

**Every fact-bearing table carries these columns.** Non-negotiable — Step 1 verified BindingDB is internally split-licensed [V], so dataset-level provenance is provably insufficient (ADR-007).

| Field | Type | Null? | Description | Validation |
|---|---|---|---|---|
| `source_id` | `TEXT` | NO | Registry key (`chembl`, `bindingdb`, `tdc_caco2_wang`) | FK → `data_source`; must exist in `registry.yaml` |
| `source_version` | `TEXT` | NO | Upstream version (`chembl_37`, `invitrodb_v4.3`) | Non-empty |
| `source_record_id` | `TEXT` | YES | Native upstream ID (`CHEMBL25`, activity_id) | — |
| `snapshot_id` | `TEXT` | NO | `{version}__{date}__{sha256[:12]}` | Matches regex; FK → `ingestion_snapshot` |
| `source_license` | `TEXT` | NO | SPDX identifier | ∈ §C.1 |
| `license_tier` | `ENUM` | NO | `green` / `amber` / `red` / `black` | Derived from `source_license`; consistency asserted at G5 |
| `is_commercial_ok` | `BOOLEAN` | NO | Usable on a commercial path | `FALSE` ⟺ tier = `black` |
| `pipeline_version` | `TEXT` | NO | ETL git SHA | 40-char hex |
| `toolchain_id` | `TEXT` | NO | `rdkit-2026.03.1__python-3.12.4` | FK → `toolchain` |
| `ingested_at` | `TIMESTAMPTZ` | NO | UTC ingestion time | ≤ now() |
| `drugsim_release` | `TEXT` | NO | Core DB SemVer at publication | Matches `core-db-vN.N.N` |

**Storage cost is real and accepted.** At ~10⁷ rows this is a few GB of metadata. It is what makes the licence audit (G6) and the reproducibility contract (§7) mechanical rather than archaeological.

---

## C. Controlled Vocabularies

### C.1 `source_license` (SPDX)
`CC0-1.0` · `CC-BY-4.0` · `CC-BY-3.0` · `CC-BY-SA-4.0` · `CC-BY-SA-3.0` · `CC-BY-NC-SA-4.0` · `PDDL-1.0` · `US-PD` (US Government work) · `PROPRIETARY`

### C.2 `license_tier` — mapping is normative

| Tier | Licenses | Commercial path | Sources (Step 1 [V]) |
|---|---|---|---|
| `green` | `CC0-1.0`, `US-PD` | Unrestricted | PDB, Open Targets, Tox21/ToxCast, openFDA, DailyMed, Reactome, DSSTox |
| `amber` | `CC-BY-4.0`, `CC-BY-3.0` | Attribution only | UniProt, TDC (majority), BindingDB-curated portion, ChEBI, GO |
| `red` | `CC-BY-SA-4.0`, `CC-BY-SA-3.0` | **Permitted, ShareAlike unresolved** | ChEMBL, DrugCentral, SIDER, PharmGKB, BindingDB ChEMBL-derived portion |
| `black` | `CC-BY-NC-SA-4.0`, `PROPRIETARY` | **Prohibited** | **FreeSolv**, DrugBank, PDBbind (verify) |

### C.3 `measurement_status`
`measured` · `not_measured` · `below_loq` · `above_loq` · `inconclusive` · `withdrawn_by_source`
Enforces §8.4: `NULL` alone never encodes meaning.

### C.4 `value_relation`
`=` · `<` · `<=` · `>` · `>=` · `~`
Preserves censoring. **Records with relation ≠ `=` must never be treated as point values in training** without an explicit, recorded censoring-aware decision.

### C.5 `evidence_type`
`experimental` · `predicted` · `derived` · `expert_curated` · `text_mined` · `inferred_by_homology`
**Enforcement of P4:** `measurement` tables accept only `experimental`, `expert_curated`, `derived`. `predicted` in a measurement table is a constraint violation.

### C.6 `applicability_domain_verdict`
`in_domain` · `borderline` · `out_of_domain` · `undeterminable`

### C.7 `stereo_completeness`
`fully_defined` · `partially_defined` · `undefined` · `not_applicable`

### C.8 `standardization_flag` (multi-valued)
`salt_stripped` · `charge_neutralised` · `tautomer_canonicalised` · `isotope_removed` · `fragment_selected` · `metal_disconnected` · `unchanged`

---

## D. Compound Identity

| Field | Type | Unit | Null? | Description | Validation | Provenance |
|---|---|---|---|---|---|---|
| `compound_uid` | `ULID CHAR(26)` | — | NO | **Immutable internal PK** | Unique; never reused | Generated |
| `source_smiles` | `TEXT` | — | NO | SMILES exactly as received | Non-empty | Source, verbatim |
| `canonical_smiles` | `TEXT` | — | NO | RDKit canonical, no stereo | Round-trips to same mol | `Chem.MolToSmiles(mol, isomericSmiles=False)` |
| `isomeric_smiles` | `TEXT` | — | NO | Canonical with stereo | Round-trips | `Chem.MolToSmiles(mol, isomericSmiles=True)` |
| `standardized_smiles` | `TEXT` | — | NO | Post-standardisation (§8.1) | Idempotent under re-run | ChEMBL Structure Pipeline + RDKit |
| `parent_smiles` | `TEXT` | — | YES | Salt/solvate-stripped, neutralised | — | Standardisation step 4–5 |
| `inchi` | `TEXT` | — | NO | Standard InChI | Starts `InChI=1S/` | `Chem.MolToInchi` |
| `inchikey_full` | `CHAR(27)` | — | NO | Stereo/isotope-specific | `^[A-Z]{14}-[A-Z]{10}-[A-Z]$` | `Chem.MolToInchiKey` |
| `inchikey_skeleton` | `CHAR(14)` | — | NO | Connectivity block — **leakage prevention** | First 14 of full | Derived |
| `parent_inchikey` | `CHAR(27)` | — | YES | InChIKey of parent | Regex as above | Derived |
| `molecular_formula` | `TEXT` | — | NO | Hill notation | `^([A-Z][a-z]?\d*)+$` | `rdMolDescriptors.CalcMolFormula` |
| `bemis_murcko_scaffold` | `TEXT` | — | YES | BM scaffold SMILES | Valid SMILES or NULL (acyclic) | `MurckoScaffold.GetScaffoldForMol` |
| `generic_scaffold` | `TEXT` | — | YES | Atom/bond-type-agnostic framework | — | `MakeScaffoldGeneric` |
| `stereo_completeness` | `ENUM` | — | NO | §C.7 | ∈ enum | `FindMolChiralCenters(includeUnassigned=True)` |
| `standardization_flags` | `TEXT[]` | — | NO | §C.8 | Non-empty | Standardisation pipeline |
| `mol` | `mol` (cartridge) | — | NO | Binary structure for indexed search | — | RDKit cartridge |
| `morgan_fp_r2_2048` | `bfp` | — | NO | Morgan/ECFP4, radius 2, 2048 bits | — | `GetMorganFingerprintAsBitVect(m,2,2048)` |

**Join guidance — read before writing any query.** Use `parent_inchikey` for bioactivity aggregation (salt forms share pharmacology); `inchikey_full` for exact-entity dedup; `inchikey_skeleton` **only** for split assignment and stereoisomer grouping — never as a merge key, as it is stereochemistry-blind and stereoisomers can differ by orders of magnitude in both potency and toxicity.

---

## E. Physicochemical Descriptors

All computed under a pinned `toolchain_id`. **These values are not comparable across RDKit versions** (ADR-005).

| Field | Type | **Unit** | Range | RDKit provenance | Validation |
|---|---|---|---|---|---|
| `mw_g_mol` | `NUMERIC(10,4)` | **g/mol (Da)** | > 0 | `Descriptors.MolWt` | `> 0 AND < 10000` |
| `mw_parent_g_mol` | `NUMERIC(10,4)` | g/mol | > 0 | On parent structure | `> 0` |
| `exact_mass_g_mol` | `NUMERIC(12,6)` | **g/mol, monoisotopic** | > 0 | `Descriptors.ExactMolWt` | Within 0.5 of `mw_g_mol` |
| `logp_crippen` | `NUMERIC(8,4)` | **dimensionless** (log₁₀ P, octanol/water) | −10 … 15 | `Crippen.MolLogP` (Wildman–Crippen) | Warn outside −5…10 |
| `logd_74` | `NUMERIC(8,4)` | **dimensionless** (log₁₀ D at **pH 7.4**) | −10 … 15 | Experimental or predicted — **pH is part of the definition** | `ph_reference` NOT NULL |
| `logs_mol_l` | `NUMERIC(8,4)` | **log₁₀(mol/L)** | −14 … 2 | Experimental or predicted | Warn outside −13…1 |
| `tpsa_a2` | `NUMERIC(8,3)` | **Å²** | ≥ 0 | `Descriptors.TPSA` | `>= 0 AND < 1000` |
| `molar_refractivity` | `NUMERIC(8,3)` | **cm³/mol** | ≥ 0 | `Crippen.MolMR` | `>= 0` |
| `rotatable_bonds` | `INTEGER` | count | ≥ 0 | `Lipinski.NumRotatableBonds` — **strictness recorded** | `>= 0 AND < 200` |
| `aromatic_rings` | `INTEGER` | count | ≥ 0 | `rdMolDescriptors.CalcNumAromaticRings` | `>= 0` |
| `ring_count` | `INTEGER` | count | ≥ 0 | `rdMolDescriptors.CalcNumRings` | `>= 0` |
| `heavy_atom_count` | `INTEGER` | count | > 0 | `Descriptors.HeavyAtomCount` | `> 0` |
| `formal_charge` | `INTEGER` | **e** (elementary charge) | — | `Chem.GetFormalCharge` | `BETWEEN -20 AND 20` |
| `hbd_lipinski` | `INTEGER` | count | ≥ 0 | `Lipinski.NumHDonors` | `>= 0` |
| `hba_lipinski` | `INTEGER` | count | ≥ 0 | `Lipinski.NumHAcceptors` | `>= 0` |
| `hbd_strict` | `INTEGER` | count | ≥ 0 | `rdMolDescriptors.CalcNumHBD` | `>= 0` |
| `hba_strict` | `INTEGER` | count | ≥ 0 | `rdMolDescriptors.CalcNumHBA` | `>= 0` |
| `heteroatom_count` | `INTEGER` | count | ≥ 0 | `Lipinski.NumHeteroatoms` | `>= 0` |
| `fraction_csp3` | `NUMERIC(6,5)` | ratio 0–1 | 0–1 | `rdMolDescriptors.CalcFractionCSP3` | `BETWEEN 0 AND 1` |
| `num_stereocentres` | `INTEGER` | count | ≥ 0 | `FindMolChiralCenters` | `>= 0` |
| `largest_ring_size` | `INTEGER` | count | ≥ 0 | Ring info | `>= 0` |

### E.1 The HBD/HBA definitional trap — store both

**Correction (Sprint 2.5, verified against installed RDKit 2025.3.3):** this section originally named `Lipinski.NumHDonors` vs `rdMolDescriptors.CalcNumHBD` as the two divergent conventions. That was checked directly against RDKit source and is **wrong** — `Lipinski.NumHDonors` and `Lipinski.NumHAcceptors` are thin aliases that delegate directly to `rdMolDescriptors.CalcNumHBD`/`CalcNumHBA` (`rdkit/Chem/Lipinski.py`: `NumHDonors = lambda x: rdMolDescriptors.CalcNumHBD(x)`). They are the same function under two names in the currently pinned version; there is no divergence between them.

The genuine divergence — confirmed empirically across a battery of molecules (aspirin, sulfonamide, guanidine, aniline) — is between:
- **`Lipinski.NHOHCount` / `Lipinski.NOCount`** (= `CalcNumLipinskiHBD` / `CalcNumLipinskiHBA`): the literal, originally-published Rule-of-Five convention — donors = count of all N–H and O–H hydrogens; acceptors = count of all N and O atoms, with no chemical context considered.
- **`rdMolDescriptors.CalcNumHBD` / `CalcNumHBA`** (aliased, confusingly, as `Lipinski.NumHDonors`/`NumHAcceptors`): a chemically refined definition that excludes, for example, amide nitrogens and certain aromatic nitrogens as acceptors.

Example: aspirin's refined HBA (`CalcNumHBA`) is 3; its literal Lipinski HBA (`NOCount`) is 4 — the ester and both carbonyl/hydroxyl oxygens are counted differently under each convention.

Consequences that make this worth two columns instead of one:
- **Lipinski violation counts differ** depending on which is used, so drug-likeness verdicts differ
- Published comparisons are frequently non-reproducible because the paper does not state which was used
- Cross-source joins (ChEMBL publishes its own HBA/HBD) silently disagree
- **RDKit's own naming is actively misleading here**: a function living in the `Lipinski` module (`NumHDonors`) is *not* the historical Lipinski counting convention — that lives under the unrelated-looking names `NHOHCount`/`NOCount` in the same module. Anyone implementing this from the function names alone, without checking source, will pick the wrong pair — which is exactly what happened when this document was first written.

**Rule: `lipinski_*` rule evaluation uses `NHOHCount`/`NOCount` (the literal original convention); `*_strict` uses `CalcNumHBD`/`CalcNumHBA` (the refined convention).** The strict variants are available for modelling but must never be substituted into rule evaluation. `descriptor_definition_version` records the convention in force. See `src/drugsim_chem/descriptors.py` for the verified implementation.

### E.2 Rotatable bonds
RDKit offers strict and non-strict patterns (they differ on amide C–N bonds). The choice is recorded in `descriptor_spec_version`. Default: **strict** (amides not rotatable), consistent with Veber's original analysis.

---

## F. Drug-Likeness & Medicinal Chemistry Descriptors

Rule definitions are normative — each is stored as both component booleans and a violation count, never as a bare pass/fail. Collapsing to a single boolean discards the information a chemist actually needs.

| Field | Type | Unit | Definition | Validation |
|---|---|---|---|---|
| `lipinski_violations` | `INTEGER` | count 0–4 | MW ≤ 500; LogP ≤ 5; HBD_lipinski ≤ 5; HBA_lipinski ≤ 10 | `BETWEEN 0 AND 4` |
| `lipinski_pass` | `BOOLEAN` | — | `lipinski_violations <= 1` | Derived; consistency asserted |
| `veber_pass` | `BOOLEAN` | — | RotB ≤ 10 **AND** TPSA ≤ 140 Å² | Derived |
| `ghose_pass` | `BOOLEAN` | — | 160 ≤ MW ≤ 480; −0.4 ≤ LogP ≤ 5.6; 40 ≤ MR ≤ 130; 20 ≤ atom count ≤ 70 | Derived |
| `egan_pass` | `BOOLEAN` | — | TPSA ≤ 131.6 Å²; LogP ≤ 5.88 | Derived |
| `muegge_pass` | `BOOLEAN` | — | 200 ≤ MW ≤ 600; −2 ≤ LogP ≤ 5; TPSA ≤ 150; rings ≤ 7; C > 4; heteroatoms > 1; RotB ≤ 15; HBA ≤ 10; HBD ≤ 5 | Derived |
| `rule_of_three_pass` | `BOOLEAN` | — | Fragment-likeness: MW < 300; LogP ≤ 3; HBD ≤ 3; HBA ≤ 3; RotB ≤ 3 | Derived |
| `bioavailability_score` | `NUMERIC(4,3)` | probability | Martin (2005) tiers — see note below | ∈ {0.11, 0.17, 0.55, 0.56, 0.85} |
| `qed_score` | `NUMERIC(6,5)` | 0–1 | Quantitative Estimate of Drug-likeness (Bickerton 2012) | `BETWEEN 0 AND 1`; `QED.qed` |
| `sa_score` | `NUMERIC(5,3)` | **1–10** (1 = easy) | Ertl & Schuffenhauer synthetic accessibility | `BETWEEN 1 AND 10`; RDKit Contrib `sascorer` |
| `np_likeness_score` | `NUMERIC(6,3)` | −5 … 5 | Natural-product likeness | RDKit Contrib |
| `pains_alerts` | `INTEGER` | count | PAINS A/B/C substructure hits | `>= 0`; `FilterCatalog(PAINS)` |
| `brenk_alerts` | `INTEGER` | count | Brenk unwanted-substructure hits | `>= 0`; `FilterCatalog(BRENK)` |
| `nih_alerts` | `INTEGER` | count | NIH filter hits | `>= 0` |
| `cns_mpo_score` | `NUMERIC(4,2)` | 0–6 | Pfizer CNS MPO desirability | `BETWEEN 0 AND 6` |
| `ligand_efficiency` | `NUMERIC(8,4)` | **kcal/mol per heavy atom** | 1.37 × pActivity / HAC | Requires an activity value |
| `lipophilic_efficiency` | `NUMERIC(8,4)` | dimensionless | LLE = pActivity − LogP | Requires an activity value |
| `descriptor_spec_version` | `TEXT` | — | Pins definitions & RDKit conventions | FK → `descriptor_spec` |

**Note on `bioavailability_score`, corrected in Sprint 2.5:** this document originally guessed at a 4-tier charge×TPSA matrix. Verified against the actual rule (Martin, Y.C., *J. Med. Chem.* 2005, 48, 3164-3170): it is **not** symmetric. **Anions** are scored by TPSA alone — PSA≤75 → 0.85 (a tier the original guess omitted entirely); 75<PSA<150 → 0.56; PSA≥150 → 0.11. **Neutral, zwitterionic, or cationic** compounds are scored instead by whether they pass the **Lipinski Rule of Five** — 0.55 if pass, 0.17 if fail — with TPSA playing no role in that branch. It is a coarse heuristic derived from historical rat data, not a calibrated probability, and is flagged as such wherever it is reported.

**Known limitation:** "anion" in the real rule means the predominant ionisation state at physiological pH, which requires pKa prediction — explicitly deferred pending a pKa predictor decision (§4, §11). The implementation uses formal charge on the standardised input structure as a proxy, which misclassifies the common case of a carboxylic acid drawn/stored neutral but >99% ionised at pH 7.4. This is a real, currently-unresolved scientific limitation, not a rounding error, and should be revisited once ionisation-state prediction exists.

**Note on PAINS:** alert counts are advisory. PAINS filters have well-documented false-positive rates and flag legitimate chemotypes. They must be surfaced as flags for chemist review, never as automated rejection.

---

## G. Canonical Unit Registry — ADMET Endpoints

**This is the single most error-prone table in DrugSim.** Every unit marked **[P]** is provisional pending G4 empirical confirmation, because TDC does not document units [V, checked 2026-08-05].

| Endpoint | Canonical unit | Task type | Expected envelope (G4 assertion) | Status |
|---|---|---|---|---|
| **Absorption** |
| Caco-2 permeability | **log₁₀(cm/s)** | regression | −7.8 … −3.5, median ≈ −4.8 | **[P]** |
| PAMPA permeability | log₁₀(cm/s) | regression/binary | — | **[P]** |
| HIA | binary {0,1} | classification | class balance ≈ 0.8 positive | **[P]** |
| P-gp inhibition | binary {0,1} | classification | — | **[P]** |
| Oral bioavailability | binary {0,1} (F ≥ 20 % threshold) | classification | — | **[P]** |
| Lipophilicity (logD7.4) | **dimensionless**, pH 7.4 | regression | −1.5 … 4.5 | **[P]** |
| Aqueous solubility (logS) | **log₁₀(mol/L)** | regression | −13 … +2, median ≈ −2.6 | **[P]** |
| Hydration free energy | kcal/mol | regression | −25 … +4 | **[P]** · ⛔ **BLACK — excluded** |
| **Distribution** |
| BBB penetration | binary {0,1} | classification | — | **[P]** |
| Plasma protein binding | **% bound (0–100)** | regression | 0–100, left-skewed | **[P]** |
| VDss | **L/kg** | regression | 0.01 … 700, log-normal | **[P]** |
| **Metabolism** |
| CYP inhibition (1A2/2C9/2C19/2D6/3A4) | binary {0,1} | classification | — | **[P]** |
| CYP substrate (2C9/2D6/3A4) | binary {0,1} | classification | — | **[P]** |
| **Excretion** |
| Half-life | **hours** | regression | 0.05 … 500, log-normal | **[P]** |
| Clearance, hepatocyte | **µL/min/10⁶ cells** | regression | 0 … 200 | **[P]** ⚠️ high risk |
| Clearance, microsome | **mL/min/g protein** | regression | 0 … 500 | **[P]** ⚠️ high risk |
| **Toxicity** |
| hERG blockade | binary — blocks (1) / not (0) | classification | — | **[V]** |
| Ames mutagenicity | binary — mutagenic (1) / not (0) | classification | — | **[V]** |
| DILI | binary — liver injury (1) / not (0) | classification | — | **[V]** |
| Carcinogenicity | binary — carcinogenic (1) / not (0) | classification | — | **[V]** |
| ClinTox | binary | classification | encoding undocumented — **determine empirically** | **[P]** |
| Acute toxicity LD50 | source: **log(1/(mol/kg))**; canonical: **mg/kg** | regression | — | **[P]** ⚠️ highest risk |
| NOAEL | **mg/kg/day** | regression | — | **[P]** |
| **Potency (ChEMBL/BindingDB)** |
| IC50 / Ki / Kd / EC50 | **nM** | regression | pChEMBL 3–12 | **[V]** ChEMBL documents nM + pChEMBL |

### G.1 The two highest-risk conversions

**LD50 — sign convention *and* MW dependency.** TDC's label appears to be `log(1/(mol/kg))`, in which **higher means more toxic** — the inverse of intuition. Two independent failure modes:
1. **Sign inversion** produces a model that ranks safe compounds as toxic. It will train, converge, and report good metrics while being exactly backwards.
2. **MW dependency** — converting to mg/kg requires molecular weight, so the choice of *which* MW (salt vs. parent) is itself a scientific decision. It is recorded in `conversion_mw_basis`.

Both are checked at G4 by asserting that known-toxic reference compounds rank as toxic. A unit test with a handful of well-characterised compounds catches an inversion that no distribution check would.

**Clearance — units differ between the two AZ datasets.** Hepatocyte and microsome clearance use different denominators (per 10⁶ cells vs. per g protein). They are **not interchangeable** and must never be pooled into a single endpoint. They are stored as distinct endpoints with distinct units.

### G.2 Conversion audit fields
Per ADR-012, every converted measurement stores:

| Field | Type | Description |
|---|---|---|
| `source_value` | `NUMERIC(14,6)` | As received, unconverted |
| `source_unit` | `TEXT` | As received (or `undocumented`) |
| `canonical_value` | `NUMERIC(14,6)` | Post-conversion |
| `canonical_unit` | `TEXT` | From §G |
| `conversion_factor` | `NUMERIC(18,9)` | Multiplier applied |
| `conversion_formula` | `TEXT` | Symbolic, e.g. `10^(-x)*1e9` |
| `conversion_mw_basis` | `TEXT` | `parent` / `salt` / `n_a` — for mass↔molar |
| `unit_verified_method` | `ENUM` | `documented` / `range_assertion` / `cross_source` / `unverified` |

`unit_verified_method = 'unverified'` **blocks publication at G6.** Nothing reaches a model with unknown units.

---

## H. Experimental Measurement Fields

Applies to the ADMET and toxicology measurement tables. **`evidence_type` is constrained to exclude `predicted` (§C.5) — this is how P4 is enforced structurally rather than by convention.**

| Field | Type | Unit | Null? | Description | Validation |
|---|---|---|---|---|---|
| `measurement_uid` | `ULID` | — | NO | PK | Unique |
| `compound_uid` | `ULID` | — | NO | FK → `compound` | FK |
| `endpoint_id` | `TEXT` | — | NO | FK → `endpoint` (§G) | FK |
| `canonical_value` | `NUMERIC(14,6)` | per §G | YES | Harmonised value | Within envelope or flagged |
| `canonical_unit` | `TEXT` | — | NO | From §G registry | ∈ registry |
| `value_relation` | `ENUM` | — | NO | §C.4 — censoring | ∈ enum |
| `measurement_status` | `ENUM` | — | NO | §C.3 | ∈ enum |
| `evidence_type` | `ENUM` | — | NO | §C.5 | **≠ `predicted`** |
| `assay_uid` | `ULID` | — | YES | FK → `assay` | FK |
| `species` | `TEXT` | — | YES | NCBI taxon name | ∈ taxonomy |
| `tissue_or_system` | `TEXT` | — | YES | e.g. `human hepatocyte` | — |
| `ph_reference` | `NUMERIC(4,2)` | pH units | YES | **Mandatory for logD** | `BETWEEN 0 AND 14` |
| `temperature_c` | `NUMERIC(5,2)` | **°C** | YES | Assay temperature | `BETWEEN -80 AND 200` |
| `n_replicates` | `INTEGER` | count | YES | Replicate count | `> 0` |
| `std_error` | `NUMERIC(14,6)` | as value | YES | Reported uncertainty | `>= 0` |
| `loq_value` / `loq_unit` | `NUMERIC` / `TEXT` | — | YES | Required when status is `below_loq`/`above_loq` | Conditional NOT NULL |
| `reference_doi` | `TEXT` | — | YES | Literature DOI | DOI regex |
| `reference_pmid` | `TEXT` | — | YES | PubMed ID | Numeric |
| `confidence_score` | `NUMERIC(4,3)` | 0–1 | YES | Source-derived reliability (ChEMBL 0–9 rescaled) | `BETWEEN 0 AND 1` |
| `data_validity_flag` | `TEXT` | — | YES | ChEMBL `data_validity_comment` passthrough | — |
| *+ all §B metadata* | | | | | |

**Species is not optional in spirit.** Rat LD50 and human hepatotoxicity are different endpoints. Pooling across species because both are "toxicity" is a common and serious error; `species` participates in the endpoint uniqueness constraint.

---

## I. Prediction Fields

Separate table, separate lineage (P4). Every field below exists because Step 1 §5.5 established that DrugSim's honest positioning is prioritisation, and that requires uncertainty to be structural.

| Field | Type | Unit | Null? | Description | Validation |
|---|---|---|---|---|---|
| `prediction_uid` | `ULID` | — | NO | PK | Unique |
| `compound_uid` | `ULID` | — | NO | FK → `compound` | FK |
| `endpoint_id` | `TEXT` | — | NO | FK → `endpoint` | FK |
| `predicted_value` | `NUMERIC(14,6)` | per §G | NO | Point estimate | Within envelope |
| `predicted_unit` | `TEXT` | — | NO | Must match endpoint canonical unit | = §G |
| `prediction_interval_low` | `NUMERIC(14,6)` | as value | YES | Conformal lower bound | `<= predicted_value` |
| `prediction_interval_high` | `NUMERIC(14,6)` | as value | YES | Conformal upper bound | `>= predicted_value` |
| `interval_coverage` | `NUMERIC(4,3)` | 0–1 | YES | Nominal coverage (e.g. 0.90) | `BETWEEN 0 AND 1` |
| `confidence_score` | `NUMERIC(6,5)` | 0–1 | NO | **Calibrated** probability/confidence | `BETWEEN 0 AND 1` |
| `calibration_method` | `TEXT` | — | YES | `platt` / `isotonic` / `venn_abers` / `none` | ∈ enum |
| `ad_verdict` | `ENUM` | — | NO | §C.6 | ∈ enum |
| `ad_max_tanimoto` | `NUMERIC(6,5)` | 0–1 | NO | Max similarity to any training compound | `BETWEEN 0 AND 1` |
| `ad_knn_distance` | `NUMERIC(10,6)` | descriptor-space | YES | Mean distance to k nearest training compounds | `>= 0` |
| `ad_scaffold_seen` | `BOOLEAN` | — | NO | Query scaffold present in training set | — |
| `prediction_method` | `TEXT` | — | NO | `gnn` / `gbm_descriptor` / `rf` / `ensemble` / `qsar_readacross` | ∈ enum |
| `model_version` | `TEXT` | — | NO | FK → `model_registry` | FK |
| `feature_set_id` | `TEXT` | — | NO | Content hash (§6.2) | **Must equal model's training `feature_set_id`** |
| `training_snapshot_id` | `TEXT` | — | NO | FK → training snapshot | FK |
| `training_license_tiers` | `TEXT[]` | — | NO | Tiers consumed by the model | Non-empty |
| `is_commercial_ok` | `BOOLEAN` | — | NO | `FALSE` if any tier is `black` | Derived, asserted |
| `quality_score` | `NUMERIC(6,5)` | 0–1 | NO | Composite (§I.1) | `BETWEEN 0 AND 1` |
| `quality_score_formula_version` | `TEXT` | — | NO | Pins the composite definition | FK |
| `supporting_evidence` | `JSONB` | — | YES | Nearest training neighbours + measured values | Schema-validated |
| `predicted_at` | `TIMESTAMPTZ` | — | NO | UTC | ≤ now() |

### I.1 `quality_score` — composite, versioned
A single number for UI ranking, decomposed on demand. Components: applicability-domain verdict, interval width relative to endpoint spread, training-set size for that endpoint, measurement noise floor, and model validation performance.

**It is explicitly not a probability of correctness**, and reporting must never present it as one. The formula is versioned because it will change, and predictions made under different formulae are not comparable — a fact that must be recoverable, not assumed away.

### I.2 Structural enforcement of honesty
Three constraints that make the Step 1 positioning non-optional in code:
1. `feature_set_id` mismatch between prediction and model → **hard error**, preventing training/serving skew
2. `ad_verdict` is `NOT NULL` — a prediction cannot exist without a domain assessment
3. `predicted_unit` must equal the endpoint's canonical unit — no free-text units anywhere

---

## J. Protein / Target Fields

| Field | Type | Null? | Description | Validation |
|---|---|---|---|---|
| `protein_uid` | `ULID` | NO | Internal PK | Unique |
| `uniprot_accession` | `VARCHAR(10)` | NO | **Canonical protein identity** | UniProt accession regex |
| `uniprot_entry_name` | `TEXT` | YES | e.g. `EGFR_HUMAN` | — |
| `is_reviewed` | `BOOLEAN` | NO | Swiss-Prot (true) vs TrEMBL | **Ground truth requires `TRUE`** |
| `isoform_id` | `TEXT` | YES | e.g. `P00533-2` | — |
| `gene_symbol` | `TEXT` | YES | HGNC-approved | ∈ HGNC |
| `organism_taxon_id` | `INTEGER` | NO | NCBI taxon | ∈ taxonomy |
| `sequence` | `TEXT` | YES | Amino acid sequence | `^[ACDEFGHIKLMNPQRSTVWYUOXBZJ]+$` |
| `sequence_length` | `INTEGER` | YES | Residue count | `> 0`; consistent with `sequence` |
| `ec_number` | `TEXT` | YES | Enzyme Commission | `^\d+\.\d+\.\d+\.\d+$` |
| `protein_class` | `TEXT` | YES | e.g. `kinase`, `GPCR`, `transporter` | ∈ vocabulary |
| `is_enzyme` / `is_transporter` | `BOOLEAN` | NO | Role flags for §6/§7 tables | — |
| `target_confidence` | `INTEGER` | YES | ChEMBL 0–9 confidence | `BETWEEN 0 AND 9` |

**Rule:** `is_reviewed = FALSE` (TrEMBL) records may support coverage and exploration but are excluded from any training ground truth (Step 1 §3.6).

---

## K. Validation Rule Catalogue

Machine-checkable rules, referenced by ID in pipeline code and in test names.

### K.1 Identity (G3)
| ID | Rule | Severity |
|---|---|---|
| ID-01 | Every structure parses and sanitises under RDKit | **FAIL** |
| ID-02 | `inchikey_full` matches the 27-char pattern | **FAIL** |
| ID-03 | `inchikey_skeleton` = first 14 chars of `inchikey_full` | **FAIL** |
| ID-04 | Standardisation is idempotent (f(f(x)) = f(x)) | **FAIL** |
| ID-05 | `canonical_smiles` round-trips to an identical molecule | **FAIL** |
| ID-06 | No duplicate `inchikey_full` within a source | **WARN** → merge |
| ID-07 | Mixtures/multi-component structures flagged, not silently split | **WARN** |

### K.2 Descriptors (G3)
| ID | Rule | Severity |
|---|---|---|
| DS-01 | `exact_mass` within 0.5 Da of `mw` | **FAIL** |
| DS-02 | All counts ≥ 0 | **FAIL** |
| DS-03 | `qed_score`, `fraction_csp3` ∈ [0,1]; `sa_score` ∈ [1,10] | **FAIL** |
| DS-04 | `lipinski_violations` consistent with component descriptors | **FAIL** |
| DS-05 | `logp_crippen` outside [−5, 10] | **WARN** |
| DS-06 | Descriptors recomputed under a new `toolchain_id` differ → new `feature_set_id` | **FAIL** if reused |

### K.3 Licensing (G5/G6)
| ID | Rule | Severity |
|---|---|---|
| LC-01 | Every fact row has non-null `source_license` | **FAIL** |
| LC-02 | `license_tier` consistent with `source_license` mapping (§C.2) | **FAIL** |
| LC-03 | No `black`-tier record in a commercial-path artefact | **FAIL** |
| LC-04 | Upstream license unchanged since last snapshot | **FAIL** → human review |
| LC-05 | Attribution manifest regenerated and complete | **FAIL** |
| LC-06 | Model's `training_license_tiers` matches actual training data tiers | **FAIL** |

### K.4 Units & semantics (G4) — *the TDC-driven gate*
| ID | Rule | Severity |
|---|---|---|
| UV-01 | Observed min/max within the §G envelope | **FAIL** → manual unit determination |
| UV-02 | Distribution skewness consistent with log vs. linear scale | **WARN** |
| UV-03 | Overlapping compounds agree across sources within tolerance | **FAIL** |
| UV-04 | **Sign convention verified against known reference compounds** | **FAIL** |
| UV-05 | `unit_verified_method ≠ 'unverified'` before publication | **FAIL** |
| UV-06 | Censored records (`value_relation ≠ '='`) not silently coerced to point values | **FAIL** |

### K.5 Integration & leakage (G5/G6)
| ID | Rule | Severity |
|---|---|---|
| IN-01 | All FKs resolve | **FAIL** |
| IN-02 | No `split_group` in both train and test across **any** dataset pair | **FAIL** |
| IN-03 | `split_group` assignments unchanged from prior release | **FAIL** |
| IN-04 | Cross-source duplicates resolved to one `compound_uid` | **FAIL** |
| IN-05 | Conflicting measurements retained separately, never averaged in-place | **FAIL** |
| IN-06 | No `evidence_type = 'predicted'` in a measurement table | **FAIL** |

### K.6 Prediction integrity (Z5)
| ID | Rule | Severity |
|---|---|---|
| PR-01 | `feature_set_id` = model's training `feature_set_id` | **FAIL** |
| PR-02 | `ad_verdict` NOT NULL | **FAIL** |
| PR-03 | `predicted_unit` = endpoint canonical unit | **FAIL** |
| PR-04 | Interval bounds bracket the point estimate | **FAIL** |
| PR-05 | `out_of_domain` verdict present in API response and report | **FAIL** |

---

## L. Registry Schema

`datasets/registry.yaml` — the Z0 artefact. One entry per source; git-reviewed; drives ETL, licence audit, and freshness monitoring. See the companion file for the populated version covering the nine Tier 1 sources.

| Field | Required | Description |
|---|---|---|
| `source_id` | yes | Stable key |
| `name`, `homepage` | yes | Human reference |
| `upstream_version` | yes | e.g. `chembl_37` |
| `retrieval` | yes | Method, URL, checksum URL |
| `license.spdx`, `license.tier`, `license.commercial_ok`, `license.attribution` | yes | Drives §C.2 and LC-* |
| `cadence.expected_days`, `cadence.last_seen` | yes | Freshness monitoring |
| `verification.status`, `verification.date` | yes | Step 1 [V]/[S]/[U] carried forward |
| `notes` | no | Caveats (e.g. BindingDB split licensing) |

---

## M. Known Gaps

Stated rather than smoothed over:

1. **All TDC units are [P].** Confirmed empirically at G4 before first model training. Highest risk: LD50 sign convention, clearance denominators.
2. **TrEMBL entry count unverified**; PubChem and DailyMed figures unverified (network-blocked, Step 1).
3. **`quality_score` weights undefined** — requires model performance data from Phase 3. The field and versioning mechanism exist now; the formula is deliberately deferred rather than invented.
4. **NOAEL has no committed public source.** Present in the schema per the Step 7 brief, but Step 1 identified no high-quality open NOAEL dataset. Either a source is licensed or the endpoint stays unpopulated — it should not be quietly listed as a capability.
5. **ClinTox label encoding undocumented** — determine empirically.
6. **21 CFR Part 11 audit fields not included**, pending the regulatory-ambition decision (Step 1 open question 3). Retrofitting these is expensive; if the answer is yes, they enter the Step 3 ERD.

---

*End Step 2 (data dictionary). Awaiting approval before Step 3 (ERD & relational schema).*
