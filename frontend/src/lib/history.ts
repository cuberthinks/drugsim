import type { PredictionResponse } from "../api/types";
import { deriveReliabilityRating } from "./reliability";

const STORAGE_KEY = "drugsim_prediction_history_v1";
const MAX_ENTRIES = 50;

export interface HistoryEntry {
  id: string;
  timestamp: string;
  compoundName: string | null;
  endpoint: string;
  structure: string;
  predictedLabel: string;
  reliabilityRating: ReturnType<typeof deriveReliabilityRating>;
  applicabilityDomainVerdict: string;
  modelId: string;
  modelVersion: string;
}

/**
 * Client-side only, by design (Phase 10 yellow-improvement pass). The
 * backend has no per-user identity -- the API key is a single shared
 * secret, not real multi-tenant auth (documented since Phase 8) -- so a
 * server-side history would either mix every visitor's compounds together
 * or require new auth infrastructure this pass is not authorised to add.
 * localStorage sidesteps that entirely: nothing here is ever sent
 * anywhere, it is private to this browser by construction, and it
 * trivially satisfies "do not store confidential structures unnecessarily"
 * and "do not use private user compounds for model training" since the
 * backend never even learns this list exists.
 */
function readRaw(): HistoryEntry[] {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    // Private browsing, storage disabled, or corrupted data -- history is
    // a convenience feature, never something a prediction should fail over.
    return [];
  }
}

function writeRaw(entries: HistoryEntry[]): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(entries));
  } catch {
    // Storage full or disabled -- silently no-op rather than break the
    // prediction flow that triggered this save.
  }
}

export function getHistory(): HistoryEntry[] {
  return readRaw();
}

export function saveToHistory(
  prediction: PredictionResponse,
  compoundName: string,
  timestamp: string,
): void {
  const entry: HistoryEntry = {
    id: prediction.id,
    timestamp,
    compoundName: compoundName.trim() || null,
    endpoint: prediction.estimate.endpoint,
    structure: prediction.molecule.canonical_smiles,
    predictedLabel: prediction.estimate.predicted_label,
    reliabilityRating: deriveReliabilityRating(prediction.reliability),
    applicabilityDomainVerdict: prediction.reliability.applicability_domain.verdict,
    modelId: prediction.provenance.model_id,
    modelVersion: prediction.provenance.model_version,
  };
  const existing = readRaw().filter((e) => e.id !== entry.id);
  const next = [entry, ...existing].slice(0, MAX_ENTRIES);
  writeRaw(next);
}

export function removeFromHistory(id: string): void {
  writeRaw(readRaw().filter((e) => e.id !== id));
}

export function clearHistory(): void {
  writeRaw([]);
}
