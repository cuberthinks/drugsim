import { ApiError } from "../api/client";

interface Props {
  error: ApiError;
  onRetry?: () => void;
}

const COPY: Record<ApiError["kind"], { title: string; hint: string }> = {
  validation: {
    title: "This structure could not be processed",
    hint: "Check the input below and try again. The message above explains exactly what failed.",
  },
  unauthorized: {
    title: "This deployment requires access to be configured",
    hint: "The prediction service is not reachable from this page. This is a deployment configuration issue, not something you can fix by changing your input.",
  },
  not_found: {
    title: "Prediction not found",
    hint: "This prediction may have expired, or the link is incorrect.",
  },
  forbidden: {
    title: "This endpoint is not available for predictions",
    hint: "It is registered but has not passed the promotion gate for normal use yet. See the endpoints list for what's currently available.",
  },
  rate_limited: {
    title: "Too many requests",
    hint: "Please wait a moment before trying again.",
  },
  server_error: {
    title: "Something went wrong on our end",
    hint: "This is not a problem with your molecule. Please try again in a moment.",
  },
  unavailable: {
    title: "The prediction service is temporarily unavailable",
    hint: "The model could not be loaded. Please try again shortly.",
  },
  network: {
    title: "Could not reach the prediction service",
    hint: "Check your connection and try again.",
  },
  timeout: {
    title: "The request took too long",
    hint: "The prediction service did not respond in time. Please try again.",
  },
};

/** Renders a clear, honest failure state. Never shows a fabricated result. */
export function ErrorPanel({ error, onRetry }: Props) {
  const copy = COPY[error.kind];
  return (
    <div role="alert" className="rounded-lg border border-concern/40 bg-concern-soft p-6">
      <p className="font-medium text-concern">{copy.title}</p>
      <p className="mt-2 text-sm leading-relaxed text-ink-soft">{error.message}</p>
      <p className="mt-2 text-sm leading-relaxed text-ink-soft">{copy.hint}</p>
      {error.problem?.errors && error.problem.errors.length > 0 && (
        <ul className="mt-3 list-inside list-disc text-sm text-ink-soft">
          {error.problem.errors.map((e, i) => (
            <li key={i}>{e.message}</li>
          ))}
        </ul>
      )}
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-4 rounded-md border border-line bg-white px-4 py-2 text-sm font-medium text-ink hover:bg-paper-alt"
        >
          Try again
        </button>
      )}
    </div>
  );
}
