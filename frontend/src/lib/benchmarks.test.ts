import { describe, expect, it } from "vitest";
import hergEvaluationReport from "../../../models/admet/herg_inhibition/evaluation_report.json";
import hergDatasetReport from "../../../models/admet/herg_inhibition/phase4/02_validate_endpoint_report.json";
import hergExternalValidationReport from "../../../models/admet/herg_inhibition/phase4/04_external_validation_report.json";
import cypEvaluationReport from "../../../models/admet/cyp3a4_inhibition/evaluation_report.json";
import cypExternalValidationReport from "../../../models/admet/cyp3a4_inhibition/external_validation_report.json";
import registryYaml from "../../../datasets/registry.yaml?raw";
import { BENCHMARKS, EXAMPLE_CASE_PREDICTIONS, OVERALL_DATABASE_SCALE } from "./benchmarks";

/**
 * These tests read the ACTUAL evaluation report JSON files this project's
 * model-development scripts produced, and assert the frontend benchmark
 * registry matches them exactly. This is the test that would catch a
 * fabricated, rounded, or stale number -- not just that the module
 * compiles, but that every figure on the page traces back to the real
 * artifact it claims to.
 */

describe("benchmark registry matches the real evaluation reports on disk", () => {
  it("hERG scaffold-split metrics match models/admet/herg_inhibition/evaluation_report.json exactly", () => {
    const report = hergEvaluationReport as unknown as {
      global_split: { n_test: number; roc_auc: number; balanced_accuracy: number; f1: number; precision: number; recall: number; confusion_matrix: { tn: number; fp: number; fn: number; tp: number } };
      roc_auc_gap: number;
    };
    const herg = BENCHMARKS.find((b) => b.endpointId === "herg_inhibition");
    expect(herg).toBeDefined();
    expect(herg!.scaffoldSplitTest.n).toBe(report.global_split.n_test);
    expect(herg!.scaffoldSplitTest.rocAuc).toBe(report.global_split.roc_auc);
    expect(herg!.scaffoldSplitTest.balancedAccuracy).toBe(report.global_split.balanced_accuracy);
    expect(herg!.scaffoldSplitTest.f1).toBe(report.global_split.f1);
    expect(herg!.scaffoldSplitTest.confusionMatrix).toEqual(report.global_split.confusion_matrix);
    expect(herg!.rocAucGap).toBe(report.roc_auc_gap);
  });

  it("hERG dataset size matches models/admet/herg_inhibition/phase4/02_validate_endpoint_report.json exactly", () => {
    const report = hergDatasetReport as unknown as {
      dataset_version: { final_compound_count: number; dataset_version: string };
    };
    const herg = BENCHMARKS.find((b) => b.endpointId === "herg_inhibition");
    expect(herg!.finalCompoundCount).toBe(report.dataset_version.final_compound_count);
    expect(herg!.datasetVersion).toBe(report.dataset_version.dataset_version);
  });

  it("hERG external validation matches models/admet/herg_inhibition/phase4/04_external_validation_report.json exactly", () => {
    const report = hergExternalValidationReport as unknown as {
      performance: { excluding_exact_training_overlap: { n: number; roc_auc: number; balanced_accuracy: number; confusion_matrix: { tn: number; fp: number; fn: number; tp: number } } };
    };
    const herg = BENCHMARKS.find((b) => b.endpointId === "herg_inhibition");
    const external = herg!.externalValidation!;
    expect(external.n).toBe(report.performance.excluding_exact_training_overlap.n);
    expect(external.rocAuc).toBe(report.performance.excluding_exact_training_overlap.roc_auc);
    expect(external.confusionMatrix).toEqual(report.performance.excluding_exact_training_overlap.confusion_matrix);
  });

  it("CYP3A4 scaffold-split metrics match models/admet/cyp3a4_inhibition/evaluation_report.json exactly", () => {
    const report = cypEvaluationReport as unknown as {
      global_split: {
        n_test: number; roc_auc: number; balanced_accuracy: number; f1: number;
        matthews_corrcoef: number; specificity_recall_negative: number;
        confusion_matrix: { tn: number; fp: number; fn: number; tp: number };
        confidence_interval_95pct: { "roc_auc_ci_lower_2.5pct": number; "roc_auc_ci_upper_97.5pct": number };
      };
    };
    const cyp = BENCHMARKS.find((b) => b.endpointId === "cyp3a4_inhibition");
    expect(cyp).toBeDefined();
    expect(cyp!.scaffoldSplitTest.n).toBe(report.global_split.n_test);
    expect(cyp!.scaffoldSplitTest.rocAuc).toBe(report.global_split.roc_auc);
    expect(cyp!.scaffoldSplitTest.matthewsCorrcoef).toBe(report.global_split.matthews_corrcoef);
    expect(cyp!.scaffoldSplitTest.specificity).toBe(report.global_split.specificity_recall_negative);
    expect(cyp!.scaffoldSplitTest.confusionMatrix).toEqual(report.global_split.confusion_matrix);
    expect(cyp!.scaffoldSplitTest.confidenceInterval95!.lower).toBe(report.global_split.confidence_interval_95pct["roc_auc_ci_lower_2.5pct"]);
    expect(cyp!.scaffoldSplitTest.confidenceInterval95!.upper).toBe(report.global_split.confidence_interval_95pct["roc_auc_ci_upper_97.5pct"]);
  });

  it("CYP3A4 external validation matches models/admet/cyp3a4_inhibition/external_validation_report.json exactly", () => {
    const report = cypExternalValidationReport as unknown as {
      metrics_on_disjoint_external_set: { n: number; roc_auc: number; confusion_matrix: { tn: number; fp: number; fn: number; tp: number } };
    };
    const cyp = BENCHMARKS.find((b) => b.endpointId === "cyp3a4_inhibition");
    const external = cyp!.externalValidation!;
    expect(external.n).toBe(report.metrics_on_disjoint_external_set.n);
    expect(external.rocAuc).toBe(report.metrics_on_disjoint_external_set.roc_auc);
    expect(external.confusionMatrix).toEqual(report.metrics_on_disjoint_external_set.confusion_matrix);
  });

  it("overall database scale matches datasets/registry.yaml's chembl entry", () => {
    // Cheap, dependency-free check rather than pulling in a YAML parser for one test file:
    // the exact figures must appear verbatim in the registry text.
    expect(registryYaml).toContain(`distinct_compounds: ${OVERALL_DATABASE_SCALE.distinctCompounds}`);
    expect(registryYaml).toContain(`activities: ${OVERALL_DATABASE_SCALE.bioactivityMeasurements}`);
    expect(registryYaml).toContain(`assays: ${OVERALL_DATABASE_SCALE.assays}`);
    expect(registryYaml).toContain(`targets: ${OVERALL_DATABASE_SCALE.targets}`);
  });
});

describe("no fabricated AI comparison data", () => {
  it("GPT and Claude results are null on every benchmark -- no evaluation has been run", () => {
    for (const benchmark of BENCHMARKS) {
      expect(benchmark.aiComparison.gpt.rocAuc).toBeNull();
      expect(benchmark.aiComparison.gpt.accuracy).toBeNull();
      expect(benchmark.aiComparison.gpt.f1).toBeNull();
      expect(benchmark.aiComparison.claude.rocAuc).toBeNull();
      expect(benchmark.aiComparison.claude.accuracy).toBeNull();
      expect(benchmark.aiComparison.claude.f1).toBeNull();
    }
  });

  it("every 'not evaluated' entry states why, rather than a bare null with no explanation", () => {
    for (const benchmark of BENCHMARKS) {
      expect(benchmark.aiComparison.gpt.notEvaluatedReason.length).toBeGreaterThan(20);
      expect(benchmark.aiComparison.claude.notEvaluatedReason.length).toBeGreaterThan(20);
    }
  });
});

describe("reproducibility fields are present on every benchmark", () => {
  it.each(BENCHMARKS)("$benchmarkId has a dataset version, model version, evaluation date, and source file", (benchmark) => {
    expect(benchmark.datasetVersion).toBeTruthy();
    expect(benchmark.modelVersion).toBeTruthy();
    expect(benchmark.evaluationDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(benchmark.sourceFile).toMatch(/^models\//);
    expect(benchmark.splitMethod).toBeTruthy();
  });
});

describe("individual molecule explorer uses only public, non-confidential compounds", () => {
  const ALLOWED_PUBLIC_COMPOUNDS = new Set(["Aspirin", "Terfenadine", "Dofetilide", "Paracetamol"]);

  it("every example case is one of the app's existing public example compounds", () => {
    for (const c of EXAMPLE_CASE_PREDICTIONS) {
      expect(ALLOWED_PUBLIC_COMPOUNDS.has(c.compoundName)).toBe(true);
    }
  });

  it("every example case cites a public ground-truth source, not DrugSim's private data", () => {
    for (const c of EXAMPLE_CASE_PREDICTIONS) {
      expect(c.groundTruthSource.length).toBeGreaterThan(15);
      expect(c.groundTruthSource.toLowerCase()).not.toContain("training set");
      expect(c.groundTruthSource.toLowerCase()).not.toContain("test set");
    }
  });
});
