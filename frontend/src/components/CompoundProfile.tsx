import { useEffect, useState } from "react";
import { ApiError, predict } from "../api/client";
import type { EndpointListItem, PredictionResponse } from "../api/types";
import { EndpointProfileCard } from "./EndpointProfileCard";

type CardState =
  | { status: "loading" }
  | { status: "error"; error: ApiError }
  | { status: "done"; prediction: PredictionResponse };

interface Props {
  structureValue: string;
  endpoints: EndpointListItem[];
  /** User-supplied label (e.g. "Aspirin") -- display only, never sent to or
   * returned by the backend; every prediction below is unaffected by it. */
  compoundName?: string;
}

/**
 * The DrugSim Compound Profile (Phase 10 Sec 7): one molecule, every
 * VALIDATED endpoint it has, grouped by category (Absorption/Distribution/
 * Metabolism/Toxicity — whichever categories actually have an approved
 * endpoint; a category with none simply does not appear).
 *
 * Deliberately NOT a single combined "DrugSim Score" (Phase 10 Sec 7/18):
 * each endpoint's card stands alone with its own prediction, uncertainty,
 * and reliability. hERG inhibition and CYP3A4 inhibition are unrelated
 * biological mechanisms; averaging or otherwise combining them into one
 * number would imply a relationship the science does not support.
 *
 * Runs one prediction per servable endpoint in parallel. A failure on one
 * endpoint never hides or fabricates a result for another -- each card
 * reports its own outcome independently (Promise.allSettled, not
 * Promise.all, specifically so one rejection cannot blank the whole page).
 */
export function CompoundProfile({ structureValue, endpoints, compoundName }: Props) {
  const [cardStates, setCardStates] = useState<Record<string, CardState>>({});

  useEffect(() => {
    const servable = endpoints.filter((e) => e.servable);
    setCardStates(Object.fromEntries(servable.map((e) => [e.model_id, { status: "loading" } as CardState])));

    let cancelled = false;
    for (const endpoint of servable) {
      predict(structureValue, "smiles", endpoint.model_id)
        .then((prediction) => {
          if (!cancelled) setCardStates((prev) => ({ ...prev, [endpoint.model_id]: { status: "done", prediction } }));
        })
        .catch((err) => {
          if (cancelled) return;
          const error = err instanceof ApiError ? err : new ApiError("network", "Something went wrong.");
          setCardStates((prev) => ({ ...prev, [endpoint.model_id]: { status: "error", error } }));
        });
    }
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [structureValue, endpoints.map((e) => e.model_id).join(",")]);

  const servable = endpoints.filter((e) => e.servable);
  const categories = Array.from(new Set(servable.map((e) => e.category ?? "Other")));

  return (
    <section aria-labelledby="compound-profile-heading" className="flex flex-col gap-6">
      <div>
        <p className="text-xs font-medium tracking-wide text-ink-soft uppercase">DrugSim Compound Profile</p>
        <h2 id="compound-profile-heading" className="mt-1 font-display text-2xl font-semibold text-ink">
          Every validated endpoint for {compoundName?.trim() ? compoundName.trim() : "this molecule"}
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Only endpoints that have passed the promotion gate are shown. There is no combined
          "DrugSim score" — each property below is a separate, independently validated
          prediction with its own uncertainty and reliability.
        </p>
      </div>

      {categories.map((category) => (
        <div key={category}>
          <h3 className="text-xs font-semibold tracking-wide text-ink-soft uppercase">{category}</h3>
          <div className="mt-3 grid gap-4 md:grid-cols-2">
            {servable
              .filter((e) => (e.category ?? "Other") === category)
              .map((endpoint) => (
                <EndpointProfileCard
                  key={endpoint.model_id}
                  endpoint={endpoint}
                  state={cardStates[endpoint.model_id] ?? { status: "loading" }}
                />
              ))}
          </div>
        </div>
      ))}

      {servable.length === 0 && (
        <p className="text-sm text-ink-soft">No validated endpoints are currently available.</p>
      )}
    </section>
  );
}
