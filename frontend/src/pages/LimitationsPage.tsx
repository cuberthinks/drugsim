import { Link } from "react-router-dom";

const LIMITATIONS = [
  {
    title: "Computational predictions, not experimental results",
    body: "Every prediction is a model estimate derived from historical data. It is not a laboratory measurement of this molecule.",
  },
  {
    title: "Does not replace laboratory or animal testing",
    body: "DrugSim is intended to help prioritise which molecules might be worth testing next — not to substitute for in vitro laboratory assays or in vivo animal studies. It is a computational research and prioritisation aid, not a replacement for either.",
  },
  {
    title: "Does not establish clinical or biological safety",
    body: "A favourable prediction does not mean a compound is safe, and an unfavourable one does not mean it is dangerous. Neither conclusion is valid without experimental follow-up.",
  },
  {
    title: "Applicability domain limits reliability",
    body: "The model has more evidence for molecules that resemble its training chemistry. Predictions for novel or out-of-domain structures should be treated as extrapolations with reduced reliability.",
  },
  {
    title: "Each endpoint is independent, and the list is short",
    body: "DrugSim currently covers hERG inhibition and CYP3A4 inhibition, each validated separately. A prediction for one endpoint says nothing about any other ADMET property, efficacy, or safety endpoint — and the two are never combined into a single score or an overall verdict.",
  },
  {
    title: "CYP3A4 model: a known false-positive tendency",
    body: "On its own held-out test set, the CYP3A4 model's specificity is only 40.5% — a real, asymmetric tendency to label a compound an inhibitor when it is not. Treat a 'predicted inhibitor' result as a reason to look closer, not as strong evidence on its own.",
  },
  {
    title: "hERG model: no independent external validation",
    body: "Every reported hERG metric comes from held-out portions of its own training source, not a separate dataset — an external validation attempt was blocked by an unreachable data source during training. The CYP3A4 model does have an external validation result; the hERG model currently does not.",
  },
  {
    title: "The 10 µM active/inactive threshold is a screening convention",
    body: "Both models label a compound active (blocker/inhibitor) using a 10 µM cutoff on historical IC50 measurements. That threshold is a common literature convention for early screening, not a clinical or biological boundary — predictions near it are the least stable.",
  },
  {
    title: "Not a whole-body or whole-drug simulation",
    body: "DrugSim is a collection of validated computational predictions for specific, narrowly defined endpoints. It does not predict exact human pharmacokinetics, clinical safety, patient outcomes, therapeutic efficacy, or complete ADMET behaviour, and its endpoints are never implied to combine into a simulation of a whole organism.",
  },
];

export function LimitationsPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Limitations</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">
          What DrugSim does not tell you
        </h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          DrugSim is a research tool for internal use. Read this page before acting on any
          prediction it produces.
        </p>
      </header>

      <ul className="flex flex-col gap-4">
        {LIMITATIONS.map((item) => (
          <li key={item.title} className="rounded-lg border border-concern/30 bg-concern-soft p-5">
            <h2 className="font-medium text-ink">{item.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-ink-soft">{item.body}</p>
          </li>
        ))}
      </ul>

      <p className="text-sm">
        <Link to="/methodology" className="underline underline-offset-2 hover:text-ink">
          See how predictions are made →
        </Link>
      </p>
    </div>
  );
}
