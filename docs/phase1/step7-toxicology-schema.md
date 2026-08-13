# DrugSim — Phase 1, Step 7
## Toxicology Database

**Document status:** Draft for approval
**Date:** 2026-08-05
**Depends on:** Steps 1–6 (approved)
**Extends:** Step 3 §6.4 `measurement_toxicology`

---

## 1. Design Position

Toxicology is where DrugSim's claims are most consequential and its data is weakest. Step 1 verified the corpus behind the headline endpoints:

- **DILI (hepatotoxicity): 475 compounds** [V]
- **Carcinogens: 278 compounds** [V]
- **ClinTox: 1,484 compounds**, imbalanced, noisy labels [V]
- **Ames: 7,255 compounds** [V]
- **hERG: 648 / 13,445 / 306,893 across three datasets** [V]

The schema below is shaped by that. Three consequences run through it:

1. **Outcome and mechanism are separated.** "Hepatotoxic" is an observed outcome; "inhibits BSEP" is a mechanism. Conflating them prevents mechanistic reasoning and makes read-across impossible. §4 formalises this via Adverse Outcome Pathways.
2. **Dose is not optional.** Every toxic substance is non-toxic below some dose. A binary "toxic/non-toxic" label without dose context is scientifically incomplete, and the schema records dose wherever the source provides it.
3. **Assay detail is preserved, not flattened.** "Ames positive" is a summary of a five-strain panel run with and without metabolic activation. Flattening it discards the information a toxicologist needs (§3).

---

## 2. Toxicity Endpoint Registry

Covers every category in the brief. `tox_category` on `measurement_toxicology` (Step 3 §6.4) already constrains these values.

### 2.1 Organ-level outcomes
| `endpoint_id` | Display | Unit | Type | Source availability |
|---|---|---|---|---|
| `hepatotoxicity_dili` | Drug-induced liver injury | binary | cls | TDC DILI, 475 cpds [V] |
| `cardiotoxicity` | Cardiotoxicity (clinical) | binary | cls | Sparse |
| `nephrotoxicity` | Nephrotoxicity | binary | cls | **Sparse — see §7** |
| `neurotoxicity` | Neurotoxicity | binary | cls | **Sparse — see §7** |
| `developmental_toxicity` | Developmental/reproductive toxicity | binary | cls | ToxCast, limited |
| `clinical_toxicity` | Clinical trial toxicity failure | binary | cls | ClinTox, 1,484 [V] |

### 2.2 Genetic toxicology
| `endpoint_id` | Display | Unit | Type | Note |
|---|---|---|---|---|
| `ames_mutagenicity` | Ames bacterial reverse mutation | binary | cls | Panel — see §3 |
| `carcinogenicity` | Carcinogenicity | binary | cls | 278 cpds [V] |
| `genotoxicity_invitro` | In vitro genotoxicity (micronucleus/chromosome aberration) | binary | cls | — |
| `genotoxicity_invivo` | In vivo genotoxicity | binary | cls | — |

### 2.3 Mechanistic / in vitro
| `endpoint_id` | Display | Canonical unit | Type |
|---|---|---|---|
| `herg_inhibition` | hERG channel blockade | binary | cls |
| `herg_ic50` | hERG IC50 | nM | reg |
| `cytotoxicity_ic50` | General cytotoxicity IC50 | nM | reg |
| `bsep_inhibition` | BSEP inhibition (DILI mechanism) | binary | cls |
| `mitochondrial_toxicity` | Mitochondrial dysfunction | binary | cls |

### 2.4 Dose-descriptor endpoints
| `endpoint_id` | Display | Canonical unit | `higher_is_worse` |
|---|---|---|---|
| `ld50` | Median lethal dose | **mg/kg** | **FALSE** ⚠️ |
| `noael` | No-observed-adverse-effect level | **mg/kg/day** | **FALSE** |
| `loael` | Lowest-observed-adverse-effect level | mg/kg/day | FALSE |
| `bmd10` | Benchmark dose, 10 % response | mg/kg/day | FALSE |

**⚠️ `higher_is_worse = FALSE` for LD50 in mg/kg** — a higher lethal dose means a *safer* compound. This inverts if the value is stored in TDC's native `log(1/(mol/kg))` scale, where higher means more toxic. Step 2 §G.1 identified this as the highest-risk conversion in the system: a sign inversion trains cleanly, converges, and reports good metrics while ranking safe compounds as dangerous. The `endpoint` table's `NOT NULL` constraint on `higher_is_worse` exists specifically to force this decision to be recorded rather than assumed.

---

## 3. The Ames Test Is a Panel, Not a Boolean

Verified against OECD TG 471: the bacterial reverse mutation test requires **at least five strains** — *S. typhimurium* TA1535; TA1537 or TA97 or TA97a; TA98; TA100; and either TA102 or *E. coli* WP2 uvrA — each tested **with and without S9 metabolic activation**.

That is ten or more condition-level results per compound. Collapsing them to one boolean loses information that matters:

- **Strain identity indicates mutation type.** TA98 and TA1537 detect frameshift mutations; TA100 and TA1535 detect base-pair substitutions. Which strain responds tells you the mechanism.
- **S9 dependence is mechanistically decisive.** A compound positive *only* with S9 is not itself mutagenic — a **metabolite** is. This changes the risk assessment entirely and is directly relevant under ICH M7.

```sql
CREATE TABLE ames_panel_result (
    panel_result_uid ulid PRIMARY KEY,
    compound_uid     ulid NOT NULL REFERENCES compound(compound_uid) ON DELETE RESTRICT,
    strain           TEXT NOT NULL CHECK (strain IN
        ('TA98','TA100','TA102','TA1535','TA1537','TA97','TA97a','WP2_uvrA','WP2_uvrA_pKM101')),
    s9_activation    BOOLEAN NOT NULL,
    result           TEXT NOT NULL CHECK (result IN ('positive','negative','equivocal','not_tested')),
    fold_induction   NUMERIC(8,3) CHECK (fold_induction >= 0),
    max_concentration_ug_plate NUMERIC(12,3),
    is_cytotoxic_at_top BOOLEAN,
    guideline        TEXT CHECK (guideline IN ('OECD_TG_471','ICH_S2R1','other','unspecified')),
    is_glp           BOOLEAN,
    measurement_uid  ulid,
    measurement_license_tier license_tier_t,
    source_id        TEXT NOT NULL REFERENCES data_source(source_id) ON DELETE RESTRICT,
    license_tier     license_tier_t NOT NULL,
    FOREIGN KEY (measurement_uid, measurement_license_tier)
        REFERENCES measurement (measurement_uid, license_tier) ON DELETE RESTRICT,
    CONSTRAINT uq_ames_condition UNIQUE (compound_uid, strain, s9_activation, source_id)
);
CREATE INDEX ix_ames_compound ON ames_panel_result (compound_uid);

CREATE VIEW ames_overall AS
SELECT compound_uid,
       bool_or(result = 'positive')                          AS is_ames_positive,
       bool_or(result = 'positive' AND s9_activation)        AS positive_with_s9,
       bool_or(result = 'positive' AND NOT s9_activation)    AS positive_without_s9,
       bool_or(result = 'positive' AND s9_activation)
         AND NOT bool_or(result = 'positive' AND NOT s9_activation) AS requires_metabolic_activation,
       count(*) FILTER (WHERE result <> 'not_tested')        AS conditions_tested,
       count(DISTINCT strain) FILTER (WHERE result <> 'not_tested') AS strains_tested,
       count(DISTINCT strain) FILTER (WHERE result <> 'not_tested') >= 5 AS meets_tg471_strain_minimum
FROM ames_panel_result
GROUP BY compound_uid;
```

**`meets_tg471_strain_minimum`** flags whether the underlying data satisfies the guideline. Most public Ames data — including TDC's 7,255-compound set — is an aggregated call with no strain detail, so this will be `FALSE` for the majority. That is worth knowing explicitly: it distinguishes a guideline-compliant study from a literature summary, which matters under a regulatory path.

`equivocal` is a first-class result, not forced into positive or negative.

---

## 4. Adverse Outcome Pathways — the Mechanism Layer

The **AOP framework** is the OECD-endorsed structure for linking chemistry to toxicity, and it is the right backbone for a mechanistic toxicology layer. An AOP connects two anchor points — a **Molecular Initiating Event (MIE)** and an **Adverse Outcome (AO)** — through a chain of measurable **Key Events (KE)** joined by **Key Event Relationships (KER)**.

This matters for DrugSim beyond elegance. With 475 DILI compounds, a direct structure→hepatotoxicity model has a narrow applicability domain. But hepatotoxicity has known mechanisms — BSEP inhibition, mitochondrial dysfunction, reactive metabolite formation — each with substantially more data. **Predicting mechanisms and reasoning to the outcome is more defensible than predicting the outcome directly**, and it produces an explanation rather than a bare number. Under OECD Principle 5, that mechanistic interpretation is also a validation requirement.

```sql
CREATE TABLE aop (
    aop_uid        ulid PRIMARY KEY,
    aop_wiki_id    TEXT UNIQUE,
    title          TEXT NOT NULL,
    status         TEXT CHECK (status IN ('under_development','oecd_endorsed','wpha_approved','deprecated')),
    weight_of_evidence TEXT CHECK (weight_of_evidence IN ('high','moderate','low')),
    source_id      TEXT NOT NULL REFERENCES data_source(source_id) ON DELETE RESTRICT,
    license_tier   license_tier_t NOT NULL
);

CREATE TABLE aop_event (
    event_uid      ulid PRIMARY KEY,
    aop_wiki_event_id TEXT UNIQUE,
    event_type     TEXT NOT NULL CHECK (event_type IN ('molecular_initiating_event','key_event','adverse_outcome')),
    title          TEXT NOT NULL,
    biological_level TEXT CHECK (biological_level IN
        ('molecular','cellular','tissue','organ','individual','population')),
    protein_uid    ulid REFERENCES protein(protein_uid) ON DELETE RESTRICT,
    endpoint_id    TEXT REFERENCES endpoint(endpoint_id) ON DELETE RESTRICT
);

CREATE TABLE aop_event_membership (
    aop_uid    ulid NOT NULL REFERENCES aop(aop_uid) ON DELETE RESTRICT,
    event_uid  ulid NOT NULL REFERENCES aop_event(event_uid) ON DELETE RESTRICT,
    sequence_order SMALLINT NOT NULL CHECK (sequence_order >= 0),
    PRIMARY KEY (aop_uid, event_uid)
);

CREATE TABLE aop_key_event_relationship (
    ker_uid        ulid PRIMARY KEY,
    aop_uid        ulid NOT NULL REFERENCES aop(aop_uid) ON DELETE RESTRICT,
    upstream_event_uid   ulid NOT NULL REFERENCES aop_event(event_uid) ON DELETE RESTRICT,
    downstream_event_uid ulid NOT NULL REFERENCES aop_event(event_uid) ON DELETE RESTRICT,
    is_adjacent    BOOLEAN NOT NULL,
    evidence_level TEXT CHECK (evidence_level IN ('high','moderate','low')),
    CONSTRAINT ck_ker_distinct CHECK (upstream_event_uid <> downstream_event_uid),
    CONSTRAINT uq_ker UNIQUE (aop_uid, upstream_event_uid, downstream_event_uid)
);
```

**`aop_event.protein_uid` and `endpoint_id` are the crucial joins.** They connect the mechanistic framework to things DrugSim can actually predict: an MIE like "hERG blockade" links to both the hERG protein and the `herg_inhibition` endpoint. That is what turns an AOP from documentation into a reasoning structure.

Source: OECD AOP-Wiki / AOP-KB. **Licence to verify before ingestion** — not covered in Step 1.

---

## 5. Safety Margins — the Decision-Relevant Quantity

A hERG IC50 in isolation does not indicate cardiac risk. The risk quantity is the **safety margin**: hERG IC50 relative to expected free plasma concentration. A 1 µM IC50 is concerning for a drug with a 500 nM Cmax and irrelevant for one with a 5 nM Cmax.

```sql
CREATE TABLE safety_margin (
    margin_uid      ulid PRIMARY KEY,
    compound_uid    ulid NOT NULL REFERENCES compound(compound_uid) ON DELETE RESTRICT,
    hazard_endpoint_id TEXT NOT NULL REFERENCES endpoint(endpoint_id) ON DELETE RESTRICT,
    hazard_value_nm NUMERIC(14,4) NOT NULL CHECK (hazard_value_nm > 0),
    hazard_source   TEXT NOT NULL CHECK (hazard_source IN ('measured','predicted')),
    exposure_value_nm NUMERIC(14,4) CHECK (exposure_value_nm > 0),
    exposure_basis  TEXT CHECK (exposure_basis IN
        ('cmax_total','cmax_free','css_total','css_free','assumed_reference')),
    margin_fold     NUMERIC(12,3) CHECK (margin_fold > 0),
    risk_flag       TEXT CHECK (risk_flag IN ('low','moderate','high','indeterminate')),
    computed_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_margin_requires_exposure
        CHECK (margin_fold IS NULL OR exposure_value_nm IS NOT NULL)
);
```

**`exposure_basis = 'assumed_reference'` and `risk_flag = 'indeterminate'` exist because DrugSim will usually not know the exposure.** A novel designed molecule has no clinical Cmax. The honest output is "hERG IC50 = X, margin indeterminate without exposure data" — not a fabricated risk score built on an invented Cmax. `ck_margin_requires_exposure` makes a margin without an exposure basis impossible to store.

---

## 6. Literature References

The brief asks for literature references wherever possible. `measurement` carries `reference_doi` and `reference_pmid`, but a single-DOI column cannot represent multiple supporting citations or citations attached to non-measurement entities such as AOPs and structural alerts.

```sql
CREATE TABLE literature_reference (
    reference_uid ulid PRIMARY KEY,
    doi           TEXT UNIQUE,
    pmid          TEXT UNIQUE,
    pmcid         TEXT,
    title         TEXT NOT NULL,
    authors       TEXT[],
    journal       TEXT,
    publication_year SMALLINT CHECK (publication_year BETWEEN 1800 AND 2100),
    CONSTRAINT ck_ref_has_id CHECK (COALESCE(doi, pmid, pmcid) IS NOT NULL)
);

CREATE TABLE entity_reference (
    entity_table  TEXT NOT NULL,
    entity_pk     TEXT NOT NULL,
    reference_uid ulid NOT NULL REFERENCES literature_reference(reference_uid) ON DELETE RESTRICT,
    citation_role TEXT NOT NULL CHECK (citation_role IN
        ('primary_source','supporting','contradicting','method','review')),
    PRIMARY KEY (entity_table, entity_pk, reference_uid, citation_role)
);
CREATE INDEX ix_entref_ref ON entity_reference (reference_uid);
```

**`citation_role = 'contradicting'` is deliberate.** Toxicology literature frequently disagrees — one study finds a compound hepatotoxic, another does not. Storing only supporting citations produces a false impression of consensus. Recording contradicting evidence lets a report show the disagreement, which is what a scientist reviewing a triage output needs to see.

`entity_reference` uses a polymorphic `(entity_table, entity_pk)` pair rather than typed FKs. This is a deliberate exception to the schema's FK discipline: typed columns for every citable entity would mean a dozen nullable FKs and a CHECK enforcing exactly one non-null. Referential integrity is enforced by trigger instead, and it is listed alongside the other trigger-enforced rules in Step 3 §10.

---

## 7. Honest Data-Availability Assessment

Endpoints in the brief with **no adequate public source identified in Step 1**:

| Endpoint | Status | Consequence |
|---|---|---|
| **NOAEL** | No high-quality open dataset identified | Schema-ready, will remain empty. Carried forward from Step 3 §12 |
| **Nephrotoxicity** | No dedicated public dataset | Partial proxies only (FAERS signals, ToxCast renal assays) |
| **Neurotoxicity** | No dedicated public dataset | Partial proxies only |
| **Developmental toxicity** | Limited ToxCast coverage | Weak; not a defensible standalone claim |
| **Carcinogenicity** | 278 compounds [V] | Too small for a general-purpose model |

**Recommendation:** these endpoints exist in the schema so that data can be added when sourced, but they must **not** appear in any capability list, marketing material, or report template until populated and validated. An empty endpoint that renders as "no prediction available" is honest; one that renders a low-confidence guess from 278 training compounds is not.

This is the Step 1 §5.5 positioning applied concretely: the schema supports the full toxicology vocabulary, the product should claim only the parts with evidence behind them.

---

## 8. Cross-Reference: ICH M7 Integration

Under the regulatory path, mutagenicity has a prescribed workflow (Step 2 addendum §2, Step 3 §7.4):

1. **Rule-based arm** ← `compound_structural_alert` filtered on `is_genotoxic_alert` (Step 4 §6)
2. **Statistical arm** ← a `prediction` from a model with `methodology = 'statistical_based'` on `ames_mutagenicity`
3. Both feed `ich_m7_assessment`, whose two distinct FKs make a single-methodology assessment structurally impossible
4. Disagreement, out-of-domain, or equivocal results set `requires_expert_review`
5. `expert_review` records outcome, rationale and electronic signature
6. `final_class` records the ICH M7 classification (Class 1–5)

Experimental Ames data, where available, enters through `ames_panel_result` and takes precedence over both predictions — consistent with the resolution rule in Step 4 §8.

---

*End Step 7. Steps 5–7 complete; awaiting approval before Step 8 (Data Cleaning Pipeline).*
