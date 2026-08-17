import type { ConformalResult } from "../api/types";
import { labelText } from "../lib/endpointCopy";

interface Props {
  conformal: ConformalResult;
  endpoint: string;
}

/**
 * Shows the conformal prediction set exactly as returned — never converted
 * into an invented confidence percentage. The backend's coverage guarantee
 * is marginal/population-level, not a per-instance correctness probability
 * (see drugsim_predict.conformal module docstring); this panel's copy
 * reflects that distinction rather than papering over it.
 *
 * User feedback (this revision): the two p-values the API already returns
 * (conformal.p_value_blocker / p_value_non_blocker) were computed but never
 * shown, and nobody who isn't already a conformal-prediction practitioner
 * knows what "p-value" means here without being told. Both gaps are fixed
 * below with a plain-English definition and the real numbers — never a
 * paraphrase or an invented percentage.
 */
export function UncertaintyPanel({ conformal, endpoint }: Props) {
  const { predicted_set, nominal_confidence, is_singleton, p_value_blocker, p_value_non_blocker } = conformal;
  const confidencePct = Math.round(nominal_confidence * 100);

  return (
    <div>
      <h3 className="text-sm font-medium text-ink">Uncertainty</h3>
      <div className="mt-3 flex flex-wrap gap-2">
        {predicted_set.map((label) => (
          <span
            key={label}
            className="rounded-full border border-line bg-paper-alt px-3 py-1 text-sm font-medium text-ink"
          >
            {labelText(endpoint, label)}
          </span>
        ))}
        {predicted_set.length === 0 && (
          <span className="text-sm text-ink-soft">No class remained plausible at this confidence level.</span>
        )}
      </div>
      <p className="mt-3 text-sm leading-relaxed text-ink-soft">
        {is_singleton
          ? `At ${confidencePct}% target coverage, only this outcome remains plausible for this structure.`
          : `At ${confidencePct}% target coverage, both outcomes remain plausible — the model cannot distinguish them confidently for this structure.`}
      </p>

      <dl className="mt-4 divide-y divide-line rounded-md border border-line bg-paper-alt text-sm">
        <div className="flex items-center justify-between gap-3 px-3 py-2">
          <dt className="text-ink-soft">p-value — {labelText(endpoint, "blocker")}</dt>
          <dd className="font-mono text-ink">{p_value_blocker.toFixed(3)}</dd>
        </div>
        <div className="flex items-center justify-between gap-3 px-3 py-2">
          <dt className="text-ink-soft">p-value — {labelText(endpoint, "non_blocker")}</dt>
          <dd className="font-mono text-ink">{p_value_non_blocker.toFixed(3)}</dd>
        </div>
      </dl>

      <details className="mt-2 text-xs text-ink-soft">
        <summary className="cursor-pointer select-none font-medium text-ink hover:underline">
          What is a p-value here?
        </summary>
        <p className="mt-2 leading-relaxed">
          In conformal prediction, a p-value represents the fraction of training examples
          that look more extreme than your molecule, for a given class. A low p-value means
          the model strongly doubts that class; a high p-value means the class remains
          plausible. A class stays in the predicted set above whenever its p-value is high
          enough to clear the {confidencePct}% target coverage threshold — that's why a
          result can list one outcome or both.
        </p>
      </details>

      <p className="mt-3 text-xs leading-relaxed text-ink-soft">
        This is a population-level coverage guarantee (the true outcome falls in the
        stated set at least {confidencePct}% of the time across many predictions), not a
        probability that this specific prediction is correct.
      </p>
    </div>
  );
}
