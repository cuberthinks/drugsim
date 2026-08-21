/**
 * Types mirroring src/drugsim_predict/schemas.py exactly.
 *
 * This file has no logic — it exists so the frontend cannot drift from the
 * Phase 5 contract silently. If a backend field changes, this file changes
 * with it; nothing here is invented or computed independently.
 */

export type StructureFormat = "smiles" | "molblock" | "inchi";

export interface StructureInput {
  format: StructureFormat;
  value: string;
}

export interface PredictRequest {
  structure: StructureInput;
  /** Phase 9: which registered endpoint to run. Omit for hERG (the default). */
  endpoint?: string;
}

export type Severity = "low" | "medium" | "high";

export interface WarningItem {
  code: string;
  severity: Severity;
  message: string;
  field: string;
}

export interface MoleculeInfo {
  canonical_smiles: string;
  isomeric_smiles: string;
  standardized_smiles: string;
  inchikey_full: string;
  molecular_formula: string;
}

// Phase 9: widened from a hERG-only "blocker" | "non_blocker" union to a
// plain string, since other endpoints use their own label vocabulary (e.g.
// CYP3A4's "inhibitor" / "non_inhibitor") -- mirrors the same widening on
// the backend's EstimateSchema/ConformalSchema. See src/lib/endpointCopy.ts
// for how these raw strings are mapped to display text per endpoint.
export type PredictedLabel = string;

export interface Estimate {
  endpoint: string;
  predicted_label: PredictedLabel;
  /** Legacy hERG-only field: populated only when endpoint === "herg_inhibition". */
  predicted_probability_blocker: number | null;
  /** Probability of the endpoint's positive-class label. Populated for every endpoint. */
  predicted_probability: number;
}

export interface ConformalResult {
  predicted_set: PredictedLabel[];
  p_value_blocker: number;
  p_value_non_blocker: number;
  nominal_confidence: number;
  is_singleton: boolean;
  /** Phase 10: names the uncertainty methodology, e.g. "split_conformal_prediction". */
  method: string;
}

export type ADVerdict = "in_domain" | "borderline" | "out_of_domain" | "undeterminable";

export interface ApplicabilityDomain {
  verdict: ADVerdict;
  max_tanimoto_to_training: number | null;
  knn_distance: number | null;
  knn_distance_threshold: number;
  scaffold_seen_in_training: boolean | null;
  rationale: string;
  /** Phase 10: names the applicability-domain methodology. */
  method: string;
}

export interface Reliability {
  conformal: ConformalResult;
  applicability_domain: ApplicabilityDomain;
}

export interface Provenance {
  model_id: string;
  model_version: string;
  model_checksum: string;
  dataset_version: string;
  feature_set_id: string;
  standardization_pipeline_version: string;
  descriptor_spec_version: string;
  rdkit_version: string;
  training_set_size: number;
  input_hash: string;
  final_report_status: string;
}

export interface PredictionResponse {
  id: string;
  request_id: string;
  molecule: MoleculeInfo;
  estimate: Estimate;
  reliability: Reliability;
  provenance: Provenance;
  warnings: WarningItem[];
  inference_timestamp: string;
  status: "complete";
}

export interface AtomContribution {
  atom_index: number;
  /** Positive pushes toward positive_class_label; negative pushes away from it. */
  contribution: number;
}

export interface DescriptorContribution {
  name: string;
  value: number;
  contribution: number;
}

export interface ExplainabilityResponse {
  molecule: MoleculeInfo;
  endpoint: string;
  positive_class_label: string;
  base_value: number;
  atom_contributions: AtomContribution[];
  descriptor_contributions: DescriptorContribution[];
  /** How much of the prediction is explained by chemistry NOT present in
   * this molecule -- see the backend schema's own field description for why
   * this can't be mapped onto any atom. */
  absent_substructure_contribution: number;
  method: string;
}

export interface ErrorDetail {
  field: string | null;
  code: string;
  message: string;
}

export interface ProblemDetail {
  type: string;
  title: string;
  status: number;
  detail: string;
  instance?: string | null;
  request_id?: string | null;
  errors?: ErrorDetail[] | null;
}

/** GET /endpoints item — Phase 9 discovery metadata, one per registered endpoint. */
export interface EndpointListItem {
  model_id: string;
  endpoint_name: string;
  category: string | null;
  final_report_status: string;
  dataset_version: string;
  training_set_size: number | null;
  /** Whether POST /predict will currently accept this endpoint. */
  servable: boolean;
}

export interface EndpointsResponse {
  endpoints: EndpointListItem[];
}

export interface ModelDetail {
  model_id: string;
  model_version: string;
  model_checksum: string;
  endpoint: string;
  dataset_version: string;
  algorithm: string;
  training_set_size: number;
  feature_set_id: string;
  standardization_pipeline_version: string;
  descriptor_spec_version: string;
  rdkit_version: string;
  final_report_status: string;
  global_split_test_roc_auc: number | null;
}
