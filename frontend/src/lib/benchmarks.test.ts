import { describe, expect, it } from "vitest";
import hergEvaluationReport from "../../../models/admet/herg_inhibition/evaluation_report.json";
import hergDatasetReport from "../../../models/admet/herg_inhibition/phase4/02_validate_endpoint_report.json";
import hergExternalValidationReport from "../../../models/admet/herg_inhibition/phase4/04_external_validation_report.json";
import cypEvaluationReport from "../../../models/admet/cyp3a4_inhibition/evaluation_report.json";
import cypExternalValidationReport from "../../../models/admet/cyp3a4_inhibition/external_validation_report.json";
import registryYaml from "../../../datasets/registry.yaml?raw";
import claudeSubsetReport from "../../../models/admet/herg_inhibition/claude_informal_subset_evaluation.json";
import cypClaudeFullEvaluation from "../../../models/admet/cyp3a4_inhibition/claude_full_test_set_evaluation.json";
import hergClaudeFullEvaluation from "../../../models/admet/herg_inhibition/claude_full_test_set_evaluation.json";
import { BENCHMARKS, CLAUDE_HERG_SUBSET_EVALUATION, EXAMPLE_CASE_PREDICTIONS, OVERALL_DATABASE_SCALE } from "./benchmarks";

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
  it("Claude is null except where a real evaluation exists, and a real one carries full reproducibility metadata", () => {
    for (const benchmark of BENCHMARKS) {
      const claude = benchmark.aiComparison.claude;
      const isEvaluated = claude.notEvaluatedReason === null;
      if (!isEvaluated) {
        expect(claude.rocAuc).toBeNull();
        expect(claude.accuracy).toBeNull();
        expect(claude.f1).toBeNull();
        expect(claude.notEvaluatedReason!.length).toBeGreaterThan(20);
      } else {
        // A real result must never silently look like a "Not evaluated" cell,
        // and must always carry enough to audit where it came from.
        expect(claude.rocAuc).not.toBeNull();
        expect(claude.accuracy).not.toBeNull();
        expect(claude.f1).not.toBeNull();
        expect(claude.n).toBeGreaterThan(0);
        expect(claude.modelIdentifier).toBeTruthy();
        expect(claude.evaluatedAt).toMatch(/^\d{4}-\d{2}-\d{2}$/);
        expect(claude.sourceFile).toMatch(/^models\//);
        expect(claude.methodologyNote?.length ?? 0).toBeGreaterThan(50);
      }
    }
  });

  it("CYP3A4's real Claude evaluation matches the source file exactly", () => {
    const cyp = BENCHMARKS.find((b) => b.endpointId === "cyp3a4_inhibition")!;
    const report = cypClaudeFullEvaluation as unknown as {
      n: number;
      roc_auc: number;
      balanced_accuracy: number;
      f1: number;
      model_identifier: string;
      evaluated_at: string;
      compounds: unknown[];
    };
    expect(cyp.aiComparison.claude.rocAuc).toBe(report.roc_auc);
    expect(cyp.aiComparison.claude.accuracy).toBe(report.balanced_accuracy);
    expect(cyp.aiComparison.claude.f1).toBe(report.f1);
    expect(cyp.aiComparison.claude.n).toBe(report.n);
    // Provenance (model id, run date) lives in the source JSON, not just
    // hardcoded in benchmarks.ts -- this catches the two drifting apart.
    expect(cyp.aiComparison.claude.modelIdentifier).toBe(report.model_identifier);
    expect(cyp.aiComparison.claude.evaluatedAt).toBe(report.evaluated_at);
    expect(report.compounds).toHaveLength(459);
  });

  it("hERG's real Claude evaluation matches the source file exactly", () => {
    const herg = BENCHMARKS.find((b) => b.endpointId === "herg_inhibition")!;
    const report = hergClaudeFullEvaluation as unknown as {
      n: number;
      roc_auc: number;
      balanced_accuracy: number;
      f1: number;
      model_identifier: string;
      evaluated_at: string;
      compounds: unknown[];
    };
    expect(herg.aiComparison.claude.rocAuc).toBe(report.roc_auc);
    expect(herg.aiComparison.claude.accuracy).toBe(report.balanced_accuracy);
    expect(herg.aiComparison.claude.f1).toBe(report.f1);
    expect(herg.aiComparison.claude.n).toBe(report.n);
    expect(herg.aiComparison.claude.modelIdentifier).toBe(report.model_identifier);
    expect(herg.aiComparison.claude.evaluatedAt).toBe(report.evaluated_at);
    expect(report.compounds).toHaveLength(800);
  });

  it("hERG's full-test-set Claude result is lower than DrugSim's own -- shown as-is, not softened", () => {
    const herg = BENCHMARKS.find((b) => b.endpointId === "herg_inhibition")!;
    expect(herg.aiComparison.claude.rocAuc).toBeLessThan(herg.scaffoldSplitTest.rocAuc);
    expect(herg.aiComparison.claude.accuracy).toBeLessThan(herg.scaffoldSplitTest.balancedAccuracy);
    expect(herg.aiComparison.claude.f1).toBeLessThan(herg.scaffoldSplitTest.f1);
  });

  it.each([
    ["hERG (800)", hergClaudeFullEvaluation, "blocker"],
    ["CYP3A4 (459)", cypClaudeFullEvaluation, "inhibitor"],
  ])(
    "%s: the raw per-compound outcomes independently recompute to the same confusion matrix -- catches drift between raw results and summary numbers",
    (_label, reportRaw, positiveLabel) => {
      const report = reportRaw as unknown as {
        n: number;
        tp: number;
        fp: number;
        fn: number;
        tn: number;
        compounds: { true_label: string; prediction: string; outcome: string }[];
      };
      expect(report.compounds).toHaveLength(report.n);
      const counts = { TP: 0, FP: 0, FN: 0, TN: 0 };
      for (const c of report.compounds) {
        const truePos = c.true_label === positiveLabel;
        const predPos = c.prediction === positiveLabel;
        const expectedOutcome = truePos === predPos ? (truePos ? "TP" : "TN") : truePos ? "FN" : "FP";
        expect(c.outcome).toBe(expectedOutcome);
        counts[c.outcome as keyof typeof counts]++;
      }
      expect(counts).toEqual({ TP: report.tp, FP: report.fp, FN: report.fn, TN: report.tn });
    },
  );
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

describe("Claude spot-check is a disclosed single run, never a fabricated or retrofitted estimate", () => {
  it("every spot-check names a real, versioned model identifier and a run date", () => {
    for (const c of EXAMPLE_CASE_PREDICTIONS) {
      expect(c.claudeSpotCheck.modelIdentifier).toBe("claude-sonnet-5");
      expect(c.claudeSpotCheck.runDate).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    }
  });

  it("a compound is either genuinely predicted or explicitly marked unavailable, never both and never neither", () => {
    for (const c of EXAMPLE_CASE_PREDICTIONS) {
      const hasPrediction = c.claudeSpotCheck.predictedLabel !== null;
      const hasReason = c.claudeSpotCheck.notAvailableReason !== null;
      expect(hasPrediction).toBe(!hasReason);
      if (hasPrediction) {
        expect(c.claudeSpotCheck.confidencePercent).toBeGreaterThan(0);
        expect(c.claudeSpotCheck.confidencePercent).toBeLessThanOrEqual(100);
      } else {
        expect(c.claudeSpotCheck.confidencePercent).toBeNull();
      }
    }
  });

  it("Dofetilide's spot-check is unavailable -- its answer was seen before a prediction could be made", () => {
    const dofetilide = EXAMPLE_CASE_PREDICTIONS.find((c) => c.compoundName === "Dofetilide")!;
    expect(dofetilide.claudeSpotCheck.predictedLabel).toBeNull();
    expect(dofetilide.claudeSpotCheck.notAvailableReason).toMatch(/seen before/i);
  });

  it("matches the exact values recorded during the session that produced them", () => {
    const byName = Object.fromEntries(EXAMPLE_CASE_PREDICTIONS.map((c) => [c.compoundName, c.claudeSpotCheck]));
    expect(byName["Aspirin"]).toMatchObject({ predictedLabel: "non_blocker", confidencePercent: 90 });
    expect(byName["Terfenadine"]).toMatchObject({ predictedLabel: "blocker", confidencePercent: 80 });
    expect(byName["Paracetamol"]).toMatchObject({ predictedLabel: "non_blocker", confidencePercent: 88 });
  });
});

describe("Claude's 30-compound subset evaluation matches the real per-compound source file exactly", () => {
  const report = claudeSubsetReport as unknown as {
    n: number;
    tp: number;
    fp: number;
    fn: number;
    tn: number;
    roc_auc: number;
    accuracy: number;
    balanced_accuracy: number;
    precision: number;
    recall: number;
    specificity: number;
    f1: number;
    seed: number;
    model_identifier: string;
    evaluated_at: string;
    compounds: { true_label: string; claude_prediction: string; outcome: string; probability: number }[];
  };

  it("displayed confusion matrix and metrics match the source report exactly", () => {
    expect(CLAUDE_HERG_SUBSET_EVALUATION.n).toBe(report.n);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.seed).toBe(report.seed);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.confusionMatrix).toEqual({
      tp: report.tp,
      fp: report.fp,
      fn: report.fn,
      tn: report.tn,
    });
    expect(CLAUDE_HERG_SUBSET_EVALUATION.rocAuc).toBe(report.roc_auc);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.accuracy).toBe(report.accuracy);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.balancedAccuracy).toBe(report.balanced_accuracy);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.precision).toBe(report.precision);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.recall).toBe(report.recall);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.specificity).toBe(report.specificity);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.f1).toBe(report.f1);
    // Provenance (model id, run date) lives in the source JSON, not just
    // hardcoded in benchmarks.ts -- this catches the two drifting apart.
    expect(CLAUDE_HERG_SUBSET_EVALUATION.modelIdentifier).toBe(report.model_identifier);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.runDate).toBe(report.evaluated_at);
  });

  it("self-reported confidence is coarse -- only 9 distinct values across 30 compounds, the fact behind the page's calibration caveat", () => {
    const distinctProbabilities = new Set(report.compounds.map((c) => c.probability));
    expect(distinctProbabilities.size).toBe(9);
  });

  it("every compound's probability score is directionally consistent with its binary verdict -- the follow-up scoring pass didn't contradict the original reasoning", () => {
    for (const c of report.compounds) {
      const predictedBlocker = c.claude_prediction === "blocker";
      expect(c.probability >= 50).toBe(predictedBlocker);
    }
  });

  it("the 30 raw per-compound outcomes independently recompute to the same confusion matrix -- catches drift between the raw results and the summary numbers", () => {
    expect(report.compounds).toHaveLength(30);
    const counts = { TP: 0, FP: 0, FN: 0, TN: 0 };
    for (const c of report.compounds) {
      const trueBlocker = c.true_label === "blocker";
      const predBlocker = c.claude_prediction === "blocker";
      const expectedOutcome = trueBlocker === predBlocker ? (trueBlocker ? "TP" : "TN") : trueBlocker ? "FN" : "FP";
      expect(c.outcome).toBe(expectedOutcome);
      counts[c.outcome as keyof typeof counts]++;
    }
    expect(counts).toEqual({ TP: report.tp, FP: report.fp, FN: report.fn, TN: report.tn });
  });

  it("is a real, disclosed, unflattering-if-that's-what-it-is result -- not silently rounded up to match DrugSim's own number", () => {
    const herg = BENCHMARKS.find((b) => b.endpointId === "herg_inhibition")!;
    // This is the actual finding: the 30-compound subset scored lower than
    // DrugSim's own model on the full 800. The test locks in that this stays
    // visible rather than quietly disappearing in a future edit.
    expect(CLAUDE_HERG_SUBSET_EVALUATION.balancedAccuracy).toBeLessThan(herg.scaffoldSplitTest.balancedAccuracy);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.f1).toBeLessThan(herg.scaffoldSplitTest.f1);
  });

  it("sample size is real and small -- 30, not fabricated as if it were the full 800", () => {
    expect(CLAUDE_HERG_SUBSET_EVALUATION.n).toBe(30);
    expect(CLAUDE_HERG_SUBSET_EVALUATION.n).toBeLessThan(800);
  });
});
