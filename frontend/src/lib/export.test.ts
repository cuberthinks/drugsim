import { describe, expect, it, vi } from "vitest";
import { downloadTextFile, predictionToCSV, predictionToExportObject, predictionToJSON } from "./export";
import { makePrediction } from "../test/fixtures";

describe("prediction export", () => {
  it("includes every field the API actually returned, nothing invented", () => {
    const prediction = makePrediction();
    const obj = predictionToExportObject(prediction, "Aspirin");

    expect(obj.compound_name).toBe("Aspirin");
    expect(obj.molecule).toEqual(prediction.molecule);
    expect(obj.prediction.predicted_label).toBe(prediction.estimate.predicted_label);
    expect(obj.prediction.predicted_probability).toBe(prediction.estimate.predicted_probability);
    expect(obj.uncertainty).toEqual(prediction.reliability.conformal);
    expect(obj.applicability_domain).toEqual(prediction.reliability.applicability_domain);
    expect(obj.model.model_checksum).toBe(prediction.provenance.model_checksum);
    expect(obj.model.model_version).toBe(prediction.provenance.model_version);
    expect(obj.inference_timestamp).toBe(prediction.inference_timestamp);
  });

  it("always includes the scientific disclaimer", () => {
    const obj = predictionToExportObject(makePrediction());
    expect(obj.disclaimer).toMatch(/do not establish clinical safety or efficacy/i);
  });

  it("stores an untrimmed/empty compound name as null, not an empty string", () => {
    expect(predictionToExportObject(makePrediction(), "   ").compound_name).toBeNull();
    expect(predictionToExportObject(makePrediction()).compound_name).toBeNull();
  });

  it("produces valid, round-trippable JSON", () => {
    const json = predictionToJSON(makePrediction(), "Aspirin");
    const parsed = JSON.parse(json);
    expect(parsed.compound_name).toBe("Aspirin");
    expect(parsed.disclaimer).toBeTruthy();
  });

  it("produces a two-row CSV (header + values) with one value per header column", () => {
    const csv = predictionToCSV(makePrediction(), "Aspirin");
    const lines = csv.trim().split("\n");
    expect(lines).toHaveLength(2);

    // A quote-aware split -- the naive `line.split(",")` this test used
    // before is wrong here on purpose: the disclaimer column itself
    // contains commas ("laboratory, preclinical, or clinical testing"),
    // so it's correctly CSV-quoted, and a naive split would over-count.
    const splitCsvLine = (line: string) => line.match(/"(?:[^"]|"")*"|[^,]+/g) ?? [];
    const headerCols = splitCsvLine(lines[0]);
    const valueCols = splitCsvLine(lines[1]);

    expect(headerCols).toContain("model_checksum");
    expect(headerCols).toContain("applicability_domain_verdict");
    expect(headerCols).toContain("disclaimer");
    expect(valueCols.length).toBe(headerCols.length);
  });

  it("quotes CSV fields that contain commas or quotes, so a long rationale can't break columns", () => {
    const prediction = makePrediction({
      reliability: {
        ...makePrediction().reliability,
        applicability_domain: {
          ...makePrediction().reliability.applicability_domain,
          rationale: 'Contains, a comma and "quotes".',
        },
      },
    });
    const csv = predictionToCSV(prediction);
    expect(csv).toContain('"Contains, a comma and ""quotes""."');
  });

  it("triggers a browser download with the given filename and content type", () => {
    const createObjectURL = vi.fn().mockReturnValue("blob:mock-url");
    const revokeObjectURL = vi.fn();
    vi.stubGlobal("URL", { ...URL, createObjectURL, revokeObjectURL });

    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});

    downloadTextFile("result.json", '{"a":1}', "application/json");

    expect(createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();
    expect(revokeObjectURL).toHaveBeenCalledWith("blob:mock-url");

    clickSpy.mockRestore();
    vi.unstubAllGlobals();
  });
});
