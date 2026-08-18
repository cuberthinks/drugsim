import type { EndpointListItem, PredictionResponse } from "../api/types";
import { ApiError } from "../api/client";
import { getEndpointCopy, labelText } from "../lib/endpointCopy";
import { deriveReliabilityRating } from "../lib/reliability";

const RATING_COLOR: Record<string, string> = {
  High: "var(--color-signal)",
  Moderate: "var(--color-caution)",
  Low: "var(--color-concern)",
};

interface Props {
  endpoint: EndpointListItem;
  state: { status: "loading" } | { status: "error"; error: ApiError } | { status: "done"; prediction: PredictionResponse };
}

/**
 * One endpoint's slice of the DrugSim Compound Profile (Phase 10 Sec 7):
 * prediction, uncertainty, and reliability together, at equal visual
 * weight — never a bare label. A failed endpoint shows an honest error
 * card, never a fabricated or blank-but-implied-fine result.
 */
export function EndpointProfileCard({ endpoint, state }: Props) {
  const copy = getEndpointCopy(endpoint.model_id);

  return (
    <div className="rounded-lg border border-line bg-white p-5">
      <p className="font-mono text-xs text-ink-soft">{endpoint.model_id}</p>
      <h3 className="mt-1 font-display text-base font-semibold text-ink">{endpoint.endpoint_name}</h3>

      {state.status === "loading" && (
        <p className="mt-3 text-sm text-ink-soft" role="status">
          Running prediction…
        </p>
      )}

      {state.status === "error" && (
        <div role="alert" className="mt-3 rounded-md border border-concern/40 bg-concern-soft p-3">
          <p className="text-sm font-medium text-concern">Could not complete this prediction</p>
          <p className="mt-1 text-xs leading-relaxed text-ink-soft">{state.error.message}</p>
        </div>
      )}

      {state.status === "done" && (
        <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-3">
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Prediction</dt>
            <dd className="mt-1 text-sm font-semibold text-ink">
              {labelText(endpoint.model_id, state.prediction.estimate.predicted_label)}
            </dd>
            <dd className="mt-0.5 font-mono text-xs text-ink-soft">
              {copy.probabilityCaption.replace(/^Estimated probability of /i, "p=")}: {state.prediction.estimate.predicted_probability.toFixed(3)}
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Uncertainty</dt>
            <dd className="mt-1 text-sm text-ink">
              {state.prediction.reliability.conformal.is_singleton ? "Confident (single outcome)" : "Ambiguous (both outcomes plausible)"}
            </dd>
            <dd className="mt-0.5 font-mono text-xs text-ink-soft">
              {Math.round(state.prediction.reliability.conformal.nominal_confidence * 100)}% target coverage
            </dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Reliability</dt>
            <dd
              className="mt-1 text-sm font-semibold"
              style={{ color: RATING_COLOR[deriveReliabilityRating(state.prediction.reliability)] }}
            >
              {deriveReliabilityRating(state.prediction.reliability)}
            </dd>
            <dd className="mt-0.5 font-mono text-xs text-ink-soft">
              {state.prediction.reliability.applicability_domain.verdict.replace(/_/g, " ")}
            </dd>
          </div>
        </dl>
      )}
    </div>
  );
}
