import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { clearHistory, getHistory, removeFromHistory, saveToHistory } from "./history";
import { makePrediction } from "../test/fixtures";

describe("prediction history (client-side only)", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("starts empty", () => {
    expect(getHistory()).toEqual([]);
  });

  it("saves a completed prediction with the fields a review page needs", () => {
    const prediction = makePrediction();
    saveToHistory(prediction, "Aspirin", "2026-01-01T00:00:00Z");

    const [entry] = getHistory();
    expect(entry).toMatchObject({
      id: prediction.id,
      compoundName: "Aspirin",
      endpoint: prediction.estimate.endpoint,
      structure: prediction.molecule.canonical_smiles,
      predictedLabel: prediction.estimate.predicted_label,
      modelId: prediction.provenance.model_id,
      modelVersion: prediction.provenance.model_version,
    });
  });

  it("stores no name as null, never an empty string, when the user didn't provide one", () => {
    saveToHistory(makePrediction(), "   ", "2026-01-01T00:00:00Z");
    expect(getHistory()[0].compoundName).toBeNull();
  });

  it("orders most-recent first", () => {
    saveToHistory(makePrediction({ id: "first" }), "", "2026-01-01T00:00:00Z");
    saveToHistory(makePrediction({ id: "second" }), "", "2026-01-02T00:00:00Z");
    expect(getHistory().map((e) => e.id)).toEqual(["second", "first"]);
  });

  it("replaces an existing entry with the same prediction id rather than duplicating it", () => {
    saveToHistory(makePrediction({ id: "same" }), "First name", "2026-01-01T00:00:00Z");
    saveToHistory(makePrediction({ id: "same" }), "Updated name", "2026-01-02T00:00:00Z");
    const entries = getHistory();
    expect(entries).toHaveLength(1);
    expect(entries[0].compoundName).toBe("Updated name");
  });

  it("caps stored history at 50 entries, keeping the most recent", () => {
    for (let i = 0; i < 55; i++) {
      saveToHistory(makePrediction({ id: `p${i}` }), "", `2026-01-01T00:00:${String(i).padStart(2, "0")}Z`);
    }
    const entries = getHistory();
    expect(entries).toHaveLength(50);
    expect(entries[0].id).toBe("p54");
    expect(entries.find((e) => e.id === "p0")).toBeUndefined();
  });

  it("removes a single entry by id", () => {
    saveToHistory(makePrediction({ id: "keep" }), "", "2026-01-01T00:00:00Z");
    saveToHistory(makePrediction({ id: "drop" }), "", "2026-01-02T00:00:00Z");
    removeFromHistory("drop");
    expect(getHistory().map((e) => e.id)).toEqual(["keep"]);
  });

  it("clears everything", () => {
    saveToHistory(makePrediction(), "", "2026-01-01T00:00:00Z");
    clearHistory();
    expect(getHistory()).toEqual([]);
  });

  it("never throws if localStorage is unavailable (private browsing, quota exceeded)", () => {
    const spy = vi.spyOn(window.localStorage, "setItem").mockImplementation(() => {
      throw new DOMException("QuotaExceededError");
    });
    expect(() => saveToHistory(makePrediction(), "", "2026-01-01T00:00:00Z")).not.toThrow();
    spy.mockRestore();
  });

  it("never throws and returns an empty list if stored data is corrupted", () => {
    window.localStorage.setItem("drugsim_prediction_history_v1", "{not valid json");
    expect(getHistory()).toEqual([]);
  });
});
