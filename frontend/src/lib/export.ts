import type { PredictionResponse } from "../api/types";

const DISCLAIMER =
  "DrugSim provides computational estimates for research purposes. These predictions do not " +
  "establish clinical safety or efficacy and do not replace laboratory, preclinical, or " +
  "clinical testing.";

/**
 * Exports exactly what is already on screen -- nothing computed or
 * invented here, no field this file adds that the API response didn't
 * already return (Phase 10 yellow-improvement pass, section 12: "Exports
 * should contain appropriate prediction, uncertainty, applicability
 * domain, reliability, model version, timestamp, scientific disclaimer").
 */
export function predictionToExportObject(prediction: PredictionResponse, compoundName?: string) {
  return {
    compound_name: compoundName?.trim() || null,
    molecule: prediction.molecule,
    endpoint: prediction.estimate.endpoint,
    prediction: {
      predicted_label: prediction.estimate.predicted_label,
      predicted_probability: prediction.estimate.predicted_probability,
    },
    uncertainty: prediction.reliability.conformal,
    applicability_domain: prediction.reliability.applicability_domain,
    model: {
      model_id: prediction.provenance.model_id,
      model_version: prediction.provenance.model_version,
      model_checksum: prediction.provenance.model_checksum,
      dataset_version: prediction.provenance.dataset_version,
      training_set_size: prediction.provenance.training_set_size,
      final_report_status: prediction.provenance.final_report_status,
    },
    inference_timestamp: prediction.inference_timestamp,
    prediction_id: prediction.id,
    disclaimer: DISCLAIMER,
  };
}

export function predictionToJSON(prediction: PredictionResponse, compoundName?: string): string {
  return JSON.stringify(predictionToExportObject(prediction, compoundName), null, 2);
}

function csvCell(value: unknown): string {
  const s = value === null || value === undefined ? "" : String(value);
  return /[",\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export function predictionToCSV(prediction: PredictionResponse, compoundName?: string): string {
  const obj = predictionToExportObject(prediction, compoundName);
  const rows: [string, unknown][] = [
    ["compound_name", obj.compound_name],
    ["canonical_smiles", obj.molecule.canonical_smiles],
    ["molecular_formula", obj.molecule.molecular_formula],
    ["endpoint", obj.endpoint],
    ["predicted_label", obj.prediction.predicted_label],
    ["predicted_probability", obj.prediction.predicted_probability],
    ["conformal_predicted_set", obj.uncertainty.predicted_set.join("|")],
    ["conformal_p_value_blocker", obj.uncertainty.p_value_blocker],
    ["conformal_p_value_non_blocker", obj.uncertainty.p_value_non_blocker],
    ["conformal_nominal_confidence", obj.uncertainty.nominal_confidence],
    ["applicability_domain_verdict", obj.applicability_domain.verdict],
    ["applicability_domain_rationale", obj.applicability_domain.rationale],
    ["model_id", obj.model.model_id],
    ["model_version", obj.model.model_version],
    ["model_checksum", obj.model.model_checksum],
    ["dataset_version", obj.model.dataset_version],
    ["training_set_size", obj.model.training_set_size],
    ["final_report_status", obj.model.final_report_status],
    ["inference_timestamp", obj.inference_timestamp],
    ["prediction_id", obj.prediction_id],
    ["disclaimer", obj.disclaimer],
  ];
  const header = rows.map(([key]) => csvCell(key)).join(",");
  const values = rows.map(([, value]) => csvCell(value)).join(",");
  return `${header}\n${values}\n`;
}

export function downloadTextFile(filename: string, content: string, mimeType: string): void {
  const blob = new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
