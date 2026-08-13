import type { Reliability } from "../api/types";
import { deriveReliabilityRating } from "../lib/reliability";

const RATING_COLOR: Record<string, string> = {
  High: "var(--color-signal)",
  Moderate: "var(--color-caution)",
  Low: "var(--color-concern)",
};

export function ReliabilityBadge({ reliability }: { reliability: Reliability }) {
  const rating = deriveReliabilityRating(reliability);
  return (
    <div>
      <h3 className="text-sm font-medium text-ink">Reliability</h3>
      <p className="mt-2 text-2xl font-semibold" style={{ color: RATING_COLOR[rating] }}>
        {rating}
      </p>
      <p className="mt-1 text-xs leading-relaxed text-ink-soft">
        Summarised from the applicability-domain verdict and prediction-set width above —
        not a separate backend measurement.
      </p>
    </div>
  );
}
