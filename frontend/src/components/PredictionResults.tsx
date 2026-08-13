import type { PredictionResponse } from "../api/types";
import { getEndpointCopy, labelText } from "../lib/endpointCopy";
import { ApplicabilityDomainGauge } from "./ApplicabilityDomainGauge";
import { ModelEvidencePanel } from "./ModelEvidencePanel";
import { ReliabilityBadge } from "./ReliabilityBadge";
import { ScientificExplanation } from "./ScientificExplanation";
import { UncertaintyPanel } from "./UncertaintyPanel";
import { WarningsList } from "./WarningsList";

/**
 * The primary results dashboard (spec sections 5–6). Every value shown here
 * is read directly from the Phase 5 API response — nothing is computed or
 * invented in this component. Uncertainty, applicability domain, and
 * reliability are laid out with equal visual weight to the headline
 * prediction, never as secondary or hidden detail.
 *
 * Phase 9: this renders whichever single endpoint's result was returned —
 * one endpoint per call, no cross-endpoint "drug score" or combined verdict
 * (Phase 9 Sec 18 explicitly rules that out).
 */
interface Props {
  prediction: PredictionResponse;
  /** User-supplied label (e.g. "Aspirin") -- display only, never sent to or
   * returned by the backend; the prediction itself is unaffected by it. */
  compoundName?: string;
}

export function PredictionResults({ prediction, compoundName }: Props) {
  const { estimate, reliability, provenance, warnings } = prediction;
  const copy = getEndpointCopy(estimate.endpoint);
  const probability = estimate.predicted_probability;

  return (
    <section aria-labelledby="results-heading" className="flex flex-col gap-6">
      <p className="text-xs font-medium tracking-wide text-ink-soft uppercase">Predicted information</p>

      <div className="rounded-lg border border-line bg-white p-6">
        {compoundName?.trim() && <p className="text-sm font-medium text-ink">{compoundName.trim()}</p>}
        <p className="font-mono text-xs text-ink-soft">{estimate.endpoint}</p>
        <h2 id="results-heading" className="mt-1 font-display text-2xl font-semibold text-ink">
          {labelText(estimate.endpoint, estimate.predicted_label)}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          {copy.probabilityCaption}: <span className="font-mono text-ink">{probability.toFixed(3)}</span> — a
          model output, not a measured quantity. Read it together with the uncertainty and
          applicability-domain information below before drawing any conclusion.
        </p>
      </div>

      <WarningsList warnings={warnings} />

      <div className="grid gap-6 md:grid-cols-2">
        <div className="rounded-lg border border-line bg-white p-6">
          <UncertaintyPanel conformal={reliability.conformal} endpoint={estimate.endpoint} />
        </div>
        <div className="rounded-lg border border-line bg-white p-6">
          <ReliabilityBadge reliability={reliability} />
        </div>
      </div>

      <div className="rounded-lg border border-line bg-white p-6">
        <ApplicabilityDomainGauge applicabilityDomain={reliability.applicability_domain} />
      </div>

      <ScientificExplanation endpoint={estimate.endpoint} />

      <ModelEvidencePanel prediction={prediction} />

      <p className="font-mono text-xs text-ink-soft">
        Model {provenance.model_id} v{provenance.model_version} · trained on{" "}
        {provenance.training_set_size.toLocaleString()} compounds · {provenance.final_report_status}
      </p>
    </section>
  );
}
