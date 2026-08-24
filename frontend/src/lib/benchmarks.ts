/**
 * Every number in this file is copied, not estimated, from a real evaluation
 * report already checked into the repository. Each field cites the exact
 * source file so a claim on the Benchmark page can always be traced back to
 * where it came from. See docs/benchmarks/dataset-registry.md for the full
 * citation trail and docs/benchmarks/README.md for how these reports were
 * produced.
 *
 * Nothing here is fabricated, rounded up, or estimated. Where a comparison
 * (GPT, Claude) has not actually been run, its value is `null` and the UI
 * must render "Not evaluated" -- never a placeholder number.
 */

export type TaskType = "classification";

export interface ConfusionMatrix {
  tn: number;
  fp: number;
  fn: number;
  tp: number;
}

export interface ClassificationMetrics {
  n: number;
  positiveFraction: number;
  rocAuc: number;
  averagePrecision: number;
  balancedAccuracy: number;
  f1: number;
  precision: number;
  recall: number;
  matthewsCorrcoef?: number;
  specificity?: number;
  confusionMatrix: ConfusionMatrix;
  confidenceInterval95?: { lower: number; upper: number; nBootstrap: number };
}

export interface BaselineComparison {
  name: string;
  description: string;
  rocAuc: number | null;
  balancedAccuracy: number;
  note?: string;
}

export interface ExternalValidation {
  datasetName: string;
  provenanceNote: string;
  n: number;
  positiveFraction: number;
  rocAuc: number;
  balancedAccuracy: number;
  matthewsCorrcoef: number;
  confusionMatrix: ConfusionMatrix;
  labelDefinitionCaveat: string;
  sourceFile: string;
}

export interface ApplicabilityDomainTier {
  tier: string;
  n: number;
  /** Not every endpoint's AD report computed a Tanimoto range per tier -- omit rather than guess. */
  tanimotoRange?: [number, number];
  /** Each field below is present only when the source report actually computed
   * that exact metric for this tier -- omitted, never guessed or converted from
   * a different metric. hERG's report computed ROC-AUC and balanced accuracy
   * per tier; CYP3A4's computed plain (non-balanced) accuracy per verdict --
   * these are genuinely different metrics, not two spellings of one number. */
  positiveFraction?: number;
  rocAuc?: number;
  balancedAccuracy?: number;
  accuracy?: number;
}

export interface AiComparisonResult {
  /** null means genuinely not evaluated -- the UI must render "Not evaluated", never 0 or a dash implying a score. */
  rocAuc: number | null;
  accuracy: number | null;
  f1: number | null;
  notEvaluatedReason: string;
}

export interface Benchmark {
  benchmarkId: string;
  endpointId: string;
  endpointName: string;
  taskType: TaskType;
  datasetVersion: string;
  datasetSource: string;
  license: string;
  finalCompoundCount: number;
  splitMethod: string;
  splitDescription: string;
  modelVersion: string;
  evaluationDate: string;
  sourceFile: string;
  scaffoldSplitTest: ClassificationMetrics;
  randomSplitProxy: ClassificationMetrics;
  rocAucGap: number;
  gapExplanation: string;
  baselines: BaselineComparison[];
  externalValidation: ExternalValidation | null;
  applicabilityDomainTiers: ApplicabilityDomainTier[] | null;
  calibration: {
    internalBrierScore: number;
    internalEce: number;
    nominalConfidence: number;
    internalEmpiricalCoverage: number;
    externalEmpiricalCoverage: number | null;
    externalN: number | null;
  };
  aiComparison: {
    gpt: AiComparisonResult;
    claude: AiComparisonResult;
  };
}

const NOT_EVALUATED_REASON =
  "No GPT or Claude evaluation has been run against this benchmark. DrugSim has no API access configured for either service, and running one requires the documented protocol in docs/benchmarks/ai-comparison-protocol.md to be followed and recorded, not an informal comparison.";

export const BENCHMARKS: Benchmark[] = [
  {
    benchmarkId: "herg_inhibition_v1_scaffold_split",
    endpointId: "herg_inhibition",
    endpointName: "hERG (KCNH2/Kv11.1) cardiac channel inhibition",
    taskType: "classification",
    datasetVersion: "v1",
    datasetSource: "ChEMBL REST API (direct), target CHEMBL240, IC50 activities",
    license: "CC BY-SA 3.0 (ChEMBL, EMBL-EBI)",
    finalCompoundCount: 9589,
    splitMethod: "scaffold",
    splitDescription:
      "Global scaffold-level split (split_group 9 held out, ADR-009) -- structurally related compounds cannot appear in both train and test.",
    modelVersion: "0.1.0",
    evaluationDate: "2026-08-09",
    sourceFile: "models/admet/herg_inhibition/evaluation_report.json",
    scaffoldSplitTest: {
      n: 800,
      positiveFraction: 0.6112,
      rocAuc: 0.7875,
      averagePrecision: 0.8446,
      balancedAccuracy: 0.6495,
      f1: 0.7918,
      precision: 0.7008,
      recall: 0.91,
      confusionMatrix: { tn: 121, fp: 190, fn: 44, tp: 445 },
    },
    randomSplitProxy: {
      n: 800,
      positiveFraction: 0.6637,
      rocAuc: 0.8488,
      averagePrecision: 0.9136,
      balancedAccuracy: 0.7418,
      f1: 0.8489,
      precision: 0.8124,
      recall: 0.8889,
      confusionMatrix: { tn: 160, fp: 109, fn: 59, tp: 472 },
    },
    rocAucGap: 0.0613,
    gapExplanation:
      "Global scaffold splitting prevents cross-dataset/near-neighbour leakage; the random-split proxy is optimistic because structurally near-identical compounds can appear in both its train and test sets. This gap is the leakage the scaffold split removes, not a change in the model between the two runs. Not a TDC-comparable leaderboard number -- no true external benchmark split exists for this ChEMBL-sourced dataset.",
    baselines: [
      {
        name: "Majority class",
        description: "Always predicts 'blocker' (the majority training label).",
        rocAuc: null,
        balancedAccuracy: 0.5,
        note: "ROC-AUC is undefined for a constant predictor.",
      },
      {
        name: "Random (stratified)",
        description: "Predictions drawn at the train-set positive rate, 20-repeat average.",
        rocAuc: 0.5,
        balancedAccuracy: 0.5017,
      },
      {
        name: "Simple descriptors only",
        description: "LogP, molecular weight, and TPSA only -- 3 features, no fingerprint.",
        rocAuc: 0.601,
        balancedAccuracy: 0.5688,
      },
      {
        name: "DrugSim (registered model)",
        description: "Full descriptor + Morgan fingerprint feature set, 2,066 features, tuned Random Forest.",
        rocAuc: 0.7875,
        balancedAccuracy: 0.6495,
      },
    ],
    externalValidation: {
      datasetName: "PubChem AID 588834 (NCATS qHTS hERG inhibition screen)",
      provenanceNote:
        "Distinct submitting lab, assay technology, and data pipeline from ChEMBL. Fetched directly from PubChem's own REST API, never used in training, feature selection, hyperparameter tuning, threshold selection, or calibration.",
      n: 3919,
      positiveFraction: 0.0898,
      rocAuc: 0.8696,
      balancedAccuracy: 0.7794,
      matthewsCorrcoef: 0.4922,
      confusionMatrix: { tn: 2490, fp: 1077, fn: 49, tp: 303 },
      labelDefinitionCaveat:
        "The external set's positive rate (~9%) is far lower than training (~66%). ROC-AUC (ranking quality) transfers well, but the model's fixed 0.5 decision threshold was fit under a ~66% prior and does not adapt -- this shows up as high recall but low precision, a prevalence-shift effect, not evidence of poor discrimination.",
      sourceFile: "models/admet/herg_inhibition/phase4/04_external_validation_report.json",
    },
    applicabilityDomainTiers: [
      { tier: "Highly similar (Tanimoto 0.7-1.0)", n: 405, tanimotoRange: [0.7, 1.0], positiveFraction: 0.642, rocAuc: 0.8074, balancedAccuracy: 0.6852 },
      { tier: "Moderately similar (0.4-0.7)", n: 760, tanimotoRange: [0.4, 0.7], positiveFraction: 0.425, rocAuc: 0.8188, balancedAccuracy: 0.7207 },
      { tier: "Chemically novel (0.2-0.4)", n: 2700, tanimotoRange: [0.2, 0.4], positiveFraction: 0.0989, rocAuc: 0.8507, balancedAccuracy: 0.771 },
      { tier: "Out of domain (< 0.2)", n: 891, tanimotoRange: [-0.01, 0.2], positiveFraction: 0.0101, rocAuc: 0.7273, balancedAccuracy: 0.7024 },
    ],
    calibration: {
      internalBrierScore: 0.1864,
      internalEce: 0.0597,
      nominalConfidence: 0.9,
      internalEmpiricalCoverage: 0.8988,
      externalEmpiricalCoverage: 0.9196,
      externalN: 3956,
    },
    aiComparison: {
      gpt: { rocAuc: null, accuracy: null, f1: null, notEvaluatedReason: NOT_EVALUATED_REASON },
      claude: { rocAuc: null, accuracy: null, f1: null, notEvaluatedReason: NOT_EVALUATED_REASON },
    },
  },
  {
    benchmarkId: "cyp3a4_inhibition_v1_scaffold_split",
    endpointId: "cyp3a4_inhibition",
    endpointName: "CYP3A4 metabolic inhibition",
    taskType: "classification",
    datasetVersion: "v1",
    datasetSource: "ChEMBL REST API (direct), target CHEMBL340, IC50 activities",
    license: "CC BY-SA 3.0 (ChEMBL, EMBL-EBI)",
    finalCompoundCount: 5344,
    splitMethod: "scaffold",
    splitDescription:
      "Global scaffold-level split (split_group 9 held out, ADR-009) -- structurally related compounds cannot appear in both train and test.",
    modelVersion: "0.1.0",
    evaluationDate: "2026-08-10",
    sourceFile: "models/admet/cyp3a4_inhibition/evaluation_report.json",
    scaffoldSplitTest: {
      n: 459,
      positiveFraction: 0.6667,
      rocAuc: 0.7995,
      averagePrecision: 0.8922,
      balancedAccuracy: 0.652,
      f1: 0.8185,
      precision: 0.7514,
      recall: 0.8987,
      matthewsCorrcoef: 0.3564,
      specificity: 0.4052,
      confusionMatrix: { tn: 62, fp: 91, fn: 31, tp: 275 },
      confidenceInterval95: { lower: 0.7593, upper: 0.8382, nBootstrap: 1000 },
    },
    randomSplitProxy: {
      n: 459,
      positiveFraction: 0.6688,
      rocAuc: 0.8391,
      averagePrecision: 0.9094,
      balancedAccuracy: 0.7291,
      f1: 0.847,
      precision: 0.8059,
      recall: 0.8925,
      matthewsCorrcoef: 0.4922,
      specificity: 0.5658,
      confusionMatrix: { tn: 86, fp: 66, fn: 33, tp: 274 },
    },
    rocAucGap: 0.0396,
    gapExplanation:
      "Global scaffold splitting prevents cross-dataset/near-neighbour leakage; the random-split proxy is optimistic for the same structural-overlap reason as the hERG ablation. Not a TDC-comparable leaderboard number -- a within-dataset random-vs-scaffold ablation, included because no true external benchmark split exists for this dataset.",
    baselines: [
      {
        name: "Majority class",
        description: "Always predicts the majority training label, evaluated on validation group 8 (never the held-out test group).",
        rocAuc: null,
        balancedAccuracy: 0.5,
        note: "ROC-AUC is undefined for a constant predictor.",
      },
      {
        name: "Descriptors only, logistic regression",
        description: "18 physicochemical descriptors only, no fingerprint, linear model.",
        rocAuc: 0.6148,
        balancedAccuracy: 0.5866,
      },
      {
        name: "Descriptors only, random forest",
        description: "18 physicochemical descriptors only, no fingerprint, simple RF (300 trees).",
        rocAuc: 0.7291,
        balancedAccuracy: 0.5976,
      },
      {
        name: "DrugSim (registered model)",
        description: "Full descriptor + Morgan fingerprint feature set, tuned Random Forest.",
        rocAuc: 0.7995,
        balancedAccuracy: 0.652,
      },
    ],
    externalValidation: {
      datasetName: "TDC CYP3A4_Veith (PubChem AID 1851 qHTS primary screen, Veith et al. 2009, Nat Biotechnol)",
      provenanceNote:
        "A large-scale PubChem qHTS screen, completely separate from the literature-curated ChEMBL IC50 records used for training. Retrieved via a direct fetch of TDC's underlying Harvard Dataverse file. 23 of 12,175 standardised compounds (0.19%) overlapped with the ChEMBL training set and were excluded -- metrics below are computed only on the genuinely disjoint 12,152 compounds.",
      n: 12152,
      positiveFraction: 0.4184,
      rocAuc: 0.7758,
      balancedAccuracy: 0.7022,
      matthewsCorrcoef: 0.4016,
      confusionMatrix: { tn: 4325, fp: 2742, fn: 1056, tp: 4029 },
      labelDefinitionCaveat:
        "TDC's label is PubChem AID 1851's own single-concentration qHTS active/inactive call -- a different operationalisation of 'CYP3A4 inhibition' than this model's aggregated ChEMBL literature IC50 <= 10 uM definition. Some disagreement is expected from label-definition differences alone, not only from model error.",
      sourceFile: "models/admet/cyp3a4_inhibition/external_validation_report.json",
    },
    applicabilityDomainTiers: [
      { tier: "In domain (two-signal verdict; the scaffold-based signal is excluded here by construction -- see source report)", n: 262, accuracy: 0.8282 },
      { tier: "Borderline", n: 93, accuracy: 0.6989 },
      { tier: "Out of domain", n: 104, accuracy: 0.5288 },
    ],
    calibration: {
      internalBrierScore: 0.168,
      internalEce: 0.0493,
      nominalConfidence: 0.9,
      internalEmpiricalCoverage: 0.8976,
      externalEmpiricalCoverage: null,
      externalN: null,
    },
    aiComparison: {
      gpt: { rocAuc: null, accuracy: null, f1: null, notEvaluatedReason: NOT_EVALUATED_REASON },
      claude: { rocAuc: null, accuracy: null, f1: null, notEvaluatedReason: NOT_EVALUATED_REASON },
    },
  },
];

/**
 * Aggregate scale of the underlying ChEMBL database DrugSim's training data
 * was drawn from -- NOT the size of either endpoint's own training set. See
 * datasets/registry.yaml's chembl entry for the source of every figure here.
 * Deliberately kept separate from Benchmark.finalCompoundCount so no
 * component can accidentally present "trained on 2.9M compounds."
 */
export const OVERALL_DATABASE_SCALE = {
  source: "ChEMBL release 37",
  sourceFile: "datasets/registry.yaml",
  distinctCompounds: 2_921_148,
  bioactivityMeasurements: 24_527_044,
  assays: 1_970_438,
  targets: 18_552,
};

export interface ExampleCasePrediction {
  compoundName: string;
  smiles: string;
  endpoint: "herg_inhibition";
  publicGroundTruth: "blocker" | "non_blocker";
  groundTruthSource: string;
  drugsimLabel: "blocker" | "non_blocker";
  drugsimProbability: number;
  conformalSet: string[];
  conformalSingleton: boolean;
  applicabilityDomainVerdict: string;
  maxTanimotoToTraining: number;
  correct: boolean;
  evaluatedAt: string;
}

/**
 * Real, live predictions against the production API -- see this file's own
 * git history / the benchmark implementation report for the exact request
 * and response. Re-running /predict on these SMILES may return a different
 * number if the model is ever retrained; `evaluatedAt` is the date these
 * specific values were captured, not a claim that they are permanent.
 * Ground truth is well-documented public pharmacology, cited per row --
 * never DrugSim's own private training or test data, and never a
 * confidential/customer structure.
 */
export const EXAMPLE_CASE_PREDICTIONS: ExampleCasePrediction[] = [
  {
    compoundName: "Aspirin",
    smiles: "CC(=O)Oc1ccccc1C(=O)O",
    endpoint: "herg_inhibition",
    publicGroundTruth: "non_blocker",
    groundTruthSource: "No hERG liability reported in the clinical/pharmacovigilance literature; not associated with QT prolongation.",
    drugsimLabel: "non_blocker",
    drugsimProbability: 0.3067,
    conformalSet: ["non_blocker"],
    conformalSingleton: true,
    applicabilityDomainVerdict: "out_of_domain",
    maxTanimotoToTraining: 0.3208,
    correct: true,
    evaluatedAt: "2026-08-24",
  },
  {
    compoundName: "Terfenadine",
    smiles: "CC(C)(C)c1ccc(cc1)C(O)CCCN1CCC(CC1)C(O)(c1ccccc1)c1ccccc1",
    endpoint: "herg_inhibition",
    publicGroundTruth: "blocker",
    groundTruthSource: "Withdrawn from the US market in 1998 specifically for hERG-channel-mediated QT prolongation and torsades de pointes (FDA action; Woosley et al. 1993, JAMA).",
    drugsimLabel: "blocker",
    drugsimProbability: 0.92,
    conformalSet: ["blocker"],
    conformalSingleton: true,
    applicabilityDomainVerdict: "in_domain",
    maxTanimotoToTraining: 0.8913,
    correct: true,
    evaluatedAt: "2026-08-24",
  },
  {
    compoundName: "Dofetilide",
    smiles: "CS(=O)(=O)Nc1ccc(cc1)CCN(C)CCOc1ccc(NS(C)(=O)=O)cc1",
    endpoint: "herg_inhibition",
    publicGroundTruth: "blocker",
    groundTruthSource: "FDA-approved Class III antiarrhythmic whose approved mechanism of action is hERG (IKr) channel blockade.",
    drugsimLabel: "blocker",
    drugsimProbability: 0.515,
    conformalSet: ["non_blocker", "blocker"],
    conformalSingleton: false,
    applicabilityDomainVerdict: "out_of_domain",
    maxTanimotoToTraining: 0.4308,
    correct: true,
    evaluatedAt: "2026-08-24",
  },
  {
    compoundName: "Paracetamol",
    smiles: "CC(=O)Nc1ccc(O)cc1",
    endpoint: "herg_inhibition",
    publicGroundTruth: "non_blocker",
    groundTruthSource: "No hERG liability reported in the clinical/pharmacovigilance literature; not associated with QT prolongation.",
    drugsimLabel: "non_blocker",
    drugsimProbability: 0.16,
    conformalSet: ["non_blocker"],
    conformalSingleton: true,
    applicabilityDomainVerdict: "out_of_domain",
    maxTanimotoToTraining: 0.4211,
    correct: true,
    evaluatedAt: "2026-08-24",
  },
];
