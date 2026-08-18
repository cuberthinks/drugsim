import { useState } from "react";
import { Link } from "react-router-dom";
import { clearHistory, getHistory, removeFromHistory, type HistoryEntry } from "../lib/history";
import { getEndpointCopy, labelText } from "../lib/endpointCopy";

const RATING_COLOR: Record<HistoryEntry["reliabilityRating"], string> = {
  High: "var(--color-signal)",
  Moderate: "var(--color-caution)",
  Low: "var(--color-concern)",
};

function formatTimestamp(iso: string): string {
  try {
    return new Date(iso).toLocaleString(undefined, {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return iso;
  }
}

/**
 * A record of predictions run in THIS browser only (Phase 10 yellow-
 * improvement pass — see lib/history.ts for why this is client-side-only,
 * never sent to or readable by the backend). Nothing here is a new
 * scientific result; every field is exactly what the original prediction
 * already returned, at the time it was returned.
 */
export function HistoryPage() {
  const [entries, setEntries] = useState<HistoryEntry[]>(() => getHistory());

  function handleRemove(id: string) {
    removeFromHistory(id);
    setEntries(getHistory());
  }

  function handleClear() {
    clearHistory();
    setEntries([]);
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Your history</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">Prediction history</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Predictions you've run, kept only in this browser — never sent to or stored by DrugSim's
          server. Clearing your browser data, or clicking "Clear history" below, removes it
          permanently.
        </p>
      </header>

      {entries.length === 0 ? (
        <div className="rounded-lg border border-line bg-white p-6 text-sm text-ink-soft">
          No predictions saved yet.{" "}
          <Link to="/predict" className="underline underline-offset-2 hover:text-ink">
            Run one
          </Link>{" "}
          and it will appear here.
        </div>
      ) : (
        <>
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-ink-soft">
              {entries.length} saved prediction{entries.length === 1 ? "" : "s"} (up to 50 kept)
            </p>
            <div className="flex gap-4">
              {entries.length >= 2 && (
                <Link to="/compare" className="text-sm font-medium text-ink-soft underline underline-offset-2 hover:text-ink">
                  Compare two compounds
                </Link>
              )}
              <button
                type="button"
                onClick={handleClear}
                className="text-sm font-medium text-ink-soft underline underline-offset-2 hover:text-concern"
              >
                Clear history
              </button>
            </div>
          </div>

          <ul className="flex flex-col gap-3">
            {entries.map((entry) => {
              const copy = getEndpointCopy(entry.endpoint);
              return (
                <li key={entry.id} className="rounded-lg border border-line bg-white p-5">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div>
                      {entry.compoundName && <p className="text-sm font-medium text-ink">{entry.compoundName}</p>}
                      <p className="font-mono text-xs text-ink-soft break-all">{entry.structure}</p>
                      <p className="mt-1 text-xs text-ink-soft">{formatTimestamp(entry.timestamp)}</p>
                    </div>
                    <button
                      type="button"
                      onClick={() => handleRemove(entry.id)}
                      aria-label={`Remove ${entry.compoundName ?? entry.structure} from history`}
                      className="text-xs text-ink-soft underline underline-offset-2 hover:text-concern"
                    >
                      Remove
                    </button>
                  </div>
                  <dl className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-4">
                    <div>
                      <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Endpoint</dt>
                      <dd className="mt-1 text-sm text-ink">{copy.shortName}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Prediction</dt>
                      <dd className="mt-1 text-sm text-ink">{labelText(entry.endpoint, entry.predictedLabel)}</dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Reliability</dt>
                      <dd className="mt-1 text-sm font-medium" style={{ color: RATING_COLOR[entry.reliabilityRating] }}>
                        {entry.reliabilityRating}
                      </dd>
                    </div>
                    <div>
                      <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Applicability domain</dt>
                      <dd className="mt-1 text-sm text-ink">{entry.applicabilityDomainVerdict.replace(/_/g, " ")}</dd>
                    </div>
                  </dl>
                  <p className="mt-3 font-mono text-[11px] text-ink-soft">
                    Model {entry.modelId} v{entry.modelVersion}
                  </p>
                </li>
              );
            })}
          </ul>
        </>
      )}
    </div>
  );
}
