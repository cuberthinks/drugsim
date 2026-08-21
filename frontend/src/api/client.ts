/**
 * Thin client for the Phase 5 prediction API. No prediction logic lives
 * here — every value shown in the UI comes from a response the backend
 * returned; this module only shapes fetch/error handling.
 *
 * Phase 8: VITE_API_KEY, if set at build time, is sent as X-API-Key on
 * every request. This is NOT a real secret once shipped -- anything baked
 * into a browser bundle is readable by anyone who opens dev tools. It
 * exists only to keep the frontend working against a backend that has
 * DRUGSIM_PREDICT_API_KEYS configured (see drugsim_predict.security),
 * which is itself a weak, "controlled demonstration" barrier against
 * casual/automated direct API access, not real authentication. A
 * deployment that needs a real access barrier for a small known audience
 * should put HTTP Basic Auth on the Caddy reverse proxy instead (see the
 * commented example in deployment/caddy/Caddyfile) so the browser's own
 * native auth prompt covers the whole site without embedding anything.
 */
import type { EndpointsResponse, ExplainabilityResponse, ModelDetail, PredictionResponse, ProblemDetail, StructureFormat } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";

// 20s, not the original 15s: a warm prediction returns in well under a
// second, so this ceiling only ever fires on a backend that is starting up
// (a container restart re-loads the model artifacts before serving), where
// 15s was tight enough to report a false failure for a request that would
// have succeeded.
const REQUEST_TIMEOUT_MS = 20_000;

// The hosted backend is restarted by its platform on every deploy and on
// routine platform events, and serves gateway errors for a few seconds
// either side of that. Without a retry those windows surface as "Could not
// reach the prediction service" -- indistinguishable, to someone using the
// app, from the service being broken. Retrying transient classes only
// (never a 4xx: a rejected structure or an exhausted quota is a real answer
// that will not change on a second attempt) converts those windows into a
// slightly slower success.
//
// Retrying POST /predict is safe despite not being formally idempotent: a
// prediction is deterministic for a given structure, and the only write is
// an append to the provenance audit log, where a duplicate row is
// harmless. Retries only happen when no response was received at all, or
// when the gateway (not the application) answered.
const MAX_ATTEMPTS = 3;
const RETRY_BASE_DELAY_MS = 700;

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

export type ApiErrorKind =
  | "validation" // 422 -- invalid chemistry or malformed request
  | "unauthorized" // 401 -- missing/invalid API key
  | "not_found" // 404 -- unknown resource, including an unrecognised endpoint name
  | "forbidden" // 403 -- a real, registered endpoint that hasn't passed the promotion gate
  | "rate_limited" // 429
  | "server_error" // 500
  | "unavailable" // 503, or health/ready failed
  | "network" // fetch itself failed (offline, DNS, connection refused)
  | "timeout";

export class ApiError extends Error {
  readonly kind: ApiErrorKind;
  readonly problem: ProblemDetail | null;
  readonly status: number | null;

  constructor(kind: ApiErrorKind, message: string, problem: ProblemDetail | null = null, status: number | null = null) {
    super(message);
    this.name = "ApiError";
    this.kind = kind;
    this.problem = problem;
    this.status = status;
  }
}

/** Error classes worth a second attempt -- see MAX_ATTEMPTS above. */
const RETRYABLE_KINDS: ReadonlySet<ApiErrorKind> = new Set<ApiErrorKind>(["network", "timeout", "unavailable"]);

async function attemptRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), REQUEST_TIMEOUT_MS);

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      ...init,
      signal: controller.signal,
      headers: {
        "Content-Type": "application/json",
        ...(API_KEY ? { "X-API-Key": API_KEY } : {}),
        ...init?.headers,
      },
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === "AbortError") {
      throw new ApiError("timeout", "The prediction service did not respond in time.");
    }
    throw new ApiError("network", "Could not reach the prediction service. It may be offline.");
  } finally {
    clearTimeout(timeout);
  }

  if (response.ok) {
    return (await response.json()) as T;
  }

  let problem: ProblemDetail | null = null;
  try {
    problem = (await response.json()) as ProblemDetail;
  } catch {
    // Non-JSON error body (e.g. a proxy/gateway error page) -- fall through
    // with problem left null; the caller still gets a correct `kind`.
  }

  if (response.status === 401) {
    throw new ApiError("unauthorized", problem?.detail ?? "A valid API key is required.", problem, response.status);
  }
  if (response.status === 404) {
    throw new ApiError("not_found", problem?.detail ?? "Not found.", problem, response.status);
  }
  if (response.status === 403) {
    throw new ApiError("forbidden", problem?.detail ?? "This endpoint is not available for predictions.", problem, response.status);
  }
  if (response.status === 422) {
    throw new ApiError("validation", problem?.detail ?? "The request was invalid.", problem, response.status);
  }
  if (response.status === 429) {
    throw new ApiError("rate_limited", problem?.detail ?? "Too many requests.", problem, response.status);
  }
  // 502/504 come from the hosting platform's gateway, not the application,
  // and mean "the backend is restarting or briefly unreachable" -- the same
  // transient condition as an application-level 503, so they are classed
  // together here and become retryable rather than a hard server_error.
  if (response.status === 502 || response.status === 503 || response.status === 504) {
    throw new ApiError("unavailable", problem?.detail ?? "The prediction service is temporarily unavailable.", problem, response.status);
  }
  throw new ApiError("server_error", problem?.detail ?? "An unexpected error occurred.", problem, response.status);
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  for (let attemptNo = 1; ; attemptNo++) {
    try {
      return await attemptRequest<T>(path, init);
    } catch (err) {
      const canRetry =
        attemptNo < MAX_ATTEMPTS && err instanceof ApiError && RETRYABLE_KINDS.has(err.kind);
      if (!canRetry) throw err;
      await sleep(RETRY_BASE_DELAY_MS * attemptNo);
    }
  }
}

export function predict(
  value: string,
  format: StructureFormat = "smiles",
  endpoint = "herg_inhibition",
): Promise<PredictionResponse> {
  return request<PredictionResponse>("/predict", {
    method: "POST",
    body: JSON.stringify({ structure: { format, value }, endpoint }),
  });
}

export function getPrediction(id: string): Promise<PredictionResponse> {
  return request<PredictionResponse>(`/predict/${encodeURIComponent(id)}`);
}

// Deliberately a separate call from predict(), never automatic: a full SHAP
// pass over a 200-500-tree ensemble costs ~55-200ms of backend CPU per call
// (measured), meaningfully more than a plain prediction -- only fetched when
// a user explicitly asks to see it (PredictionResults' "Show AI attention
// map" toggle), not on every result.
export function explainPrediction(
  value: string,
  format: StructureFormat = "smiles",
  endpoint = "herg_inhibition",
): Promise<ExplainabilityResponse> {
  return request<ExplainabilityResponse>("/predict/explain", {
    method: "POST",
    body: JSON.stringify({ structure: { format, value }, endpoint }),
  });
}

export function getModel(endpoint = "herg_inhibition"): Promise<ModelDetail> {
  return request<ModelDetail>(`/model?endpoint=${encodeURIComponent(endpoint)}`);
}

/**
 * Every registered endpoint and its promotion status (Phase 9 Sec 17) --
 * lets the UI distinguish available/experimental/unavailable up front
 * rather than discovering it from a failed prediction.
 */
export function getEndpoints(): Promise<EndpointsResponse> {
  return request<EndpointsResponse>("/endpoints");
}

export async function checkHealth(): Promise<boolean> {
  try {
    await request<{ status: string }>("/health");
    return true;
  } catch {
    return false;
  }
}
