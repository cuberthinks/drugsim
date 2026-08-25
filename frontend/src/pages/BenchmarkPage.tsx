import { Link } from "react-router-dom";
import {
  BENCHMARKS,
  CLAUDE_HERG_SUBSET_EVALUATION,
  EXAMPLE_CASE_PREDICTIONS,
  OVERALL_DATABASE_SCALE,
  type AiComparisonResult,
  type ApplicabilityDomainTier,
  type Benchmark,
  type ClaudeSpotCheckResult,
} from "../lib/benchmarks";

function pct(x: number | null | undefined, digits = 1): string {
  if (x === null || x === undefined) return "—";
  return `${(x * 100).toFixed(digits)}%`;
}

function num3(x: number | null | undefined): string {
  if (x === null || x === undefined) return "—";
  return x.toFixed(3);
}

function NotEvaluated({ reason }: { reason: string }) {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-paper-alt px-2.5 py-0.5 font-mono text-[11px] font-medium tracking-wide text-ink-soft uppercase" title={reason}>
      Not evaluated
    </span>
  );
}

function AiMetricCell({ result, metric }: { result: AiComparisonResult; metric: "rocAuc" | "accuracy" | "f1" }) {
  const value = result[metric];
  if (value === null) {
    return <NotEvaluated reason={result.notEvaluatedReason ?? "Not evaluated."} />;
  }
  const title = [
    result.methodologyNote,
    result.n !== undefined ? `n = ${result.n}` : null,
    result.modelIdentifier ? `model: ${result.modelIdentifier}` : null,
    result.evaluatedAt ? `evaluated ${result.evaluatedAt}` : null,
    result.sourceFile ? `source: ${result.sourceFile}` : null,
  ]
    .filter(Boolean)
    .join(" — ");
  return (
    <span className="font-mono text-ink" title={title}>
      {pct(value)}
    </span>
  );
}

function ClaudeSpotCheckNote({ spotCheck }: { spotCheck: ClaudeSpotCheckResult }) {
  if (spotCheck.predictedLabel === null) {
    return (
      <span title={spotCheck.notAvailableReason ?? undefined}>
        Claude ({spotCheck.modelIdentifier}): no blind estimate available
      </span>
    );
  }
  return (
    <span
      title={`Single run, SMILES only (compound name withheld until after the prediction), ${spotCheck.runDate}. Not the repeated-run protocol in docs/benchmarks/ai-comparison-protocol.md -- an informal spot-check, not a validated result.`}
    >
      Claude ({spotCheck.modelIdentifier}, single-run spot-check): {spotCheck.predictedLabel.replace("_", "-")} (
      {spotCheck.confidencePercent}% self-reported)
    </span>
  );
}

function ConfusionMatrixGrid({ matrix, positiveLabel = "Blocker", negativeLabel = "Non-blocker" }: { matrix: { tn: number; fp: number; fn: number; tp: number }; positiveLabel?: string; negativeLabel?: string }) {
  const total = matrix.tn + matrix.fp + matrix.fn + matrix.tp;
  const cell = (label: string, value: number, tone: "good" | "bad") => (
    <div className={`rounded-md border p-3 text-center ${tone === "good" ? "border-signal/40 bg-signal-soft" : "border-concern/40 bg-concern-soft"}`}>
      <p className="font-mono text-lg font-semibold text-ink">{value}</p>
      <p className="mt-0.5 text-[11px] text-ink-soft">{label}</p>
      <p className="font-mono text-[10px] text-ink-soft">{pct(value / total)}</p>
    </div>
  );
  return (
    <div>
      <div className="grid grid-cols-2 gap-2">
        {cell(`True ${negativeLabel}`, matrix.tn, "good")}
        {cell(`False ${positiveLabel}`, matrix.fp, "bad")}
        {cell(`False ${negativeLabel}`, matrix.fn, "bad")}
        {cell(`True ${positiveLabel}`, matrix.tp, "good")}
      </div>
      <p className="mt-2 text-center font-mono text-[11px] text-ink-soft">n = {total}</p>
    </div>
  );
}

function BarRow({ label, value, max, highlight = false }: { label: string; value: number | null; max: number; highlight?: boolean }) {
  const widthPct = value === null ? 0 : Math.max(2, (value / max) * 100);
  return (
    <div className="flex items-center gap-3">
      <p className="w-48 shrink-0 text-xs text-ink-soft">{label}</p>
      <div className="h-4 flex-1 overflow-hidden rounded bg-paper-alt">
        {value !== null && (
          <div
            className={`h-full rounded ${highlight ? "bg-signal" : "bg-ink-soft/50"}`}
            style={{ width: `${widthPct}%` }}
          />
        )}
      </div>
      <p className="w-14 shrink-0 text-right font-mono text-xs text-ink">{value === null ? "n/a" : value.toFixed(3)}</p>
    </div>
  );
}

function ApplicabilityDomainTierList({ tiers }: { tiers: ApplicabilityDomainTier[] }) {
  return (
    <div className="flex flex-col gap-2">
      {tiers.map((tier) => (
        <div key={tier.tier} className="rounded-md border border-line p-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <p className="text-sm font-medium text-ink">{tier.tier}</p>
            <p className="font-mono text-xs text-ink-soft">n = {tier.n}</p>
          </div>
          <dl className="mt-1.5 grid grid-cols-2 gap-2 text-xs text-ink-soft sm:grid-cols-4">
            {tier.rocAuc !== undefined && (
              <div>
                <dt className="font-medium text-ink">ROC-AUC</dt>
                <dd className="font-mono">{num3(tier.rocAuc)}</dd>
              </div>
            )}
            {tier.balancedAccuracy !== undefined && (
              <div>
                <dt className="font-medium text-ink">Balanced acc.</dt>
                <dd className="font-mono">{pct(tier.balancedAccuracy)}</dd>
              </div>
            )}
            {tier.accuracy !== undefined && (
              <div>
                <dt className="font-medium text-ink">Accuracy</dt>
                <dd className="font-mono">{pct(tier.accuracy)}</dd>
              </div>
            )}
            {tier.positiveFraction !== undefined && (
              <div>
                <dt className="font-medium text-ink">Positive rate</dt>
                <dd className="font-mono">{pct(tier.positiveFraction)}</dd>
              </div>
            )}
          </dl>
        </div>
      ))}
    </div>
  );
}

function BenchmarkSection({ benchmark }: { benchmark: Benchmark }) {
  const baselineMax = Math.max(...benchmark.baselines.map((b) => b.rocAuc ?? 0));

  return (
    <div className="flex flex-col gap-6">
      <div className="card p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <h2 className="font-display text-xl font-semibold text-ink">{benchmark.endpointName}</h2>
          <span className="break-all font-mono text-[11px] text-ink-soft">{benchmark.benchmarkId}</span>
        </div>
        <dl className="mt-3 grid grid-cols-2 gap-3 text-xs text-ink-soft sm:grid-cols-4">
          <div>
            <dt className="font-medium text-ink">Dataset</dt>
            <dd>{benchmark.finalCompoundCount.toLocaleString()} compounds ({benchmark.datasetVersion})</dd>
          </div>
          <div>
            <dt className="font-medium text-ink">Source</dt>
            <dd>{benchmark.datasetSource}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink">Licence</dt>
            <dd>{benchmark.license}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink">Split method</dt>
            <dd className="capitalize">{benchmark.splitMethod}</dd>
          </div>
        </dl>
        <p className="mt-2 text-xs leading-relaxed text-ink-soft">{benchmark.splitDescription}</p>
        <p className="mt-2 break-words font-mono text-[11px] text-ink-soft">
          Model v{benchmark.modelVersion} · evaluated {benchmark.evaluationDate} · source: {benchmark.sourceFile}
        </p>
      </div>

      {/* Performance */}
      <div className="card p-6">
        <h3 className="font-display text-base font-semibold text-ink">Performance on the held-out scaffold-split test set</h3>
        <p className="mt-1 text-xs text-ink-soft">
          n = {benchmark.scaffoldSplitTest.n}, never seen during training or hyperparameter tuning.
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">ROC-AUC</dt>
            <dd className="font-mono text-ink">
              {num3(benchmark.scaffoldSplitTest.rocAuc)}
              {benchmark.scaffoldSplitTest.confidenceInterval95 && (
                <span className="ml-1 text-xs text-ink-soft">
                  (95% CI {num3(benchmark.scaffoldSplitTest.confidenceInterval95.lower)}–{num3(benchmark.scaffoldSplitTest.confidenceInterval95.upper)})
                </span>
              )}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Balanced accuracy</dt>
            <dd className="font-mono text-ink">{pct(benchmark.scaffoldSplitTest.balancedAccuracy)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">F1</dt>
            <dd className="font-mono text-ink">{num3(benchmark.scaffoldSplitTest.f1)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Precision / Recall</dt>
            <dd className="font-mono text-ink">
              {num3(benchmark.scaffoldSplitTest.precision)} / {num3(benchmark.scaffoldSplitTest.recall)}
            </dd>
          </div>
          {benchmark.scaffoldSplitTest.matthewsCorrcoef !== undefined && (
            <div>
              <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">MCC</dt>
              <dd className="font-mono text-ink">{num3(benchmark.scaffoldSplitTest.matthewsCorrcoef)}</dd>
            </div>
          )}
          {benchmark.scaffoldSplitTest.specificity !== undefined && (
            <div>
              <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Specificity</dt>
              <dd className="font-mono text-ink">{pct(benchmark.scaffoldSplitTest.specificity)}</dd>
            </div>
          )}
        </dl>

        <p className="mt-4 text-xs font-medium text-ink">Confusion matrix (scaffold-split test set)</p>
        <div className="mt-2 max-w-sm">
          <ConfusionMatrixGrid matrix={benchmark.scaffoldSplitTest.confusionMatrix} />
        </div>

        <details className="mt-4 text-xs text-ink-soft">
          <summary className="cursor-pointer font-medium text-ink hover:underline">
            Random-split comparison (ROC-AUC gap: {num3(benchmark.rocAucGap)})
          </summary>
          <p className="mt-2 leading-relaxed">{benchmark.gapExplanation}</p>
        </details>
      </div>

      {/* Baselines */}
      <div className="card p-6">
        <h3 className="font-display text-base font-semibold text-ink">Compared against simple baselines</h3>
        <p className="mt-1 text-xs text-ink-soft">ROC-AUC on the same held-out data. A random or constant predictor scores 0.5 or is undefined.</p>
        <div className="mt-4 flex flex-col gap-2">
          {benchmark.baselines.map((b) => (
            <BarRow key={b.name} label={b.name} value={b.rocAuc} max={Math.max(baselineMax, 1)} highlight={b.name.startsWith("DrugSim")} />
          ))}
        </div>
      </div>

      {/* External validation */}
      {benchmark.externalValidation && (
        <div className="card p-6">
          <h3 className="font-display text-base font-semibold text-ink">External validation</h3>
          <p className="mt-1 text-sm text-ink">{benchmark.externalValidation.datasetName}</p>
          <p className="mt-1 text-xs leading-relaxed text-ink-soft">{benchmark.externalValidation.provenanceNote}</p>
          <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
            <div>
              <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">n</dt>
              <dd className="font-mono text-ink">{benchmark.externalValidation.n.toLocaleString()}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">ROC-AUC</dt>
              <dd className="font-mono text-ink">{num3(benchmark.externalValidation.rocAuc)}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Balanced accuracy</dt>
              <dd className="font-mono text-ink">{pct(benchmark.externalValidation.balancedAccuracy)}</dd>
            </div>
            <div>
              <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">MCC</dt>
              <dd className="font-mono text-ink">{num3(benchmark.externalValidation.matthewsCorrcoef)}</dd>
            </div>
          </dl>
          <div className="mt-3 max-w-sm">
            <ConfusionMatrixGrid matrix={benchmark.externalValidation.confusionMatrix} />
          </div>
          <p className="mt-3 rounded-md border border-line bg-paper-alt p-3 text-xs leading-relaxed text-ink-soft">
            {benchmark.externalValidation.labelDefinitionCaveat}
          </p>
        </div>
      )}

      {/* Applicability domain */}
      {benchmark.applicabilityDomainTiers && (
        <div className="card p-6">
          <h3 className="font-display text-base font-semibold text-ink">Performance by applicability-domain tier</h3>
          <p className="mt-1 text-xs leading-relaxed text-ink-soft">
            Whether the applicability-domain check actually tracks reliability, tested directly rather than assumed.
          </p>
          <div className="mt-3">
            <ApplicabilityDomainTierList tiers={benchmark.applicabilityDomainTiers} />
          </div>
        </div>
      )}

      {/* Calibration / uncertainty */}
      <div className="card p-6">
        <h3 className="font-display text-base font-semibold text-ink">Uncertainty calibration</h3>
        <dl className="mt-3 grid grid-cols-2 gap-3 text-sm sm:grid-cols-4">
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Nominal confidence</dt>
            <dd className="font-mono text-ink">{pct(benchmark.calibration.nominalConfidence)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Empirical coverage (internal)</dt>
            <dd className="font-mono text-ink">{pct(benchmark.calibration.internalEmpiricalCoverage)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Brier score</dt>
            <dd className="font-mono text-ink">{num3(benchmark.calibration.internalBrierScore)}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Expected calibration error</dt>
            <dd className="font-mono text-ink">{num3(benchmark.calibration.internalEce)}</dd>
          </div>
        </dl>
        {benchmark.calibration.externalEmpiricalCoverage !== null && (
          <p className="mt-3 text-xs leading-relaxed text-ink-soft">
            Coverage measured again on {benchmark.calibration.externalN?.toLocaleString()} external compounds, a real
            distribution shift from the calibration population: {pct(benchmark.calibration.externalEmpiricalCoverage)}{" "}
            empirical coverage against the same {pct(benchmark.calibration.nominalConfidence)} nominal target.
          </p>
        )}
        <p className="mt-2 text-xs leading-relaxed text-ink-soft">
          This is a population-level guarantee (on average, across many predictions), never a per-instance probability
          that one specific prediction is correct.
        </p>
      </div>

      {/* AI comparison */}
      <div className="card min-w-0 p-6">
        <h3 className="font-display text-base font-semibold text-ink">DrugSim vs. general-purpose AI</h3>
        <div className="mt-3 overflow-x-auto">
          <div className="grid min-w-[480px] grid-cols-4 gap-2 text-sm">
            <div className="text-xs font-medium tracking-wide text-ink-soft uppercase">Metric</div>
            <div className="text-xs font-medium tracking-wide text-ink-soft uppercase">DrugSim</div>
            <div className="text-xs font-medium tracking-wide text-ink-soft uppercase">GPT</div>
            <div className="text-xs font-medium tracking-wide text-ink-soft uppercase">Claude</div>

            <div className="text-ink-soft">ROC-AUC</div>
            <div className="font-mono text-ink">{pct(benchmark.scaffoldSplitTest.rocAuc)}</div>
            <div><AiMetricCell result={benchmark.aiComparison.gpt} metric="rocAuc" /></div>
            <div><AiMetricCell result={benchmark.aiComparison.claude} metric="rocAuc" /></div>

            <div className="text-ink-soft">Balanced accuracy</div>
            <div className="font-mono text-ink">{pct(benchmark.scaffoldSplitTest.balancedAccuracy)}</div>
            <div><AiMetricCell result={benchmark.aiComparison.gpt} metric="accuracy" /></div>
            <div><AiMetricCell result={benchmark.aiComparison.claude} metric="accuracy" /></div>

            <div className="text-ink-soft">F1</div>
            <div className="font-mono text-ink">{pct(benchmark.scaffoldSplitTest.f1)}</div>
            <div><AiMetricCell result={benchmark.aiComparison.gpt} metric="f1" /></div>
            <div><AiMetricCell result={benchmark.aiComparison.claude} metric="f1" /></div>
          </div>
        </div>
        {benchmark.aiComparison.gpt.notEvaluatedReason !== null && benchmark.aiComparison.claude.notEvaluatedReason !== null && (
          <p className="mt-3 text-xs leading-relaxed text-ink-soft">
            No GPT or Claude evaluation has been run against this benchmark yet. Running one requires the documented,
            identical-inputs protocol at{" "}
            <Link to="/benchmarks" className="underline underline-offset-2 hover:text-ink">
              docs/benchmarks/ai-comparison-protocol.md
            </Link>{" "}
            — not an informal comparison, and not a number inferred from general knowledge of how these models perform.
          </p>
        )}
        {benchmark.aiComparison.claude.notEvaluatedReason === null && (
          <p className="mt-3 text-xs leading-relaxed text-ink-soft">
            Claude's numbers here are real (n = {benchmark.aiComparison.claude.n}, evaluated{" "}
            {benchmark.aiComparison.claude.evaluatedAt}, hover a value for the full methodology note) but are{" "}
            <strong>not</strong> the documented protocol at{" "}
            <Link to="/benchmarks" className="underline underline-offset-2 hover:text-ink">
              docs/benchmarks/ai-comparison-protocol.md
            </Link>
            , which specifies 3 independent runs per compound in fresh sessions — not achievable for Claude within a
            single conversation. GPT remains not evaluated: no API access.
          </p>
        )}
      </div>
    </div>
  );
}

export function BenchmarkPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Benchmarks</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">DrugSim Benchmark Explorer</h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          Real, reproducible evidence for each validated endpoint — the dataset it was trained and tested on, its
          performance against a held-out scaffold split and an independent external dataset, and where it is
          compared with general-purpose AI, exactly what has and has not actually been evaluated. Every number below
          traces to a specific report already in the repository; see{" "}
          <span className="font-mono text-xs">docs/benchmarks/dataset-registry.md</span> for the full citation trail.
        </p>
      </header>

      <section className="card p-6">
        <h2 className="font-display text-lg font-semibold text-ink">Overall scientific database</h2>
        <p className="mt-1 text-xs leading-relaxed text-ink-soft">
          The scale of ChEMBL, the source database. This is <strong>not</strong> the size of either endpoint's own
          training set below — a model trained on a few thousand labelled compounds is not the same claim as a
          database of millions of unlabelled bioactivity records.
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
          <div>
            <dt className="font-mono text-2xl font-semibold text-ink">{(OVERALL_DATABASE_SCALE.distinctCompounds / 1_000_000).toFixed(1)}M+</dt>
            <dd className="text-xs text-ink-soft">compounds</dd>
          </div>
          <div>
            <dt className="font-mono text-2xl font-semibold text-ink">{(OVERALL_DATABASE_SCALE.bioactivityMeasurements / 1_000_000).toFixed(1)}M+</dt>
            <dd className="text-xs text-ink-soft">bioactivity measurements</dd>
          </div>
          <div>
            <dt className="font-mono text-2xl font-semibold text-ink">{(OVERALL_DATABASE_SCALE.assays / 1_000_000).toFixed(1)}M+</dt>
            <dd className="text-xs text-ink-soft">assays</dd>
          </div>
          <div>
            <dt className="font-mono text-2xl font-semibold text-ink">{Math.round(OVERALL_DATABASE_SCALE.targets / 1000)}K+</dt>
            <dd className="text-xs text-ink-soft">targets</dd>
          </div>
        </dl>
        <p className="mt-3 break-words font-mono text-[11px] text-ink-soft">
          {OVERALL_DATABASE_SCALE.source} · source: {OVERALL_DATABASE_SCALE.sourceFile}
        </p>
      </section>

      {BENCHMARKS.map((benchmark) => (
        <section key={benchmark.benchmarkId} className="flex flex-col gap-6">
          <BenchmarkSection benchmark={benchmark} />
        </section>
      ))}

      {/* Individual molecule explorer */}
      <section className="flex flex-col gap-4">
        <div>
          <h2 className="font-display text-lg font-semibold text-ink">Explore individual cases</h2>
          <p className="mt-1 text-sm leading-relaxed text-ink-soft">
            Real, live predictions against public, well-documented compounds — never a confidential or customer
            structure. Ground truth is public pharmacological knowledge, cited per compound, not DrugSim's own
            private training or test data.
          </p>
          <p className="mt-2 text-xs leading-relaxed text-ink-soft">
            Each card also shows a single Claude prediction made directly in a development session — SMILES only,
            compound name withheld until after the answer was recorded. This is <strong>not</strong> the documented
            AI-comparison protocol (one run, not three; no temperature control) and does not fill in the "Not
            evaluated" cells above, which require a full run against DrugSim's own held-out test set. It's an
            informal spot-check on four illustrative compounds, shown for transparency, not a validated result.
          </p>
        </div>
        {EXAMPLE_CASE_PREDICTIONS.map((c) => (
          <div key={c.compoundName} className="card p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-medium text-ink">{c.compoundName}</h3>
              <span className={`font-mono text-xs font-medium ${c.correct ? "text-signal" : "text-concern"}`}>
                {c.correct ? "Matches ground truth ✓" : "Disagrees with ground truth ✕"}
              </span>
            </div>
            <p className="mt-1 font-mono text-[11px] text-ink-soft break-all">{c.smiles}</p>
            <dl className="mt-3 grid grid-cols-2 gap-3 text-xs sm:grid-cols-4">
              <div>
                <dt className="font-medium text-ink-soft uppercase tracking-wide">Public ground truth</dt>
                <dd className="mt-0.5 text-ink">{c.publicGroundTruth.replace("_", "-")}</dd>
              </div>
              <div>
                <dt className="font-medium text-ink-soft uppercase tracking-wide">DrugSim prediction</dt>
                <dd className="mt-0.5 text-ink">
                  {c.drugsimLabel.replace("_", "-")} (p={c.drugsimProbability.toFixed(3)})
                </dd>
              </div>
              <div>
                <dt className="font-medium text-ink-soft uppercase tracking-wide">Uncertainty (90% set)</dt>
                <dd className="mt-0.5 text-ink">
                  {c.conformalSingleton ? "confident, single outcome" : `ambiguous: {${c.conformalSet.join(", ")}}`}
                </dd>
              </div>
              <div>
                <dt className="font-medium text-ink-soft uppercase tracking-wide">Applicability domain</dt>
                <dd className="mt-0.5 text-ink">{c.applicabilityDomainVerdict.replace(/_/g, " ")}</dd>
              </div>
            </dl>
            <p className="mt-2 text-xs leading-relaxed text-ink-soft">{c.groundTruthSource}</p>
            <div className="mt-2 flex flex-wrap gap-x-2 gap-y-1 font-mono text-[10px] text-ink-soft">
              <span>GPT: not evaluated</span>
              <span>·</span>
              <ClaudeSpotCheckNote spotCheck={c.claudeSpotCheck} />
              <span>·</span>
              <span>live prediction captured {c.evaluatedAt}</span>
            </div>
          </div>
        ))}
      </section>

      {/* Claude informal subset evaluation -- 30 of 800, not the protocol */}
      <section className="card p-6">
        <h2 className="font-display text-lg font-semibold text-ink">Claude — informal subset evaluation</h2>
        <p className="mt-1 text-sm leading-relaxed text-ink-soft">
          {CLAUDE_HERG_SUBSET_EVALUATION.n} of DrugSim's real 800-compound held-out hERG test set (stratified sample,
          seed {CLAUDE_HERG_SUBSET_EVALUATION.seed}), evaluated by {CLAUDE_HERG_SUBSET_EVALUATION.modelIdentifier} on{" "}
          {CLAUDE_HERG_SUBSET_EVALUATION.runDate}. Each compound was judged by an independently-isolated subagent —
          SMILES only, no ground truth, no visibility into any other compound's answer — so this is genuinely
          independent across compounds. It is <strong>not</strong> the documented protocol: one run per compound, not
          three fresh-session repeats, and it is 30 of 800 compounds, not the full set. ROC-AUC was added afterward by
          asking each already-dispatched subagent for a 0-100 probability consistent with its own prior verdict, not
          a fresh run. This does not fill in the "Not evaluated" cells above.
        </p>
        <dl className="mt-4 grid grid-cols-2 gap-3 text-xs sm:grid-cols-3">
          <div>
            <dt className="font-medium text-ink-soft uppercase tracking-wide">ROC-AUC</dt>
            <dd className="mt-0.5 font-mono text-ink">{pct(CLAUDE_HERG_SUBSET_EVALUATION.rocAuc)}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink-soft uppercase tracking-wide">Accuracy</dt>
            <dd className="mt-0.5 font-mono text-ink">{pct(CLAUDE_HERG_SUBSET_EVALUATION.accuracy)}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink-soft uppercase tracking-wide">Balanced accuracy</dt>
            <dd className="mt-0.5 font-mono text-ink">{pct(CLAUDE_HERG_SUBSET_EVALUATION.balancedAccuracy)}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink-soft uppercase tracking-wide">F1</dt>
            <dd className="mt-0.5 font-mono text-ink">{pct(CLAUDE_HERG_SUBSET_EVALUATION.f1)}</dd>
          </div>
          <div>
            <dt className="font-medium text-ink-soft uppercase tracking-wide">Precision / Recall</dt>
            <dd className="mt-0.5 font-mono text-ink">
              {pct(CLAUDE_HERG_SUBSET_EVALUATION.precision)} / {pct(CLAUDE_HERG_SUBSET_EVALUATION.recall)}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-ink-soft uppercase tracking-wide">Specificity</dt>
            <dd className="mt-0.5 font-mono text-ink">{pct(CLAUDE_HERG_SUBSET_EVALUATION.specificity)}</dd>
          </div>
        </dl>
        <div className="mt-4">
          <ConfusionMatrixGrid
            matrix={{
              tn: CLAUDE_HERG_SUBSET_EVALUATION.confusionMatrix.tn,
              fp: CLAUDE_HERG_SUBSET_EVALUATION.confusionMatrix.fp,
              fn: CLAUDE_HERG_SUBSET_EVALUATION.confusionMatrix.fn,
              tp: CLAUDE_HERG_SUBSET_EVALUATION.confusionMatrix.tp,
            }}
          />
        </div>
        {(() => {
          const hergBenchmark = BENCHMARKS.find((b) => b.endpointId === "herg_inhibition");
          if (!hergBenchmark) return null;
          return (
            <p className="mt-3 text-xs leading-relaxed text-ink-soft">
              For comparison, DrugSim's own registered model on the full 800-compound version of this same test set:
              ROC-AUC {pct(hergBenchmark.scaffoldSplitTest.rocAuc)}, balanced accuracy{" "}
              {pct(hergBenchmark.scaffoldSplitTest.balancedAccuracy)}, F1 {pct(hergBenchmark.scaffoldSplitTest.f1)}.
              This subset result is lower on all three — a real difference on 30 compounds, not a claim about DrugSim
              being "better," since 30 compounds is far too small a sample to establish that on its own.
            </p>
          );
        })()}
        <p className="mt-2 font-mono text-[10px] text-ink-soft break-all">source: {CLAUDE_HERG_SUBSET_EVALUATION.sourceFile}</p>
      </section>

      {/* Methodology */}
      <section className="card p-6">
        <h2 className="font-display text-lg font-semibold text-ink">Methodology</h2>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink-soft">
          <li>Splits are scaffold-based (ADR-009), never random — structurally related compounds cannot appear in both train and test.</li>
          <li>Every reported number comes from a report already checked into the repository; none is recomputed for this page.</li>
          <li>External validation uses a dataset from a different lab and assay technology than training, never used for training, feature selection, hyperparameter tuning, or calibration.</li>
          <li>GPT and Claude have not been evaluated. The comparison protocol is fully specified before any run, so the same inputs reach every system.</li>
        </ul>
      </section>

      {/* Limitations */}
      <section className="rounded-lg border border-concern/30 bg-concern-soft p-6">
        <h2 className="font-display text-lg font-semibold text-ink">Limitations</h2>
        <ul className="mt-2 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink-soft">
          <li>Test sets are small (hundreds of compounds, not the millions in the overall ChEMBL database) — individual metrics carry real sampling uncertainty.</li>
          <li>No true external benchmark split (e.g. a TDC-canonical split) exists for either endpoint's exact compound set — the random-split numbers shown are a within-dataset ablation, not a leaderboard-comparable score.</li>
          <li>The applicability-domain mechanism only partially, not cleanly, tracks reliability — see each endpoint's own tier breakdown above rather than assuming a clean gradient.</li>
          <li>External validation label definitions differ from training label definitions (a different assay technology and a different active/inactive convention) — some disagreement is expected from that alone, not only from model error.</li>
          <li>Comparing a specialised, narrowly-scoped model against a general-purpose AI is not apples-to-apples even when it is run: the AI was never trained or fit on this specific task's data at all.</li>
        </ul>
        <p className="mt-3 text-sm font-medium text-ink">
          Benchmark results do not establish clinical validity and should not replace experimental testing.
        </p>
      </section>
    </div>
  );
}
