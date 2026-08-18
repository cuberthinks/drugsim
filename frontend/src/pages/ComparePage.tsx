import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { getHistory, type HistoryEntry } from "../lib/history";
import { getEndpointCopy, labelText } from "../lib/endpointCopy";

const RATING_COLOR: Record<HistoryEntry["reliabilityRating"], string> = {
  High: "var(--color-signal)",
  Moderate: "var(--color-caution)",
  Low: "var(--color-concern)",
};

function entryLabel(e: HistoryEntry): string {
  return e.compoundName ?? e.structure;
}

/**
 * Compares two of the user's OWN previously analysed compounds (from
 * client-side history — see lib/history.ts), restricted to the same
 * endpoint so the comparison is scientifically meaningful (Phase 10
 * yellow-improvement pass, section 4: "compare only scientifically
 * compatible information"). Deliberately has no combined "better drug"
 * score — each endpoint's prediction, uncertainty, and applicability
 * domain are shown side by side, exactly as returned, never merged into
 * one number (same rule this project already applies within a single
 * compound's own multiple endpoints).
 */
export function ComparePage() {
  const history = useMemo(() => getHistory(), []);
  const [endpoint, setEndpoint] = useState<string | null>(() => history[0]?.endpoint ?? null);
  const [leftId, setLeftId] = useState<string | null>(null);
  const [rightId, setRightId] = useState<string | null>(null);

  const endpoints = useMemo(() => Array.from(new Set(history.map((e) => e.endpoint))), [history]);
  const candidates = useMemo(
    () => history.filter((e) => e.endpoint === endpoint),
    [history, endpoint],
  );
  const left = candidates.find((e) => e.id === leftId) ?? null;
  const right = candidates.find((e) => e.id === rightId) ?? null;

  if (history.length < 2) {
    return (
      <div className="mx-auto flex max-w-3xl flex-col gap-4 px-6 py-12">
        <header>
          <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Compare</p>
          <h1 className="mt-1 font-display text-3xl font-semibold text-ink">Compound comparison</h1>
        </header>
        <div className="rounded-lg border border-line bg-white p-6 text-sm text-ink-soft">
          Run at least two predictions to compare them.{" "}
          <Link to="/predict" className="underline underline-offset-2 hover:text-ink">
            Run a prediction
          </Link>
          , or see your{" "}
          <Link to="/history" className="underline underline-offset-2 hover:text-ink">
            existing history
          </Link>
          .
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Compare</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">Compound comparison</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Compares two of your own previously analysed compounds on the same endpoint, side by
          side. There is no combined score — each compound's prediction, uncertainty, and
          applicability domain are shown exactly as returned.
        </p>
      </header>

      {endpoints.length > 1 && (
        <div>
          <label htmlFor="compare-endpoint" className="text-sm font-medium text-ink">
            Endpoint
          </label>
          <select
            id="compare-endpoint"
            value={endpoint ?? ""}
            onChange={(e) => {
              setEndpoint(e.target.value);
              setLeftId(null);
              setRightId(null);
            }}
            className="mt-2 w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink"
          >
            {endpoints.map((ep) => (
              <option key={ep} value={ep}>
                {getEndpointCopy(ep).shortName}
              </option>
            ))}
          </select>
        </div>
      )}

      {candidates.length < 2 ? (
        <p className="text-sm text-ink-soft">
          You need at least two predictions for this endpoint to compare them.
        </p>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2">
          {[
            { id: leftId, setId: setLeftId, label: "Compound A" },
            { id: rightId, setId: setRightId, label: "Compound B" },
          ].map(({ id, setId, label }) => (
            <div key={label}>
              <label htmlFor={`compare-${label}`} className="text-sm font-medium text-ink">
                {label}
              </label>
              <select
                id={`compare-${label}`}
                value={id ?? ""}
                onChange={(e) => setId(e.target.value || null)}
                className="mt-2 w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink"
              >
                <option value="">Choose a compound…</option>
                {candidates.map((c) => (
                  <option key={c.id} value={c.id}>
                    {entryLabel(c)} — {new Date(c.timestamp).toLocaleDateString()}
                  </option>
                ))}
              </select>
            </div>
          ))}
        </div>
      )}

      {left && right && (
        <div className="grid gap-4 sm:grid-cols-2">
          {[left, right].map((entry) => (
            <div key={entry.id} className="rounded-lg border border-line bg-white p-5">
              <p className="text-sm font-medium text-ink">{entryLabel(entry)}</p>
              <p className="mt-1 font-mono text-xs text-ink-soft break-all">{entry.structure}</p>
              <dl className="mt-4 flex flex-col gap-3">
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
                <div>
                  <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Model</dt>
                  <dd className="mt-1 font-mono text-xs text-ink-soft">
                    {entry.modelId} v{entry.modelVersion}
                  </dd>
                </div>
              </dl>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
