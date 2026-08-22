import type { EndpointListItem } from "../api/types";

interface Props {
  endpoints: EndpointListItem[];
  selected: string;
  onSelect: (modelId: string) => void;
  isBusy: boolean;
}

/**
 * Phase 9 Sec 17: distinguishes available (servable) endpoints from
 * experimental/unavailable ones, using exactly the promotion status the
 * backend registry reports -- never a placeholder or an invented status.
 * An endpoint that hasn't passed the promotion gate is shown, disabled,
 * with its real status as the reason, rather than hidden or silently
 * offered as if it produced normal predictions.
 */
export function EndpointSelector({ endpoints, selected, onSelect, isBusy }: Props) {
  if (endpoints.length === 0) return null;

  return (
    <div className="card p-6">
      <p className="text-sm font-medium text-ink">Endpoint</p>
      <p className="mt-1 text-xs leading-relaxed text-ink-soft">
        Choose which validated endpoint to run. Only endpoints that have passed the promotion gate
        can produce a prediction.
      </p>
      <div className="mt-3 flex flex-col gap-2 sm:flex-row sm:flex-wrap">
        {endpoints.map((endpoint) => {
          const isSelected = endpoint.model_id === selected;
          return (
            <button
              key={endpoint.model_id}
              type="button"
              disabled={isBusy || !endpoint.servable}
              onClick={() => onSelect(endpoint.model_id)}
              title={!endpoint.servable ? `Status: ${endpoint.final_report_status} — not available for predictions` : undefined}
              className={`flex flex-1 flex-col items-start gap-1 rounded-md border px-4 py-2.5 text-left text-sm shadow-sm transition-[border-color,box-shadow,transform] duration-200 active:scale-[0.98] disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 disabled:hover:shadow-sm disabled:active:scale-100 ${
                isSelected
                  ? "border-ink bg-ink text-paper"
                  : "border-line bg-white text-ink hover:-translate-y-0.5 hover:border-signal hover:bg-signal-soft hover:shadow-md"
              }`}
            >
              <span className="font-medium">{endpoint.endpoint_name}</span>
              <span
                className={`font-mono text-[11px] uppercase tracking-wide ${
                  isSelected ? "text-paper/70" : endpoint.servable ? "text-ink-soft" : "text-concern"
                }`}
              >
                {endpoint.servable ? "Available" : endpoint.final_report_status}
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}
