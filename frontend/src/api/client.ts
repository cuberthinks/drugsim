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
import type { EndpointsResponse, ModelDetail, PredictionResponse, ProblemDetail, StructureFormat } from "./types";

const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "/api";
const API_KEY = import.meta.env.VITE_API_KEY ?? "";
const REQUEST_TIMEOUT_MS = 15_000;

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

async function request<T>(path: string, init?: RequestInit): Promise<T> {
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
  if (response.status === 503) {
    throw new ApiError("unavailable", problem?.detail ?? "The prediction service is temporarily unavailable.", problem, response.status);
  }
  throw new ApiError("server_error", problem?.detail ?? "An unexpected error occurred.", problem, response.status);
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
