import type { ADVerdict, ApplicabilityDomain } from "../api/types";

const VERDICT_COPY: Record<ADVerdict, { label: string; description: string }> = {
  in_domain: {
    label: "Within known chemistry",
    description:
      "This structure closely resembles compounds the model was trained on, so the model has real, relevant experience to draw on for this prediction.",
  },
  borderline: {
    label: "Borderline",
    description:
      "This structure is only somewhat similar to the training chemistry. The model has partial experience with structures like this one, so treat the prediction with more caution than usual.",
  },
  out_of_domain: {
    label: "Novel chemistry",
    description:
      "This structure is substantially different from anything the model was trained on. The model is extrapolating far beyond its training experience here, so this prediction is much less trustworthy than one made on familiar chemistry.",
  },
  undeterminable: {
    label: "Could not be assessed",
    description: "The applicability domain could not be evaluated for this structure.",
  },
};

/**
 * User feedback (this revision): a common, simple drug like paracetamol
 * getting flagged "Novel Chemistry" reads as a bug — it isn't. The models
 * here are trained on large collections of complex pharmaceutical
 * candidates (see each endpoint's training_set_size), so a small, simple,
 * long-approved molecule can sit outside that chemical space even though
 * it is thoroughly well-understood in reality. Shown only for the two
 * verdicts a user could plausibly find surprising.
 */
const SIMPLE_MOLECULE_NOTE =
  "Note: very common, simple molecules (like paracetamol or aspirin) are often flagged this way. " +
  "This is because the model was trained on large, complex pharmaceutical drug candidates. If your " +
  "molecule is small or structurally simple, it falls outside the model's training space even when " +
  "the chemistry itself is well understood.";

/**
 * Splits the backend's rationale sentence into its three clauses for
 * display as a bullet list. drugsim_predict.applicability_domain always
 * builds this string as exactly three "; "-joined clauses (max similarity,
 * scaffold membership, k-NN distance) ending in a period — see that
 * module's docstring. Never alters the substance of any clause, only where
 * the line breaks and a leading capital for readability; if the string
 * ever doesn't match that shape (e.g. the single-sentence "could not be
 * computed" case), it falls back to one bullet with the original text
 * untouched.
 */
function rationaleBullets(rationale: string): string[] {
  return rationale
    .split("; ")
    .map((clause) => clause.trim().replace(/\.$/, ""))
    .filter(Boolean)
    .map((clause) => clause.charAt(0).toUpperCase() + clause.slice(1));
}

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
  const bullets = rationaleBullets(rationale);
  const showSimpleMoleculeNote = verdict === "out_of_domain" || verdict === "borderline";

  return (
    <div>
      <div className="flex items-baseline justify-between">
        <h3 className="text-sm font-medium text-ink">Applicability domain</h3>
        <span className="text-sm font-medium" style={{ color }}>
          {copy.label}
        </span>
      </div>
      <p className="mt-1 text-xs leading-relaxed text-ink-soft">
        How closely this molecule resembles the chemistry the model was actually trained on —
        not whether the prediction itself is correct.
      </p>

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
            // Transitioning transform, not just plopping the marker at its
            // final spot: a later prediction reuses this same SVG node (no
            // remount), so without this a re-run's marker would just teleport.
            // Sliding it communicates "the evidence for THIS molecule moved
            // from the last one" -- a real state change, not a decoration.
            <g
              transform={`translate(${10 + (positionPercent / 100) * 380}, 28)`}
              style={{ transition: "transform 500ms ease-out" }}
            >
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

      {showSimpleMoleculeNote && (
        <p className="mt-2 rounded-md border border-line bg-paper-alt p-3 text-xs leading-relaxed text-ink-soft">
          {SIMPLE_MOLECULE_NOTE}
        </p>
      )}

      <p className="mt-3 text-xs font-medium text-ink-soft">Supporting detail from the model</p>
      <ul className="mt-1 list-disc space-y-1 pl-4 text-xs leading-relaxed text-ink-soft">
        {bullets.map((clause) => (
          <li key={clause}>{clause}</li>
        ))}
      </ul>

      <p className="mt-2 text-xs leading-relaxed text-ink-soft">
        This describes how much relevant evidence the model has for chemistry like this —
        it does not mean the prediction itself is biologically correct.
      </p>
    </div>
  );
}
