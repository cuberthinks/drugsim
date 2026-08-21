import type { ExplainabilityResponse } from "../api/types";

const STORAGE_KEY = "drugsim_explanation_cache_v1";
const MAX_ENTRIES = 50;

interface CacheEntry {
  predictionId: string;
  cachedAt: string;
  data: ExplainabilityResponse;
}

/**
 * Retention for the AI attention map (Phase 11 follow-up): a SHAP
 * explanation costs real backend CPU (~55-200ms, see explainability.py) --
 * re-fetching the same molecule's explanation every time a user toggles
 * the panel, or revisits it from History, is pure waste. Keyed by
 * prediction ID (stable per PredictionResponse.id) rather than structure
 * text, so it can never be served for the wrong endpoint or a differently-
 * formatted equivalent structure.
 *
 * Client-side only, same rationale as lib/history.ts: no per-user backend
 * identity exists, so this is private to the browser by construction and
 * never sent anywhere -- not a second copy of anything the backend
 * tracks, purely a local performance cache.
 */
function readRaw(): CacheEntry[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    // Private browsing, storage disabled, or corrupted data -- this cache
    // is a convenience, never something an explanation should fail over.
    return [];
  }
}

function writeRaw(entries: CacheEntry[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // Storage full or disabled -- silently no-op rather than break the
    // explanation flow that triggered this save.
  }
}

export function getCachedExplanation(predictionId: string): ExplainabilityResponse | null {
  const entry = readRaw().find((e) => e.predictionId === predictionId);
  return entry?.data ?? null;
}

export function cacheExplanation(predictionId: string, data: ExplainabilityResponse): void {
  const existing = readRaw().filter((e) => e.predictionId !== predictionId);
  const next: CacheEntry[] = [{ predictionId, cachedAt: new Date().toISOString(), data }, ...existing].slice(
    0,
    MAX_ENTRIES,
  );
  writeRaw(next);
}

export function clearExplanationCache(): void {
  writeRaw([]);
}
