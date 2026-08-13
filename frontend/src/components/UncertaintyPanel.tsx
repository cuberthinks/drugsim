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
 */
export function UncertaintyPanel({ conformal, endpoint }: Props) {
  const { predicted_set, nominal_confidence, is_singleton } = conformal;
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
      <p className="mt-2 text-xs leading-relaxed text-ink-soft">
        This is a population-level coverage guarantee (the true outcome falls in the
        stated set at least {confidencePct}% of the time across many predictions), not a
        probability that this specific prediction is correct.
      </p>
    </div>
  );
}
