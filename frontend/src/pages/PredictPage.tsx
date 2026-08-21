import { useEffect, useState } from "react";
import { ApiError, getEndpoints, predict } from "../api/client";
import type { EndpointListItem, PredictionResponse } from "../api/types";
import { CompoundProfile } from "../components/CompoundProfile";
import { EndpointSelector } from "../components/EndpointSelector";
import { ErrorPanel } from "../components/ErrorPanel";
import { HowThisWorksGuide } from "../components/HowThisWorksGuide";
import { MoleculeInput } from "../components/MoleculeInput";
import { MoleculePreview } from "../components/MoleculePreview";
import { PredictionResults } from "../components/PredictionResults";
import { getEndpointCopy } from "../lib/endpointCopy";
import type { ExampleCompound } from "../lib/exampleCompounds";
import { saveToHistory } from "../lib/history";

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
  //
  // `overrides` exists only for handleUseExample below: setValue/
  // setCompoundName are async (React batches state updates), so a call
  // made immediately afterward would otherwise still read the OLD value
  // from this closure. Passing the real value explicitly sidesteps that
  // race rather than relying on a stale read.
  async function runPredictOrValidate(
    nextStage: "validated" | "complete",
    overrides?: { structure?: string; name?: string },
  ) {
    const structureValue = overrides?.structure ?? value.trim();
    const nameValue = overrides?.name ?? compoundName;
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
      const result = await predict(structureValue, "smiles", selectedEndpoint);
      setPrediction(result);
      setStage(nextStage);
      // Only a completed prediction, not a validation preview, is worth
      // remembering -- see lib/history.ts for why this never leaves the
      // browser.
      if (nextStage === "complete") {
        saveToHistory(result, nameValue, new Date().toISOString());
      }
    } catch (err) {
      setError(err instanceof ApiError ? err : new ApiError("network", "Something went wrong."));
      setStage(stageBeforeRun === "validated" || stageBeforeRun === "complete" ? stageBeforeRun : "idle");
    }
  }

  // Fills the example's structure/name and immediately runs a real
  // prediction against the live model -- one genuine API call, the same
  // request "Predict" itself makes, not a cached or precomputed result
  // (user preference, confirmed explicitly: examples must always reflect
  // the currently deployed model, never go stale if it's ever updated).
  function handleUseExample(example: ExampleCompound) {
    const nextName = compoundName.trim() ? compoundName : example.name;
    setValue(example.smiles);
    if (!compoundName.trim()) setCompoundName(example.name);
    setViewMode("single");
    runPredictOrValidate("complete", { structure: example.smiles, name: nextName });
  }

  const isBusy = stage === "validating" || stage === "predicting";
  const endpointCopy = getEndpointCopy(selectedEndpoint);

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Prediction workspace</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">{endpointCopy.displayName} prediction</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Every result below is returned directly by the DrugSim prediction engine — nothing here
          is simulated or cached.
        </p>
      </header>

      <HowThisWorksGuide />

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
        onUseExample={handleUseExample}
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
