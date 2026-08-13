import type { ADVerdict, ApplicabilityDomain } from "../api/types";

const VERDICT_COPY: Record<ADVerdict, { label: string; description: string }> = {
  in_domain: {
    label: "Within known chemistry",
    description: "This structure closely resembles compounds the model was trained on.",
  },
  borderline: {
    label: "Borderline",
    description: "This structure is somewhat similar to the training chemistry, but not closely.",
  },
  out_of_domain: {
    label: "Novel chemistry",
    description: "This structure is substantially different from anything the model was trained on. Treat this prediction as an extrapolation.",
  },
  undeterminable: {
    label: "Could not be assessed",
    description: "The applicability domain could not be evaluated for this structure.",
  },
};

const VERDICT_COLOR: Record<ADVerdict, string> = {
  in_domain: "var(--color-signal)",
  borderline: "var(--color-caution)",
  out_of_domain: "var(--color-concern)",
  undeterminable: "var(--color-ink-soft)",
};

interface Props {
  applicabilityDomain: ApplicabilityDomain;
}

/**
 * The product's signature visualization: a chemical-evidence gradient from
 * "known chemistry" to "novel chemistry", with the query molecule marked at
 * its actual measured Tanimoto similarity to the training set.
 *
 * This communicates evidence, not correctness — the copy is deliberately
 * explicit that a favourable position here means the model has more
 * relevant training data, not that the prediction is biologically true.
 *
 * Phase 7 UX finding: a heuristic walkthrough from a "biomedical
 * background, limited cheminformatics knowledge" persona found that the
 * backend's own rationale string ("descriptor-space distance to nearest
 * training neighbours is 2.56...") is accurate but leans on specialist
 * vocabulary. The fix is not to alter or hide that string (still shown,
 * labelled as supporting technical detail — never invented, never
 * dropped) but to lead with the plain-language `copy.description` per
 * verdict, which existed in this file already but was never rendered.
 */
export function ApplicabilityDomainGauge({ applicabilityDomain }: Props) {
  const { verdict, max_tanimoto_to_training, rationale } = applicabilityDomain;
  const copy = VERDICT_COPY[verdict];
  const color = VERDICT_COLOR[verdict];
  const hasPosition = max_tanimoto_to_training !== null;
  // 0% = fully known (tanimoto 1.0), 100% = fully novel (tanimoto 0.0)
  const positionPercent = hasPosition ? (1 - max_tanimoto_to_training) * 100 : null;

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-ink">Applicability domain</h3>
        <span className="text-sm font-medium" style={{ color }}>
          {copy.label}
        </span>
      </div>

      <div className="mt-4">
        <svg viewBox="0 0 400 56" className="w-full" role="img" aria-label={`Applicability domain: ${copy.label}. ${rationale}`}>
          <defs>
            <linearGradient id="ad-gradient" x1="0" x2="1" y1="0" y2="0">
              <stop offset="0%" stopColor="#1c6e6e" />
              <stop offset="50%" stopColor="#a6631b" />
              <stop offset="100%" stopColor="#8b3a3a" />
            </linearGradient>
          </defs>
          <line x1="10" y1="28" x2="390" y2="28" stroke="url(#ad-gradient)" strokeWidth="4" strokeLinecap="round" />
          {hasPosition && positionPercent !== null && (
            <g transform={`translate(${10 + (positionPercent / 100) * 380}, 28)`}>
              <line y1="-14" y2="8" stroke={color} strokeWidth="2" />
              <circle r="6" fill={color} stroke="white" strokeWidth="2" />
            </g>
          )}
        </svg>
        <div className="mt-1 flex justify-between font-mono text-[11px] text-ink-soft">
          <span>Known chemistry</span>
          <span>Novel chemistry</span>
        </div>
      </div>

      <p className="mt-3 text-sm leading-relaxed text-ink">{copy.description}</p>
      <p className="mt-2 text-xs leading-relaxed text-ink-soft">
        <span className="font-medium">Supporting detail from the model:</span> {rationale}
      </p>
      <p className="mt-2 text-xs leading-relaxed text-ink-soft">
        This describes how much relevant evidence the model has for chemistry like this —
        it does not mean the prediction itself is biologically correct.
      </p>
    </div>
  );
}
