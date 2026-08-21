import { Link } from "react-router-dom";

const STEPS = [
  {
    title: "Data",
    body: "Raw bioactivity measurements for each endpoint are assembled from curated public sources, with provenance tracked for every record. Every endpoint uses its own dataset, built and audited independently of the others.",
  },
  {
    title: "Standardisation",
    body: "Structures are parsed, sanitised, and canonicalised through a fixed RDKit-based pipeline so the same molecule always yields the same representation.",
  },
  {
    title: "Dataset",
    body: "Measurements are deduplicated and aggregated per compound, labelled against a fixed activity threshold, and split by scaffold to prevent leakage between training and test sets.",
  },
  {
    title: "Model",
    body: "A classifier is trained on molecular descriptors and fingerprints derived from the standardised structures, then registered with a versioned model ID.",
  },
  {
    title: "Applicability domain",
    body: "Each new structure is compared against the training set by fingerprint similarity, descriptor-space distance, and scaffold membership to assess how well-covered it is by the model's evidence.",
  },
  {
    title: "Uncertainty",
    body: "Split conformal prediction wraps the model's raw output in a calibrated prediction set with a stated coverage guarantee, rather than a single point estimate.",
  },
  {
    title: "Prediction",
    body: "The prediction engine combines the model output, applicability-domain assessment, and conformal set into the response shown for a given molecule.",
  },
];

export function MethodologyPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Methodology</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">How a prediction is made</h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          This page summarises the pipeline behind every DrugSim prediction. It links to the
          project's full validation reports rather than repeating them — those documents
          contain the complete methodology, statistics, and audit trail.
        </p>
      </header>

      <ol className="flex flex-col gap-4">
        {STEPS.map((step, i) => (
          <li key={step.title} className="card p-5">
            <p className="font-mono text-xs text-ink-soft">
              {String(i + 1).padStart(2, "0")} / {STEPS.length}
            </p>
            <h2 className="mt-1 font-display text-lg font-semibold text-ink">{step.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-soft">{step.body}</p>
          </li>
        ))}
      </ol>

      <section className="rounded-lg border border-line bg-paper-alt p-6">
        <h2 className="font-display text-lg font-semibold text-ink">Full documentation</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Each model's development, validation, and reliability testing are documented in the
          project's phase reports: hERG model validation (Phase 3), scientific audit (Phase
          3.5), reliability and robustness testing (Phase 4), the prediction engine's API
          contract (Phase 5), and the CYP3A4 endpoint's own end-to-end evaluation (Phase 9).
          These are not duplicated here to avoid the two copies drifting out of sync.
        </p>
      </section>

      <p className="text-sm">
        <Link to="/limitations" className="underline underline-offset-2 hover:text-ink">
          Read the limitations and disclaimer →
        </Link>
      </p>
    </div>
  );
}
