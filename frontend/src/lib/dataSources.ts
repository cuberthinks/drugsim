/**
 * Every fact here is traceable to a real file in the DrugSim repository --
 * this is not marketing copy. See docs/references/data-sources-page-audit.md
 * for the full citation trail (exact file paths and line numbers) behind
 * every field below, and datasets/registry.yaml for the underlying source
 * registry this data is drawn from.
 *
 * Status meanings (verified against the actual training/validation code
 * and model registry files, not against what was merely catalogued for a
 * future data pipeline):
 *   "active"   — genuinely used to train or validate one of the two live
 *                models (herg_inhibition, cyp3a4_inhibition).
 *   "excluded" — evaluated and explicitly rejected, with a stated reason.
 *   "future"   — catalogued in DrugSim's internal source registry, or
 *                identified as a candidate, but not used in any live
 *                prediction today.
 */

export type SourceStatus = "active" | "excluded" | "future";

export interface DataSource {
  id: string;
  name: string;
  provider: string;
  purpose: string;
  status: SourceStatus;
  usedIn?: string;
  license?: string;
  officialUrl?: string;
  lastVerified?: string;
  note?: string;
}

export const ACTIVE_SOURCES: DataSource[] = [
  {
    id: "chembl",
    name: "ChEMBL",
    provider: "EMBL-EBI",
    purpose: "Bioactivity measurements (IC50 values) used to train both live models.",
    status: "active",
    usedIn:
      "hERG inhibition training (target CHEMBL240) and CYP3A4 inhibition training (target CHEMBL340), fetched directly via ChEMBL's public REST API.",
    license: "CC BY-SA 3.0",
    officialUrl: "https://www.ebi.ac.uk/chembl/",
    lastVerified: "2026-08-05",
  },
  {
    id: "pubchem",
    name: "PubChem",
    provider: "National Library of Medicine (NCBI/NIH)",
    purpose: "Source of the independent screening data used to externally validate the hERG model.",
    status: "active",
    usedIn:
      "hERG external validation, fetched directly (PubChem AID 588834, an NCATS qHTS hERG screen, 4,030 compounds after quality filtering — a different lab and assay technology than the ChEMBL training data). Also the original source, via TDC, of the CYP3A4 model's external validation set (see Therapeutics Data Commons below).",
    license: "US Public Domain (PubChem's own content; individual depositor records may carry other terms)",
    officialUrl: "https://pubchem.ncbi.nlm.nih.gov/",
    lastVerified: "2026-08-05",
    note: "Verification status: secondary — DrugSim's internal source registry flags PubChem's own summary statistics as not independently re-confirmed on an unfiltered network; this does not affect the AID 588834 validation result itself, which was fetched and checked directly.",
  },
  {
    id: "tdc",
    name: "Therapeutics Data Commons (TDC)",
    provider: "Harvard University (Zitnik Lab)",
    purpose: "Source of the CYP3A4 model's external validation set.",
    status: "active",
    usedIn:
      "CYP3A4 external validation only, never training. The dataset used (CYP3A4_Veith) is TDC's republication of a PubChem qHTS screen (AID 1851, Veith et al. 2009), independent of the ChEMBL data used for training.",
    license: "Mixed, set per dataset (default CC BY 4.0). One TDC dataset — FreeSolv — is explicitly excluded from DrugSim; see Sources Not Used below.",
    officialUrl: "https://tdcommons.ai/",
    lastVerified: "2026-08-05",
  },
];

/**
 * Catalogued in DrugSim's internal source registry (datasets/registry.yaml)
 * with real license review already done, or identified as a candidate in
 * project planning docs -- but not used in any live prediction today.
 * Every entry here is exactly what the audit found: no fetch/ingestion code
 * for any of these exists anywhere in the repository.
 */
export const FUTURE_SOURCES: DataSource[] = [
  {
    id: "bindingdb",
    name: "BindingDB",
    provider: "UC San Diego",
    purpose: "Drug–protein binding affinity data.",
    status: "future",
    license: "Mixed: BindingDB's own curation is CC BY 3.0; the ChEMBL-derived portion is CC BY-SA 3.0.",
    officialUrl: "https://www.bindingdb.org/",
  },
  {
    id: "toxcast-tox21",
    name: "ToxCast / Tox21",
    provider: "U.S. EPA",
    purpose: "High-throughput toxicology screening data.",
    status: "future",
    license: "US Public Domain",
    officialUrl: "https://www.epa.gov/comptox-tools/toxicity-forecasting-toxcast",
  },
  {
    id: "uniprot",
    name: "UniProt",
    provider: "UniProt Consortium",
    purpose: "Protein identity resolution.",
    status: "future",
    license: "CC BY 4.0",
    officialUrl: "https://www.uniprot.org/",
  },
  {
    id: "pdb",
    name: "RCSB Protein Data Bank",
    provider: "RCSB",
    purpose: "Experimentally determined protein 3D structures.",
    status: "future",
    license: "CC0",
    officialUrl: "https://www.rcsb.org/",
  },
  {
    id: "drugcentral",
    name: "DrugCentral",
    provider: "University of New Mexico",
    purpose: "Approved-drug reference data.",
    status: "future",
    license: "CC BY-SA 4.0",
    officialUrl: "https://drugcentral.org/",
  },
  {
    id: "opentargets",
    name: "Open Targets",
    provider: "Open Targets Platform",
    purpose: "Drug–target–disease relationship data.",
    status: "future",
    license: "CC0",
    officialUrl: "https://platform.opentargets.org/",
  },
  {
    id: "openfda",
    name: "openFDA / FAERS",
    provider: "U.S. Food and Drug Administration",
    purpose: "Postmarket drug safety and adverse-event reports.",
    status: "future",
    license: "CC0 (US Public Domain)",
    officialUrl: "https://open.fda.gov/",
  },
  {
    id: "dailymed",
    name: "DailyMed",
    provider: "U.S. National Library of Medicine",
    purpose: "Drug labels and regulatory text.",
    status: "future",
    license: "US Public Domain",
    officialUrl: "https://dailymed.nlm.nih.gov/",
  },
];

/**
 * Identified as candidates in project planning documents, with no license
 * review or provider verification done yet -- deliberately listed with
 * less detail than FUTURE_SOURCES above, since less is actually verified
 * about them.
 */
export const DEFERRED_SOURCE_NAMES: { name: string; value: string }[] = [
  { name: "PharmGKB", value: "Pharmacogenomics and CYP enzyme variant data" },
  { name: "ChEBI", value: "Chemical ontology for drug classes" },
  { name: "DSSTox", value: "Chemical identity resolution for toxicology data" },
  { name: "Reactome", value: "Biological pathway data" },
  { name: "Gene Ontology", value: "Biological process vocabulary" },
  { name: "ClinicalTrials.gov", value: "Clinical development and attrition signal" },
  { name: "AlphaFold DB", value: "Predicted protein structures beyond experimental coverage" },
  { name: "LINCS / L1000", value: "Transcriptomic signatures for mechanism-of-action inference" },
  { name: "ZINC22", value: "Purchasable chemical space for compound optimisation" },
];

export const EXCLUDED_SOURCES: DataSource[] = [
  {
    id: "drugbank",
    name: "DrugBank",
    provider: "",
    purpose: "",
    status: "excluded",
    license: "Proprietary — free for academic non-commercial use only",
    note: "Commercial use requires a paid licence, which does not meet DrugSim's intended usage. DrugCentral is used for the same kind of approved-drug reference data instead.",
  },
  {
    id: "freesolv",
    name: "FreeSolv (Hydration Free Energy)",
    provider: "",
    purpose: "",
    status: "excluded",
    license: "CC BY-NC-SA 4.0",
    note: "Ships inside Therapeutics Data Commons behind the same interface as TDC's permissive datasets, which makes accidental inclusion easy. Its non-commercial licence is incompatible with DrugSim's intended use, so it is explicitly blocked in code, not left to documentation alone.",
  },
  {
    id: "pdbbind",
    name: "PDBbind",
    provider: "",
    purpose: "",
    status: "excluded",
    license: "Unverified",
    note: "Licensing terms have not been sufficiently verified to confirm they permit DrugSim's intended use. Excluded pending that verification, not because a specific restriction was confirmed.",
  },
  {
    id: "sider",
    name: "SIDER",
    provider: "",
    purpose: "",
    status: "excluded",
    license: "CC BY-SA 4.0",
    note: "Not excluded for licensing. SIDER is frozen at its 2015 release (v4.1) — its maintainers report funding ended, and it misses every drug approved since — so it is excluded for being out of date, not for any licence restriction.",
  },
];
