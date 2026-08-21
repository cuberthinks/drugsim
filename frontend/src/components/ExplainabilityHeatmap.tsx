import { useState } from "react";
import { ApiError, explainPrediction } from "../api/client";
import type { DescriptorContribution, ExplainabilityResponse, PredictionResponse } from "../api/types";
import { cacheExplanation, getCachedExplanation } from "../lib/explanationCache";
import { labelText } from "../lib/endpointCopy";
import { MoleculeStructure } from "./MoleculeStructure";

interface Props {
  prediction: PredictionResponse;
}

/** Must match drugsim_predict.explainability.EXPLAINABLE_MODEL_IDS exactly
 * -- kept as its own small set here (not fetched from the backend) so this
 * component can decide whether to render the toggle at all without an
 * extra request. CYP3A4 is deliberately excluded: its SHAP explainer
 * measured a ~280MB resident-memory jump and crashed the backend on a
 * 512MB instance the first time this feature was deployed. */
const EXPLAINABLE_ENDPOINTS = new Set(["herg_inhibition"]);

type FetchState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "error"; message: string }
  | { status: "done"; data: ExplainabilityResponse };

/** Human-readable labels for the model's raw descriptor field names.
 * Falls back to the raw name for anything not listed here, so a future
 * descriptor addition never renders as blank. */
const DESCRIPTOR_LABELS: Record<string, string> = {
  mw_g_mol: "Molecular weight",
  exact_mass_g_mol: "Exact mass",
  logp_crippen: "LogP",
  molar_refractivity: "Molar refractivity",
  tpsa_a2: "Polar surface area",
  rotatable_bonds: "Rotatable bonds",
  aromatic_rings: "Aromatic rings",
  ring_count: "Ring count",
  heavy_atom_count: "Heavy atom count",
  formal_charge: "Formal charge",
  hbd_lipinski: "H-bond donors (Lipinski)",
  hba_lipinski: "H-bond acceptors (Lipinski)",
  hbd_strict: "H-bond donors (strict)",
  hba_strict: "H-bond acceptors (strict)",
  heteroatom_count: "Heteroatom count",
  fraction_csp3: "Fraction sp3 carbons",
  num_stereocentres: "Stereocentres",
  largest_ring_size: "Largest ring size",
};

const TOP_DESCRIPTOR_COUNT = 4;

function topDescriptors(descriptors: DescriptorContribution[]): DescriptorContribution[] {
  return [...descriptors].sort((a, b) => Math.abs(b.contribution) - Math.abs(a.contribution)).slice(0, TOP_DESCRIPTOR_COUNT);
}

/** Atom-index order is guaranteed contiguous 0..N-1 by the backend (see
 * explainability.py's tests) -- sorting defensively rather than assuming
 * response-array order is enough on its own. */
function toWeightsArray(data: ExplainabilityResponse): number[] {
  return [...data.atom_contributions].sort((a, b) => a.atom_index - b.atom_index).map((a) => a.contribution);
}

export function ExplainabilityHeatmap({ prediction }: Props) {
  const [open, setOpen] = useState(false);
  const [state, setState] = useState<FetchState>(() => {
    const cached = getCachedExplanation(prediction.id);
    return cached ? { status: "done", data: cached } : { status: "idle" };
  });

  if (!EXPLAINABLE_ENDPOINTS.has(prediction.estimate.endpoint)) {
    // Not offered yet for this endpoint (see EXPLAINABLE_ENDPOINTS above) --
    // omitted entirely rather than shown disabled, so there is nothing to
    // explain about why a button doesn't work.
    return null;
  }

  async function handleToggle() {
    const next = !open;
    setOpen(next);
    if (next && state.status !== "done" && state.status !== "loading") {
      setState({ status: "loading" });
      try {
        const data = await explainPrediction(prediction.molecule.standardized_smiles, "smiles", prediction.estimate.endpoint);
        cacheExplanation(prediction.id, data);
        setState({ status: "done", data });
      } catch (err) {
        const message = err instanceof ApiError ? err.message : "Could not compute an explanation for this structure.";
        setState({ status: "error", message });
      }
    }
  }

  return (
    <div className="rounded-lg border border-line bg-white p-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <h3 className="text-sm font-medium text-ink">AI attention map</h3>
          <p className="mt-1 text-xs leading-relaxed text-ink-soft">
            Which atoms and properties pushed this specific prediction toward or away from{" "}
            {labelText(prediction.estimate.endpoint, "blocker")}. Computed on demand (SHAP over the trained model) —
            not part of the prediction above, and not a new measurement.
          </p>
        </div>
        <button
          type="button"
          onClick={handleToggle}
          aria-pressed={open}
          className={`shrink-0 rounded-md border px-4 py-2 text-sm font-medium ${
            open ? "border-ink bg-ink text-paper" : "border-line bg-white text-ink hover:bg-paper-alt"
          }`}
        >
          {open ? "Hide attention map" : "Show attention map"}
        </button>
      </div>

      {open && state.status === "loading" && (
        <p className="mt-4 text-sm text-ink-soft">Computing explanation…</p>
      )}

      {open && state.status === "error" && (
        <p className="mt-4 rounded-md border border-concern/40 bg-concern-soft px-4 py-3 text-sm text-concern">
          {state.message}
        </p>
      )}

      {open && state.status === "done" && (
        <ExplanationBody prediction={prediction} data={state.data} />
      )}
    </div>
  );
}

function ExplanationBody({ prediction, data }: { prediction: PredictionResponse; data: ExplainabilityResponse }) {
  const weights = toWeightsArray(data);
  const descriptors = topDescriptors(data.descriptor_contributions);
  const hasAbsentContribution = Math.abs(data.absent_substructure_contribution) > 0.005;

  return (
    <div className="mt-5 flex flex-col gap-5">
      <div className="flex flex-col items-center gap-3">
        <MoleculeStructure
          smiles={prediction.molecule.standardized_smiles}
          weights={weights}
          label={`Attention map for ${prediction.molecule.canonical_smiles}: red atoms push toward ${data.positive_class_label}, teal atoms push away from it`}
        />
        <div className="flex items-center gap-4 text-xs text-ink-soft">
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: "#8b3a3a" }} aria-hidden="true" />
            Pushes toward {data.positive_class_label}
          </span>
          <span className="flex items-center gap-1.5">
            <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ backgroundColor: "#1c6e6e" }} aria-hidden="true" />
            Pushes away from {data.positive_class_label}
          </span>
        </div>
      </div>

      <div>
        <p className="text-xs font-medium tracking-wide text-ink-soft uppercase">Largest property contributions</p>
        <ul className="mt-2 flex flex-col gap-1.5">
          {descriptors.map((d) => (
            <li key={d.name} className="flex items-center justify-between gap-3 text-sm">
              <span className="text-ink">{DESCRIPTOR_LABELS[d.name] ?? d.name}</span>
              <span
                className="font-mono text-xs"
                style={{ color: d.contribution >= 0 ? "#8b3a3a" : "#1c6e6e" }}
              >
                {d.contribution >= 0 ? "+" : ""}
                {d.contribution.toFixed(3)}
              </span>
            </li>
          ))}
        </ul>
      </div>

      {hasAbsentContribution && (
        <p className="text-xs leading-relaxed text-ink-soft">
          Part of this prediction ({data.absent_substructure_contribution >= 0 ? "+" : ""}
          {data.absent_substructure_contribution.toFixed(3)}) is explained by chemistry this molecule does{" "}
          <strong>not</strong> contain — a substructure's absence can be real evidence too, but there is no atom to
          highlight for something that isn't there.
        </p>
      )}

      <p className="text-xs leading-relaxed text-ink-soft">
        This shows what drove the model's own output, not what is biologically true. An atom highlighted here is
        correlated with the outcome in the training data — it is not a claim about mechanism.
      </p>
    </div>
  );
}
