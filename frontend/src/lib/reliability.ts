import type { Reliability } from "../api/types";

export type ReliabilityRating = "High" | "Moderate" | "Low";

/**
 * The Phase 5 API has no dedicated reliability-rating field — it returns
 * the applicability-domain verdict and the conformal prediction set, both
 * real backend outputs. This function summarises those two signals into a
 * single label for the primary results view.
 *
 * This is a PRESENTATIONAL summary, not a new scientific calculation: no
 * chemistry, no statistics beyond an if/else over two already-computed
 * verdicts. It is disclosed as derived (never presented as a backend field)
 * everywhere it appears — see ReliabilityBadge's caption.
 */
export function deriveReliabilityRating(reliability: Reliability): ReliabilityRating {
  const { applicability_domain, conformal } = reliability;

  if (applicability_domain.verdict === "out_of_domain" || applicability_domain.verdict === "undeterminable") {
    return "Low";
  }
  if (applicability_domain.verdict === "borderline") {
    return "Moderate";
  }
  // in_domain
  return conformal.is_singleton ? "High" : "Moderate";
}
