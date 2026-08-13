import type { PredictionResponse } from "../api/types";

export function makePrediction(overrides: Partial<PredictionResponse> = {}): PredictionResponse {
  return {
    id: "pred_01test",
    request_id: "req_01test",
    molecule: {
      canonical_smiles: "CC(=O)Oc1ccccc1C(=O)O",
      isomeric_smiles: "CC(=O)Oc1ccccc1C(=O)O",
      standardized_smiles: "CC(=O)Oc1ccccc1C(=O)O",
      inchikey_full: "BSYNRYMUTXBXSQ-UHFFFAOYSA-N",
      molecular_formula: "C9H8O4",
    },
    estimate: {
      endpoint: "herg_inhibition",
      predicted_label: "non_blocker",
      predicted_probability_blocker: 0.12,
      predicted_probability: 0.12,
    },
    reliability: {
      conformal: {
        predicted_set: ["non_blocker"],
        p_value_blocker: 0.03,
        p_value_non_blocker: 0.62,
        nominal_confidence: 0.9,
        is_singleton: true,
        method: "split_conformal_prediction",
      },
      applicability_domain: {
        verdict: "in_domain",
        max_tanimoto_to_training: 0.82,
        knn_distance: 0.4,
        knn_distance_threshold: 0.6,
        scaffold_seen_in_training: true,
        rationale: "This structure closely resembles compounds seen during training.",
        method: "tanimoto_knn_distance_scaffold_membership",
      },
    },
    provenance: {
      model_id: "herg_inhibition",
      model_version: "0.1.0",
      model_checksum: "a".repeat(64),
      dataset_version: "2026.01",
      feature_set_id: "fp_ecfp4_2048",
      standardization_pipeline_version: "std-v1",
      descriptor_spec_version: "desc-v1",
      rdkit_version: "2025.3.3",
      training_set_size: 6792,
      input_hash: "3b139ddd2a92",
      final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
    },
    warnings: [],
    inference_timestamp: "2026-08-09T00:00:00Z",
    status: "complete",
    ...overrides,
  };
}
