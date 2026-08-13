# DrugSim — Phase 1, Step 1
## Biomedical Dataset Survey & Source Selection

**Document status:** Draft for approval
**Date compiled:** 2026-08-05
**Owner:** Data Foundation workstream
**Supersedes:** none

---

## 0. Method & Epistemic Status

Every figure in this document is tagged so downstream readers know how much weight it carries. This matters: dataset record counts are quoted constantly in grant applications and investor decks, and most quoted figures in circulation are 2–4 years stale.

| Tag | Meaning |
|---|---|
| **[V]** | Verified live against the primary source on 2026-08-05 |
| **[S]** | Secondary source (blog, paper, search result); plausible but not confirmed at primary source |
| **[U]** | Unverified — primary source unreachable during compilation; treat as approximate |

**Sources that could not be reached during compilation** (corporate DNS/network filtering, not outages): `pubchem.ncbi.nlm.nih.gov`, `pubchemdocs.ncbi.nlm.nih.gov`, `dailymed.nlm.nih.gov`. Figures for PubChem and DailyMed are therefore **[S]/[U]** and must be re-confirmed before they appear in any external material. This is an action item, not a blocker — it does not change the tiering decisions below.

**A note on why this step got this much attention.** Dataset selection is the single least reversible decision in Phase 1. Schema mistakes get migrated; a licensing mistake that puts CC BY-SA data into a commercial prediction product gets discovered at due diligence, two years and one funding round later. Section 5 is the most commercially important part of this document, and I would rather over-invest there than in record counts.

---

## 1. Executive Summary

**Recommended Phase 1 ingestion set (Tier 1):** ChEMBL, PubChem, BindingDB, Therapeutics Data Commons, Tox21/ToxCast, UniProt, PDB, DrugCentral, Open Targets.

**Three findings that should change the plan:**

1. **The ADMET training data problem is not a data-volume problem.** ChEMBL holds 24.5M bioactivity measurements [V], but the entire TDC ADMET Benchmark Group — the actual, curated, model-ready ADMET corpus the field trains on — spans **22 datasets of 475 to 13,130 molecules each** [V]. The largest experimental human oral-bioavailability set in public circulation is ~640 compounds. DrugSim's headline product is bounded by datasets of a few hundred to a few thousand molecules, not by millions. Architecture, model choice, and — most importantly — the uncertainty-quantification requirement in Step 5 must be built around that reality. Any plan premised on "we have millions of ADMET data points" is wrong.

2. **ShareAlike copyleft runs through the core of the ecosystem.** ChEMBL (CC BY-SA 3.0) [V], DrugCentral (CC BY-SA 4.0) [S], SIDER (CC BY-SA 4.0) [V], PharmGKB (CC BY-SA 4.0) [S], and the ChEMBL-derived portion of BindingDB (CC BY-SA 3.0) [V] all carry ShareAlike. For a commercial SaaS this is a live, unsettled legal question, not a formality. It is answerable and workable, but it must be answered deliberately — see §5.

3. **Two named sources in the brief are effectively dead or degraded.** SIDER's last release was **4.1, 21 Oct 2015**, on MedDRA 16.1 [V]; its own maintainers state funding has ended and the data is outdated, with an EBI successor planned to begin in 2026 [V]. Building a side-effect module on SIDER means shipping 2015-era pharmacovigilance. openFDA FAERS (quarterly, Public Domain/CC0, records from 2014Q1) [V] is the live alternative and should carry that load.

---

## 2. Verified Scale Snapshot

Ordered by relevance to DrugSim, with verification status. Use this table as the citable reference; do not re-derive these numbers from memory.

| Source | Release / As-of | Headline scale | Status |
|---|---|---|---|
| **ChEMBL** | v37, prepared 01/05/2026, FTP-dated 2026-06-02 | 2,921,148 distinct compounds; 3,824,604 compound records; **24,527,044 activities**; 1,970,438 assays; 18,552 targets; 101,100 documents; 101 bioassay data sources | **[V]** |
| **PubChem** | ~Sept 2025 | 122M compounds; 338M substances; 1.77M bioassays; 1,072 data sources | **[S]** |
| **BindingDB** | live homepage | 3.2M binding measurements; 1.4M compounds; 11.5K protein targets. Curator-curated subset: 1.6M data / 765K compounds / 4.8K targets | **[V]** |
| **PDB (RCSB)** | live homepage | 257,629 experimental (257,235 experimental + 394 integrative); **1,062,058 Computed Structure Models** (992,732 AlphaFoldDB + 69,326 ModelArchive) | **[V]** |
| **UniProt** | 2026_02, released 10-Jun-2026 | Swiss-Prot (reviewed): **575,503 entries**, 312,871 unique references, 208,906,902 aa. TrEMBL count not confirmed | **[V]** / TrEMBL **[U]** |
| **TDC — ADMET Benchmark Group** | current | **22 datasets, 475–13,130 molecules**, scaffold split 80/20 | **[V]** |
| **ToxCast / Tox21** | invitrodb v4.3 current (v3.5 Aug 2022, v3.4 Oct 2021) | >9,500 chemicals; 625 assays; 1,496 endpoints | **[S]** |
| **DrugCentral** | "DrugCentral 2023" per site | ~4,995 active ingredients; 152,476 pharmaceutical products | **[S]** |
| **SIDER** | **4.1, 21 Oct 2015** (MedDRA 16.1) | 1,430 drugs; 5,868 side effects; 139,756 drug–SE pairs (~40% with frequency) | **[V]** |
| **openFDA FAERS** | quarterly, ~3-month lag, from 2014Q1 | Adverse event + medication error reports, MedDRA-coded | **[V]** |
| **DailyMed** | — | SPL drug labels; counts unverified | **[U]** |

### 2.1 ChEMBL 37 date reconciliation
The release notes state "prepared on 01/05/2026" while the FTP file is dated 2026-06-02. EBI uses DD/MM/YYYY, so this reads as **prepared 1 May 2026, published early June 2026**. Record it as `chembl_37` with `prepared_date = 2026-05-01`, `published_date = 2026-06-02` — never as a bare "2026". Ambiguous date formats in provenance metadata cause reproducibility failures that are painful to debug later.

---

## 3. Tier 1 Dataset Profiles

Full 14-field profiles for sources recommended for Phase 1 ingestion.

---

### 3.1 ChEMBL — **Priority: HIGH** (anchor source)

| Field | Detail |
|---|---|
| **Official website** | https://www.ebi.ac.uk/chembl/ · FTP: https://ftp.ebi.ac.uk/pub/databases/chembl/ChEMBLdb/latest/ |
| **Scientific purpose** | Manually curated bioactivity database abstracted from medicinal chemistry literature and patents. The reference corpus for structure–activity relationships. |
| **Data categories** | Compound structures & calculated properties; bioactivities (IC50/Ki/Kd/EC50, pChEMBL); assays & assay classification; targets & target hierarchy; documents; drug mechanisms; indications; ADMET-type assays; drug warnings/withdrawal; new in v37: targeted protein degradation (~29,000 bioactivity points), pesticide classification, veterinary flag |
| **Records** | 2.92M compounds / 24.53M activities / 1.97M assays / 18,552 targets **[V]** |
| **File formats** | Oracle, MySQL, PostgreSQL dumps; SQLite (5.4 GB); SDF; FASTA; FPS fingerprints; HDF5; RDF; REST API |
| **Licensing** | **CC BY-SA 3.0 Unported** (confirmed via `LICENSE` file in FTP release directory) **[V]** |
| **Commercial restrictions** | Commercial use permitted. **ShareAlike obligation attaches to adapted material** — see §5. Additional caveat: some calculated properties derive from commercial software; ChEMBL advises users to respect those vendors' terms **[S]** |
| **Update frequency** | ~2 releases/year (v35 Dec 2024 → v36 Sep 2025 → v37 Jun 2026) |
| **Data quality** | **Highest tier.** Manual expert curation; explicit `pchembl_value` standardisation; `data_validity_comment` flags (outside typical range, potential author/transcription error, manually validated); `confidence_score` 0–9 on target assignment |
| **Strengths** | Curated not scraped; standardised units; assay-level provenance to source document; target confidence scoring; stable identifiers; excellent schema documentation |
| **Weaknesses** | Literature-derived → **strong publication bias toward actives**; heterogeneous assay protocols make cross-assay values non-comparable without care; activity cliffs and errors persist despite curation; ShareAlike is a commercial complication |
| **Integration difficulty** | **Low–Medium.** Well-documented relational schema, direct SQL load. Difficulty is scientific (deciding what to trust), not technical |
| **Rationale** | Non-negotiable. The backbone of compound identity, bioactivity, and target linkage. |

**Engineering notes.** Load the PostgreSQL dump directly rather than parsing SDF — the relational schema preserves assay/document provenance that SDF discards. Filter on `confidence_score >= 8` and `standard_relation = '='` for any training set. Treat `pchembl_value` as the only cross-comparable potency field.

---

### 3.2 PubChem — **Priority: HIGH** (breadth & identity resolution)

| Field | Detail |
|---|---|
| **Official website** | https://pubchem.ncbi.nlm.nih.gov/ |
| **Scientific purpose** | The largest open chemical information aggregator; NIH/NCBI repository of substances, standardised compounds, and bioassay results. |
| **Data categories** | Compounds (standardised structures); Substances (as-deposited); BioAssays; bioactivities; computed & experimental properties; patents; literature links; classifications; toxicity/safety (GHS) |
| **Records** | ~122M compounds; ~338M substances; ~1.77M bioassays; 1,072 sources (Sept 2025) **[S]** |
| **File formats** | SDF, ASN.1, XML, JSON, CSV; PUG-REST & PUG-View APIs; bulk FTP |
| **Licensing** | Core PubChem content is **US Government work / public domain**. **Critical caveat:** PubChem is an aggregator — individual depositor records may carry their own terms **[S]** |
| **Commercial restrictions** | Generally none on core content. **Per-depositor diligence required** for any specific depositor's data you rely on materially |
| **Update frequency** | Continuous / daily |
| **Data quality** | **Variable by design.** Compound layer is well-standardised. Substance and BioAssay layers are as-deposited and unvalidated — quality ranges from excellent to unusable |
| **Strengths** | Unmatched coverage; best-in-class identifier cross-referencing (CID/SID/InChIKey/CAS/registry IDs); permissive licensing; excellent APIs; GHS safety data |
| **Weaknesses** | No curation guarantee; HTS bioassays are noisy with severe class imbalance and frequent-hitter artefacts; enormous volume forces selective ingestion; aggregation means license heterogeneity |
| **Integration difficulty** | **Medium.** APIs are easy; full-scale bulk ingestion is a real data-engineering exercise (hundreds of GB) |
| **Rationale** | Adopt as the **chemical identity resolution spine** (InChIKey ↔ CID ↔ everything else). Ingest selectively; do not mirror wholesale in Phase 1. |

---

### 3.3 BindingDB — **Priority: HIGH**

| Field | Detail |
|---|---|
| **Official website** | https://www.bindingdb.org/ |
| **Scientific purpose** | Public database of measured protein–small molecule binding affinities; the reference source for quantitative binding data. |
| **Data categories** | Ki, Kd, IC50, EC50; protein targets w/ UniProt mapping; compounds; assay conditions; patent-derived affinity data; curated links to PDB |
| **Records** | 3.2M measurements; 1.4M compounds; 11.5K targets. **Curator-curated subset: 1.6M data / 765K compounds / 4.8K targets** **[V]** |
| **File formats** | TSV, SDF, XML, SQL dumps; REST API; ready-made target-based training sets |
| **Licensing** | **Split-licensed** — BindingDB-curated data under **CC BY 3.0**; ChEMBL-imported data under **CC BY-SA 3.0 Unported** **[V]** |
| **Commercial restrictions** | Both permit commercial use. **The provenance split is operationally important**: the BindingDB-curated portion is CC BY (no copyleft), the ChEMBL-derived portion carries ShareAlike |
| **Update frequency** | Monthly / continuous |
| **Data quality** | High for the curated subset; aggregate includes imported data inheriting upstream quality |
| **Strengths** | Deepest quantitative binding-affinity coverage; strong UniProt & PDB cross-links; patent-derived data unavailable elsewhere; purpose-built ML training sets |
| **Weaknesses** | Overlaps heavily with ChEMBL — **deduplication is mandatory or you will double-count and leak between train/test**; split licensing demands per-record provenance tracking; assay conditions vary |
| **Integration difficulty** | **Medium.** Ingestion is easy; correct deduplication against ChEMBL and per-record license tagging are the real work |
| **Rationale** | Include — but store a `source_license` field **per record**, not per dataset. This is the source that makes per-record license tracking non-optional (see §5.3). |

---

### 3.4 Therapeutics Data Commons (TDC) — **Priority: HIGH** (ADMET model layer)

| Field | Detail |
|---|---|
| **Official website** | https://tdcommons.ai/ · https://github.com/mims-harvard/TDC |
| **Scientific purpose** | Curated, ML-ready benchmark datasets and standardised evaluation harnesses for therapeutic science. The field's de facto ADMET benchmark. |
| **Data categories** | ADMET Benchmark Group (22 datasets); single-instance prediction; multi-instance (DTI); generation tasks; standardised scaffold splits |
| **Records** | **475 – 13,130 molecules per dataset** **[V]** — see §3.4.1 |
| **File formats** | Python package (`PyTDC`); CSV/TSV; pandas-native |
| **Licensing** | **Per-dataset, not uniform.** Majority **CC BY 4.0**. **Exception: FreeSolv (Hydration Free Energy) is CC BY-NC-SA 4.0** **[V]** |
| **Commercial restrictions** | **FreeSolv's NC clause prohibits commercial use.** It must be excluded from any commercial DrugSim model or flagged and gated. Verify each dataset's license individually at ingestion — do not assume uniformity |
| **Update frequency** | Continuous (GitHub); benchmark versions pinned |
| **Data quality** | High curation for ML; standardised splits enable honest comparison. Quality is inherited from heterogeneous upstream sources |
| **Strengths** | Directly usable as DrugSim's ADMET training substrate; scaffold splits prevent the optimistic bias of random splits; community leaderboards give external benchmarks; low integration cost |
| **Weaknesses** | **Small datasets** — this is the binding constraint on DrugSim's accuracy; upstream heterogeneity; measurement noise floors accuracy regardless of model; some datasets have known label-quality issues |
| **Integration difficulty** | **Low.** `pip install PyTDC`. Lowest-effort/highest-value source in the survey |
| **Rationale** | The fastest credible path to a working ADMET module, with published baselines to prove DrugSim is competitive rather than merely functional. |

#### 3.4.1 TDC ADMET datasets — verified sizes & licenses **[V]**

**Absorption**

| Dataset | Size | License |
|---|---|---|
| Caco-2 (Wang et al.) | 906 | CC BY 4.0 |
| PAMPA Permeability (NCATS) | 2,035 | CC BY 4.0 |
| HIA (Hou et al.) | 578 | CC BY 4.0 |
| Pgp Inhibition (Broccatelli et al.) | 1,212 | CC BY 4.0 |
| Bioavailability (Ma et al.) | 640 | CC BY 4.0 |
| Lipophilicity (AstraZeneca) | 4,200 | CC BY 4.0 |
| Solubility (AqSolDB) | 9,982 | CC BY 4.0 |
| Hydration Free Energy (FreeSolv) | 642 | ⚠️ **CC BY-NC-SA 4.0** |

**Distribution**

| Dataset | Size | License |
|---|---|---|
| BBB (Martins et al.) | 1,975 | CC BY 4.0 |
| PPBR (AstraZeneca) | 1,614 | CC BY 4.0 |
| VDss (Lombardo et al.) | 1,130 | CC BY 4.0 |

**Metabolism**

| Dataset | Size | License |
|---|---|---|
| CYP2D6 Inhibition (Veith et al.) | 13,130 | CC BY 4.0 |
| CYP2C19 Inhibition (Veith et al.) | 12,665 | CC BY 4.0 |
| CYP1A2 Inhibition (Veith et al.) | 12,579 | CC BY 4.0 |
| CYP3A4 Inhibition (Veith et al.) | 12,328 | CC BY 4.0 |
| CYP2C9 Inhibition (Veith et al.) | 12,092 | CC BY 4.0 |
| CYP2C9 Substrate (Carbon-Mangels et al.) | 666 | CC BY 4.0 |
| CYP3A4 Substrate (Carbon-Mangels et al.) | 667 | CC BY 4.0 |
| CYP2D6 Substrate (Carbon-Mangels et al.) | 664 | CC BY 4.0 |

**Excretion**

| Dataset | Size | License |
|---|---|---|
| Half Life (Obach et al.) | 667 | CC BY 4.0 |
| Clearance Hepatocyte (AstraZeneca) | 1,102 | CC BY 4.0 |
| Clearance Microsome (AstraZeneca) | 1,020 | CC BY 4.0 |

**Toxicity**

| Dataset | Size | License |
|---|---|---|
| hERG Central | 306,893 | CC BY 4.0 |
| hERG (Karim et al.) | 13,445 | CC BY 4.0 |
| hERG blockers | 648 | CC BY 4.0 |
| Acute Toxicity LD50 | 7,385 | CC BY 4.0 |
| Ames Mutagenicity | 7,255 | CC BY 4.0 |
| Tox21 | ~6,000 | CC BY 4.0 |
| ClinTox | 1,484 | CC BY 4.0 |
| DILI | 475 | CC BY 4.0 |
| Skin Reaction | 404 | CC BY 4.0 |
| Carcinogens | 278 | CC BY 4.0 |
| ToxCast | hundreds–thousands | CC BY 4.0 |

**Read the excretion and hepatotoxicity rows carefully.** Human half-life: 667 compounds. DILI: 475 compounds. These are the datasets behind two of DrugSim's headline claims. §5.5 and Step 5 must be designed around this.

---

### 3.5 Tox21 / ToxCast — **Priority: HIGH**

| Field | Detail |
|---|---|
| **Official website** | https://tox21.gov/ · https://www.epa.gov/comptox-tools/toxicity-forecasting-toxcast · https://comptox.epa.gov/dashboard/ |
| **Scientific purpose** | US federal (EPA/NIH/FDA/NCATS) high-throughput in vitro screening programme for hazard prioritisation across nuclear receptor, stress response, and other pathways. |
| **Data categories** | Concentration–response HTS; assay endpoint definitions; curve fits & hit calls; chemical identity (DSSTox); cytotoxicity burst filters |
| **Records** | >9,500 chemicals; 625 assays; 1,496 endpoints; invitrodb v4.3 current **[S]** |
| **File formats** | MySQL `invitrodb` dump; CSV summary files (EPA Figshare); CompTox Dashboard; CTX APIs; R packages `tcpl`, `tcplfit2`, `ctxR` |
| **Licensing** | **US Government work — public domain** |
| **Commercial restrictions** | **None.** Cleanest licensing of any major bioactivity source |
| **Update frequency** | Periodic major versions (v3.4 Oct 2021 → v3.5 Aug 2022 → v4.3) |
| **Data quality** | High experimental rigour and full transparency — raw concentration–response, documented curve-fitting, explicit flags. Quality is *knowable*, which is rarer and more valuable than quality being uniformly high |
| **Strengths** | Public domain; genuine mechanistic (pathway-level) toxicity signal; enormous negative-data volume — rare and essential for calibration; reproducible open-source pipeline; DSSTox gives clean chemical identity |
| **Weaknesses** | **In vitro ≠ in vivo** — translating to organ-level human toxicity is the unsolved scientific problem, not an engineering one; assay interference & cytotoxicity burst artefacts; environmental/industrial chemical space skews away from drug-like space; steep domain learning curve |
| **Integration difficulty** | **Medium–High.** invitrodb is large and its schema assumes toxicology domain knowledge; correct use of hit calls and burst filters requires care |
| **Rationale** | Ingest. Public domain status plus large-scale negatives makes it disproportionately valuable for honest model calibration. Budget real domain-expert time. |

---

### 3.6 UniProt — **Priority: HIGH**

| Field | Detail |
|---|---|
| **Official website** | https://www.uniprot.org/ |
| **Scientific purpose** | The universal protein sequence and functional annotation knowledgebase. |
| **Data categories** | Sequences; functional annotation; GO terms; domains & sites; PTMs; variants; isoforms; cross-references (PDB, ChEMBL, Reactome, DrugBank); subcellular localisation; enzyme (EC) classification |
| **Records** | Swiss-Prot (reviewed): **575,503** entries, 312,871 references, 208,906,902 aa — release 2026_02, 10-Jun-2026 **[V]**. TrEMBL (unreviewed): ~250M+ **[U]** |
| **File formats** | FASTA, XML, RDF, flat text, TSV, JSON; REST API; SPARQL; bulk FTP |
| **Licensing** | **CC BY 4.0** **[S — multiple concurring sources]** |
| **Commercial restrictions** | **None beyond attribution.** No ShareAlike. Commercially clean |
| **Update frequency** | ~8-week release cycle |
| **Data quality** | Swiss-Prot is the gold standard for manual biocuration. TrEMBL is automated — useful for coverage, unsuitable as ground truth |
| **Strengths** | Authoritative protein reference; the universal join key (accession) across biomedical data; superb cross-referencing; evidence codes distinguish experimental from inferred; permissive license |
| **Weaknesses** | Swiss-Prot/TrEMBL quality gap must be respected in every query; annotation lag; isoform handling adds modelling complexity |
| **Integration difficulty** | **Low–Medium.** Well-structured, well-documented, stable identifiers |
| **Rationale** | The canonical protein entity table. **All protein references in DrugSim resolve to UniProt accessions** — ChEMBL targets, BindingDB targets, PDB chains, and Open Targets all map here. Restrict ground-truth use to Swiss-Prot. |

---

### 3.7 Protein Data Bank (RCSB PDB) — **Priority: HIGH**

| Field | Detail |
|---|---|
| **Official website** | https://www.rcsb.org/ · https://www.wwpdb.org/ |
| **Scientific purpose** | The global archive of experimentally determined 3D biomolecular structures. |
| **Data categories** | Experimental structures (X-ray, cryo-EM, NMR); ligand chemistry (Chemical Component Dictionary); binding sites; validation reports; Computed Structure Models |
| **Records** | **257,629 experimental** (257,235 experimental + 394 integrative); **1,062,058 CSMs** (992,732 AlphaFoldDB + 69,326 ModelArchive) **[V]** |
| **File formats** | PDB, mmCIF/PDBx, PDBML, MMTF/BinaryCIF; REST & GraphQL APIs; rsync/FTP |
| **Licensing** | **CC0 1.0 (public domain dedication)** |
| **Commercial restrictions** | **None whatsoever.** The cleanest license in the survey |
| **Update frequency** | Weekly (Wednesdays) |
| **Data quality** | High but **heterogeneous** — resolution, R-free, and ligand fit quality vary enormously. Validation reports are essential, not optional. CSMs are predictions and must be stored as a distinct entity type with confidence (pLDDT) |
| **Strengths** | CC0; experimental ground truth for structure; ligand-bound complexes enable structure-based methods; CSMs extend coverage to nearly the whole proteome; excellent APIs |
| **Weaknesses** | Ligand modelling errors are common; structures are static snapshots (no conformational dynamics); membrane proteins and IDPs under-represented; **CSMs must never be conflated with experimental structures** |
| **Integration difficulty** | **Medium.** Metadata ingestion is straightforward; structural files belong in object storage, not the RDBMS |
| **Rationale** | Ingest metadata + ligand chemistry now; defer heavy structural work to the structure-based phase. Enforce an `is_experimental` flag at schema level. |

---

### 3.8 DrugCentral — **Priority: HIGH**

| Field | Detail |
|---|---|
| **Official website** | https://drugcentral.org/ |
| **Scientific purpose** | Open drug compendium: approved drugs, regulatory status, mechanism of action, indications, pharmacology, adverse events. |
| **Data categories** | Active ingredients; products; MoA & bioactivity; indications/contraindications; pharmacologic class; FAERS-derived adverse events; regulatory approvals; veterinary drugs; identifiers |
| **Records** | ~4,995 active ingredients; 152,476 pharmaceutical products **[S]** |
| **File formats** | PostgreSQL dump; TSV; web UI; REST API |
| **Licensing** | **CC BY-SA 4.0** **[S]** |
| **Commercial restrictions** | Commercial use permitted with attribution; **ShareAlike applies to adapted material** — see §5 |
| **Update frequency** | Roughly annual — **"DrugCentral 2023" appears to be the current release**, suggesting the cadence has slowed. Confirm before depending on it for regulatory currency **[S]** |
| **Data quality** | High; academically curated (UNM); strong regulatory grounding |
| **Strengths** | **Best open substitute for DrugBank without DrugBank's commercial licensing barrier**; clean approved-drug set for benchmarking; MoA annotations; direct PostgreSQL load |
| **Weaknesses** | Approved drugs only — no preclinical space; possible update lag; ShareAlike; smaller than commercial equivalents |
| **Integration difficulty** | **Low.** PostgreSQL dump, modest size |
| **Rationale** | The approved-drug reference set: essential for validation ("does DrugSim correctly predict known drugs?") and for the drug-likeness module. Adopt **in place of DrugBank**. |

---

### 3.9 Open Targets Platform — **Priority: HIGH** *(recommended addition, not in original brief)*

| Field | Detail |
|---|---|
| **Official website** | https://platform.opentargets.org/ |
| **Scientific purpose** | Systematic target–disease association evidence integration for drug target identification and prioritisation. |
| **Data categories** | Target–disease associations w/ evidence scores; genetic associations; known drugs & clinical precedence; tractability & safety; expression; pathways; disease ontology (EFO/MONDO) |
| **Records** | Millions of evidence-backed associations across ~20K targets and ~20K diseases **[U]** |
| **File formats** | Parquet (bulk), GraphQL API, Google BigQuery, FTP |
| **Licensing** | **CC0 1.0** — and notably, all contributing sources (including those marked "commercial use for Open Targets") have agreed to unrestricted downstream use **[S]** |
| **Commercial restrictions** | **None.** Explicitly designed for unrestricted commercial reuse |
| **Update frequency** | ~Quarterly |
| **Data quality** | High; systematic evidence scoring; transparent provenance and methodology |
| **Strengths** | **CC0 on integrated, pre-harmonised data — extraordinarily valuable given §5**; Parquet-native (ideal for the data lake); GraphQL API; already resolves the target↔disease↔drug integration problem DrugSim would otherwise solve itself |
| **Weaknesses** | Target-centric, not compound-centric — complements rather than replaces ChEMBL; association scores are heuristics, not ground truth; large bulk downloads |
| **Integration difficulty** | **Low–Medium.** Parquet drops straight into the lake |
| **Rationale** | **Strongly recommended addition.** It supplies most of Step 6's biological knowledge layer (proteins, genes, diseases, pathways, targets) pre-integrated, under CC0. It is the single highest leverage-to-effort source in this survey and materially de-risks the ShareAlike exposure by giving an unencumbered backbone. |

---

## 4. Tier 2 & Tier 3 Sources

Compact profiles. Same fields, condensed.

### 4.1 openFDA (incl. FAERS) — **Priority: MEDIUM-HIGH**
- **Site:** https://open.fda.gov/
- **Purpose:** FDA regulatory & post-market safety data via public API — the live pharmacovigilance signal.
- **Categories:** FAERS adverse events (MedDRA-coded); drug labels (SPL); recalls & enforcement; NDC directory; device/food endpoints.
- **Records:** Millions of reports; from 2014Q1 **[V]**. Exact count unverified.
- **Formats:** JSON REST API; bulk JSON downloads.
- **License:** **Public Domain / CC0** **[V]** · **Commercial:** None.
- **Updates:** **Quarterly, ~3-month lag** **[V]**.
- **Quality:** Spontaneous reporting — **strongly confounded**. No denominator, reporting bias, duplicates, no causality assessment.
- **Strengths:** Real human safety outcomes; CC0; live and maintained; the correct SIDER replacement.
- **Weaknesses:** **Cannot be used as toxicity ground truth without disproportionality analysis (PRR/ROR/BCPNN).** Naive counting produces confidently wrong safety signals — a genuine scientific hazard for a product making safety claims.
- **Integration:** **Medium** (API easy; correct statistical treatment is the real cost).
- **Rationale:** Adopt as the post-market safety layer, replacing SIDER. Ingest as *evidence*, never as labels, until a proper disproportionality pipeline exists.

### 4.2 DailyMed — **Priority: MEDIUM**
- **Site:** https://dailymed.nlm.nih.gov/
- **Purpose:** NLM's authoritative repository of FDA-approved Structured Product Labels.
- **Categories:** Full prescribing information; indications; dosage; warnings/boxed warnings; contraindications; pharmacokinetics narrative; NDC codes.
- **Records:** ~150K+ SPLs **[U — primary source unreachable]**.
- **Formats:** SPL XML (HL7), REST API, bulk download.
- **License:** **US Government / public domain** · **Commercial:** None.
- **Updates:** Daily.
- **Quality:** Authoritative — this is the legal label text.
- **Strengths:** Ground-truth regulatory text; PK parameters in narrative form; excellent for the AI Assistant / report-generation modules (RAG corpus); free of licensing risk.
- **Weaknesses:** **Unstructured narrative** — PK values are prose, requiring NLP extraction with attendant error; verbose XML; one drug → many SPLs (deduplication needed).
- **Integration:** **Medium–High** (XML parsing plus NLP extraction).
- **Rationale:** Defer structured PK extraction to a later phase. Ingest now as a document corpus for the future AI Scientific Assistant — it is the highest-authority text available and CC0-equivalent.

### 4.3 ClinTox — **Priority: MEDIUM** (consume via TDC)
- **Purpose:** Benchmark pairing FDA-approved drugs against compounds that failed clinical trials for toxicity.
- **Records:** **1,484 compounds** **[V]** · **License:** CC BY 4.0 via TDC **[V]** · **Commercial:** None.
- **Quality:** Widely used benchmark; **known weaknesses** — severe class imbalance, small size, and label semantics ("failed for toxicity") that are noisier than they appear.
- **Rationale:** Include for benchmark comparability, **not** as a serious clinical-toxicity predictor. Do not let a strong ClinTox number become a marketing claim; the benchmark does not support it. Access via TDC rather than ingesting separately.

### 4.4 SIDER — **Priority: LOW** ⚠️ *(demoted from the brief's implied priority)*
- **Site:** http://sideeffects.embl.de/
- **Records:** 1,430 drugs; 5,868 side effects; 139,756 pairs **[V]**.
- **License:** **CC BY-SA 4.0** **[V]** · **Commercial:** permitted, ShareAlike applies.
- **Updates:** **None. Frozen at v4.1, 21 Oct 2015, MedDRA 16.1. Maintainers state funding ended and data is outdated; EBI successor planned to begin 2026** **[V]**.
- **Weaknesses:** **11 years stale.** Misses every drug approved since 2015 and every label change since. MedDRA 16.1 is long superseded, creating ontology-mapping debt.
- **Rationale:** **Do not build the side-effect module on SIDER.** Use openFDA FAERS as the primary source. Optionally ingest SIDER as a static historical reference clearly versioned as 2015 data. Track the EBI successor.

### 4.5 Additional Recommended Sources

| Dataset | License | Commercial | Value to DrugSim | Priority |
|---|---|---|---|---|
| **PharmGKB** — pharmacogenomics, CYP variant–drug response | CC BY-SA 4.0 **[S]** | OK, ShareAlike | Genetic basis of metabolism variability; strengthens the Metabolism module beyond population averages | MEDIUM |
| **ChEBI** — chemical entity ontology | CC BY 4.0 | Clean | Ontological backbone for drug classes & chemical roles (Step 6) | MEDIUM |
| **DSSTox / CompTox Dashboard** — chemical identity for tox | Public domain | Clean | Authoritative chemical identity resolution for Tox21/ToxCast; solves the tox-side identity problem | MEDIUM-HIGH |
| **Reactome** — curated pathways | CC0 | Clean | Pathway layer for Step 6/9 knowledge graph; CC0 | MEDIUM |
| **Gene Ontology** | CC BY 4.0 | Clean | Standard functional vocabulary; biological process nodes in the KG | MEDIUM |
| **ClinicalTrials.gov** | Public domain | Clean | Clinical development context; attrition/failure signal | MEDIUM |
| **AlphaFold DB** | CC BY 4.0 | Clean | Structural coverage where PDB is absent (already surfaced via RCSB CSMs) | MEDIUM |
| **ZINC22 / Enamine REAL** | Varies — **verify** | ⚠️ verify | Purchasable chemical space for the Drug Optimization module | LOW (Phase 4+) |
| **LINCS L1000** | CC BY 4.0 **[U]** | Likely clean | Transcriptomic signatures → MoA inference & toxicity mechanism | LOW |
| **Broad Drug Repurposing Hub** | CC BY 4.0 **[U]** | Likely clean | Clean annotated approved-drug set | LOW |
| **PDBbind** | ⚠️ **Academic restrictions** | ⚠️ **Restricted** | Structure–affinity pairs — **but licensing conflicts with commercial use; verify before any use** | LOW / blocked |
| **DrugBank** | Non-commercial free; **commercial requires paid license** **[S]** | ⚠️ **Blocked** | Excellent data, but commercially gated | **EXCLUDE** (use DrugCentral) |

---

## 5. Licensing & Commercial Strategy — *the critical section*

DrugSim is a **startup**, i.e. a commercial entity. Dataset licensing is therefore a product-defining constraint, not paperwork. This section states the exposure plainly.

### 5.1 License classification of the recommended set

**Green — unrestricted (CC0 / public domain):**
PDB · Open Targets · Tox21/ToxCast · openFDA · DailyMed · ClinicalTrials.gov · Reactome · DSSTox
→ *No constraints. Build freely.*

**Amber — attribution only (CC BY):**
UniProt · TDC (majority) · BindingDB-curated portion · ChEBI · Gene Ontology · AlphaFold DB
→ *Attribution required. No copyleft. Commercially safe. Maintain an attributions manifest.*

**Red — ShareAlike copyleft (CC BY-SA):**
**ChEMBL (3.0)** · **DrugCentral (4.0)** · **SIDER (4.0)** · **PharmGKB (4.0)** · **BindingDB ChEMBL-derived portion (3.0)**
→ *Commercial use permitted, but adapted material must be redistributed under the same license. This is the exposure.*

**Black — commercially prohibited:**
**FreeSolv (CC BY-NC-SA 4.0, inside TDC)** · **DrugBank** (without paid license) · **PDBbind** (verify)
→ *Must be excluded from commercial paths or separately licensed.*

### 5.2 The unresolved question: does ShareAlike reach model outputs?

The question that decides DrugSim's data strategy: **if a model is trained on CC BY-SA data, do the model weights and its predictions constitute "Adapted Material"?**

Honest answer: **this is genuinely unsettled** and I will not pretend otherwise. The competing positions:

- **Argument that SA does not reach outputs:** CC BY-SA governs copyright in the licensed material. Facts are not copyrightable. Model weights are a statistical summary, not a reproduction or adaptation of the database. A prediction for a novel molecule contains no expressive content from ChEMBL.
- **Argument that it might:** CC 4.0 explicitly covers *sui generis database rights* (relevant in the EU/UK). Systematic extraction of a substantial portion to build a derived product can implicate database rights independently of copyright. Weights trained on a substantial extraction sit closer to the line than a single query result.
- **Version asymmetry that matters:** **CC BY-SA 3.0 (ChEMBL) predates CC 4.0's explicit database-rights handling.** ChEMBL — the anchor source — is on the older, less clear license. This cuts both ways and is precisely why it needs counsel rather than a confident engineering opinion.
- **Industry practice:** many commercial drug-discovery companies use ChEMBL. Practice is not law, but the absence of enforcement action over ~15 years is meaningful context.

**Recommendation: obtain a written legal opinion before Phase 3 model training.** Not before Phase 1 — the architecture below keeps the option open either way, so this need not block progress. But it must be resolved before the first commercially deployed model.

### 5.3 Architectural mitigation — design for the answer you don't have yet

The prudent move is an architecture that stays correct under *either* legal outcome. Three requirements, which become hard constraints on Steps 2, 3 and 5:

1. **Per-record license provenance, not per-dataset.** Every compound, activity, and annotation row carries `source_id`, `source_version`, and `source_license`. BindingDB alone forces this — it is split-licensed internally **[V]**. This is a schema-level requirement in Step 3, and retrofitting it later is extremely painful.

2. **License-tiered data zones with enforced lineage.** Physically segregate Green/Amber from Red in the data lake. Every model records which zone(s) its training data came from. This makes "can we ship this model commercially?" a **query**, not an archaeology project.

3. **A Green/Amber-only fallback training path.** For each headline model, know whether a version trained exclusively on unencumbered data is viable, and what accuracy it costs. Given that TDC (CC BY 4.0), Tox21/ToxCast (public domain), and Open Targets (CC0) cover a large fraction of the ADMET use case, **this fallback is likely viable at modest accuracy cost.** Quantifying that cost early is cheap insurance and a genuinely strong position to hold at due diligence.

### 5.4 Immediate exclusions

- **FreeSolv** — exclude from all commercial training runs; TDC's uniform interface makes accidental inclusion easy, so gate it explicitly in code from day one.
- **DrugBank** — do not ingest. DrugCentral covers the need with a workable license.
- **PDBbind** — verify licensing before any use.

### 5.5 A scientific caveat that is also a commercial one

DrugSim's proposition is predicting behaviour "before laboratory synthesis or animal testing." The verified data says the honest achievable scope is narrower than that framing implies:

- Human oral bioavailability: **640 compounds** [V]
- Human half-life: **667 compounds** [V]
- DILI (hepatotoxicity): **475 compounds** [V]
- Clinical toxicity failure (ClinTox): **1,484 compounds**, imbalanced, noisy labels [V]

Models trained on a few hundred compounds have **narrow applicability domains** and degrade sharply outside them — which is exactly where novel designed molecules live. This is not a reason to stop; it is the reason the Step 5 schema's `confidence_score`, `quality_score`, and applicability-domain fields are the most important columns in the system, not decoration.

Concretely, this argues for two things I would flag now rather than at Step 5:
- **Applicability-domain estimation is a required output**, not an optional extra. Every prediction ships with a defensible statement of whether the query molecule is inside the training distribution.
- **Positioning should be "prioritisation and triage," not "replacement of preclinical testing."** The former is defensible, valuable, and sellable. The latter invites scientific criticism the data cannot withstand — and, for a product touching safety claims, potentially regulatory attention.

I would rather raise this at Step 1, where it shapes the schema, than after models are built around a claim they cannot support.

---

## 6. Recommended Phase 1 Ingestion Sequence

Ordered by dependency, not by dataset importance. Identity resolution must be solved before anything else, or every subsequent join is unreliable.

| Wave | Sources | Rationale | Est. effort |
|---|---|---|---|
| **W1 — Identity spine** | PubChem (selective), UniProt Swiss-Prot, ChEBI | Establish compound (InChIKey) and protein (accession) canonical identity first. Everything joins to this | 1–2 wks |
| **W2 — Bioactivity core** | ChEMBL 37 (full PostgreSQL), BindingDB (w/ dedup + per-record license tags) | The scientific core. Deduplication against ChEMBL is the main task | 2–3 wks |
| **W3 — ADMET training layer** | TDC (all 22 ADMET sets, FreeSolv gated out) | Fastest path to a working model; establishes benchmark baselines | 3–5 days |
| **W4 — Toxicology** | Tox21 / ToxCast invitrodb v4.3, DSSTox | Public domain; large negative-data volume for calibration | 2–3 wks |
| **W5 — Drug & biology context** | DrugCentral, Open Targets, Reactome, GO | Approved-drug validation set + biological knowledge layer | 1–2 wks |
| **W6 — Structure** | PDB metadata + Chemical Component Dictionary | Metadata only in Phase 1; defer structural workloads | 1 wk |
| **W7 — Safety & text** | openFDA FAERS, DailyMed (document corpus) | Post-market safety; RAG corpus for later assistant module | 1–2 wks |

**Deferred to later phases:** ZINC/Enamine (optimization module), LINCS, PDBbind (pending license), SIDER (superseded).

---

## 7. Open Questions Requiring Your Decision

These change what gets built and are yours to call, not mine:

1. **Commercial model.** Is DrugSim a commercial SaaS from day one, an academic/open platform, or open-core? This determines whether the ShareAlike analysis in §5 is a critical path item or largely moot. **It is the single biggest input to Steps 2 and 3.**

2. **Legal counsel access.** Is IP counsel available to render the §5.2 opinion before Phase 3? If not, I would default to the Green/Amber-only architecture, accepting some accuracy cost for clean provenance.

3. **Regulatory ambition.** Is there any intent to pursue regulatory-grade use (FDA submissions, ICH M7 for mutagenicity)? If yes, requirements escalate substantially — 21 CFR Part 11 audit trails, formal model validation, OECD QSAR Validation Principles — and these must enter the schema at Step 3, not later.

4. **Infrastructure budget.** Full ChEMBL + PubChem + invitrodb + PDB is a multi-terabyte footprint. Cloud, on-prem, or hybrid? This constrains the Step 10 technology recommendation.

5. **Domain expertise on the team.** Is there a toxicologist or DMPK scientist available for review? Tox21/ToxCast and FAERS both have failure modes that are invisible to a purely engineering-led team and produce confidently wrong results.

---

## 8. Deliverables from Step 1

- ✅ This survey document
- ⬜ `datasets/registry.yaml` — machine-readable source registry (name, version, URL, license, SPDX, checksum, cadence) — **proposed for Step 2**, to become the single source of truth for the ETL layer
- ⬜ `docs/legal/attribution-manifest.md` — attribution obligations per source
- ⬜ Re-verification of PubChem and DailyMed figures from primary sources on an unfiltered network

---

*End Step 1 — awaiting approval before proceeding to Step 2 (Data Architecture).*
