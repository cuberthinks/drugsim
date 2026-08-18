import { useEffect, useState } from "react";
import { ApiError, getEndpoints, predict } from "../api/client";
import type { EndpointListItem, PredictionResponse } from "../api/types";
import { CompoundProfile } from "../components/CompoundProfile";
import { EndpointSelector } from "../components/EndpointSelector";
import { ErrorPanel } from "../components/ErrorPanel";
import { MoleculeInput } from "../components/MoleculeInput";
import { MoleculePreview } from "../components/MoleculePreview";
import { PredictionResults } from "../components/PredictionResults";
import { getEndpointCopy } from "../lib/endpointCopy";

type Stage = "idle" | "validating" | "validated" | "predicting" | "complete";
type ViewMode = "single" | "profile";

const DEFAULT_ENDPOINT = "herg_inhibition";

export function PredictPage() {
  const [value, setValue] = useState("");
  const [stage, setStage] = useState<Stage>("idle");
  const [prediction, setPrediction] = useState<PredictionResponse | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  const [endpoints, setEndpoints] = useState<EndpointListItem[]>([]);
  const [selectedEndpoint, setSelectedEndpoint] = useState(DEFAULT_ENDPOINT);
  const [viewMode, setViewMode] = useState<ViewMode>("single");
  // Purely a display label the user can attach to their own submission (e.g.
  // "Aspirin") -- never sent to the API, never affects the prediction. See
  // MoleculeInput's own note to the user for the same disclosure.
  const [compoundName, setCompoundName] = useState("");

  // Endpoint discovery is best-effort: if it fails, the page still works
  // exactly as it did before Phase 9 -- a single, implicit hERG endpoint,
  // with no selector shown (EndpointSelector renders nothing for an empty list).
  useEffect(() => {
    getEndpoints()
      .then((res) => setEndpoints(res.endpoints))
      .catch(() => setEndpoints([]));
  }, []);

  function handleChange(next: string) {
    setValue(next);
    setStage("idle");
    setPrediction(null);
    setError(null);
    setViewMode("single");
  }

  function handleClear() {
    setValue("");
    setCompoundName("");
    setStage("idle");
    setPrediction(null);
    setError(null);
    setViewMode("single");
  }

  function handleSelectEndpoint(modelId: string) {
    setSelectedEndpoint(modelId);
    setStage("idle");
    setPrediction(null);
    setError(null);
  }

  // The Phase 5 API exposes no standalone "validate" endpoint — validation
  // and prediction happen in a single /predict call. "Validate" runs that
  // call and shows the resulting molecule preview without yet foregrounding
  // the prediction, giving the two-step UX the spec asks for without
  // inventing a backend capability that doesn't exist.
  async function runPredictOrValidate(nextStage: "validated" | "complete") {
    // What was on screen before this run started. A failure must fall back
    // to exactly that, never to "idle": the results below are gated on
    // stage, so resetting it discarded a result the user was still reading
    // and forced them to re-run the whole request to see it again. The
    // prediction itself was never cleared -- only the stage that displays
    // it -- so restoring the stage is all that is needed.
    const stageBeforeRun = stage;
    setStage(nextStage === "validated" ? "validating" : "predicting");
    setError(null);
    try {
      const result = await predict(value.trim(), "smiles", selectedEndpoint);
      setPrediction(result);
      setStage(nextStage);
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError("network", "Something went wrong."));
      setStage(stageBeforeRun === "validated" || stageBeforeRun === "complete" ? stageBeforeRun : "idle");
    }
  }

  const isBusy = stage === "validating" || stage === "predicting";
  const endpointCopy = getEndpointCopy(selectedEndpoint);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Prediction workspace</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">{endpointCopy.displayName} prediction</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Enter a molecule as SMILES, validate the structure, then run the prediction. Every
          result below is returned directly by the DrugSim prediction engine.
        </p>
      </header>

      <ol className="grid gap-4 sm:grid-cols-3" aria-label="How this works">
        {[
          { step: "Enter a molecule", detail: "Paste a SMILES string, or use the example." },
          { step: "Run a prediction", detail: "Validate the structure, then predict." },
          { step: "Review prediction + reliability", detail: "Read the result together with its uncertainty and applicability domain." },
        ].map(({ step, detail }, i) => (
          <li key={step} className="rounded-lg border border-line bg-paper-alt p-4">
            <p className="font-mono text-xs text-ink-soft">{i + 1}</p>
            <p className="mt-1 text-sm font-medium text-ink">{step}</p>
            <p className="mt-1 text-xs leading-relaxed text-ink-soft">{detail}</p>
          </li>
        ))}
      </ol>

      <EndpointSelector
        endpoints={endpoints}
        selected={selectedEndpoint}
        onSelect={handleSelectEndpoint}
        isBusy={isBusy}
      />

      <MoleculeInput
        value={value}
        onChange={handleChange}
        name={compoundName}
        onNameChange={setCompoundName}
        onValidate={() => runPredictOrValidate("validated")}
        onPredict={() => runPredictOrValidate("complete")}
        onClear={handleClear}
        isBusy={isBusy}
        isValidated={stage === "validated" || stage === "complete"}
        predictLabel={`Predict ${endpointCopy.shortName}`}
      />

      {error && (
        <ErrorPanel
          error={error}
          onRetry={() => runPredictOrValidate(stage === "complete" ? "complete" : "validated")}
        />
      )}

      {error && prediction && (stage === "validated" || stage === "complete") && (
        <p className="text-sm leading-relaxed text-ink-soft">
          The result below is from your last successful run. The failed request above did not
          change it.
        </p>
      )}

      {prediction && (stage === "validated" || stage === "complete") && (
        <>
          <MoleculePreview molecule={prediction.molecule} name={compoundName} />
          {endpoints.filter((e) => e.servable).length > 1 && (
            <div className="flex flex-wrap gap-3">
              <button
                type="button"
                onClick={() => setViewMode("single")}
                aria-pressed={viewMode === "single"}
                className={`rounded-md border px-4 py-2 text-sm font-medium ${viewMode === "single" ? "border-ink bg-ink text-paper" : "border-line bg-white text-ink hover:bg-paper-alt"}`}
              >
                Single endpoint
              </button>
              <button
                type="button"
                onClick={() => setViewMode("profile")}
                aria-pressed={viewMode === "profile"}
                className={`rounded-md border px-4 py-2 text-sm font-medium ${viewMode === "profile" ? "border-ink bg-ink text-paper" : "border-line bg-white text-ink hover:bg-paper-alt"}`}
              >
                Full compound profile ({endpoints.filter((e) => e.servable).length} endpoints)
              </button>
            </div>
          )}
        </>
      )}

      {prediction && viewMode === "profile" && (
        <CompoundProfile structureValue={value.trim()} endpoints={endpoints} compoundName={compoundName} />
      )}

      {prediction && stage === "complete" && viewMode === "single" && (
        <PredictionResults prediction={prediction} compoundName={compoundName} />
      )}
    </div>
  );
}
