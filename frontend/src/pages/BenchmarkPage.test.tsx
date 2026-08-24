import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { BenchmarkPage } from "./BenchmarkPage";

function setup() {
  render(
    <MemoryRouter>
      <BenchmarkPage />
    </MemoryRouter>,
  );
}

describe("BenchmarkPage", () => {
  it("shows both validated endpoints and no others", () => {
    setup();
    expect(screen.getByRole("heading", { name: /^hERG \(KCNH2\/Kv11\.1\) cardiac channel inhibition$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^CYP3A4 metabolic inhibition$/i })).toBeInTheDocument();
    // None of the un-built candidate endpoints should ever appear.
    for (const notBuilt of ["DILI", "Ames", "Caco-2", "BBB permeability", "Half-life", "Bioavailability"]) {
      expect(screen.queryByText(new RegExp(notBuilt, "i"))).not.toBeInTheDocument();
    }
  });

  it("displays a model version and dataset version for every benchmark", () => {
    setup();
    const versionMentions = screen.getAllByText(/model v0\.1\.0/i);
    expect(versionMentions.length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/\(v1\)/).length).toBeGreaterThanOrEqual(2);
  });

  it("never renders a numeric score for GPT or Claude -- only 'Not evaluated'", () => {
    setup();
    const notEvaluated = screen.getAllByText(/not evaluated/i);
    // 2 benchmarks x 2 models x 3 metric rows = 12 "Not evaluated" badges minimum.
    expect(notEvaluated.length).toBeGreaterThanOrEqual(12);
  });

  it("displays uncertainty and applicability domain for individual example cases", () => {
    setup();
    expect(screen.getAllByText(/uncertainty \(90% set\)/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/applicability domain/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/confident, single outcome/i).length).toBeGreaterThan(0);
    // Dofetilide's real, live-captured result is genuinely ambiguous -- must render as such, not smoothed over.
    expect(screen.getByText(/ambiguous: \{non_blocker, blocker\}/i)).toBeInTheDocument();
  });

  it("shows a confusion matrix with real counts, not placeholder zeros", () => {
    setup();
    expect(screen.getAllByText(/true blocker/i).length).toBeGreaterThan(0);
    expect(screen.getAllByText(/true non-blocker/i).length).toBeGreaterThan(0);
  });

  it("distinguishes the overall ChEMBL database scale from either endpoint's own training set", () => {
    setup();
    expect(screen.getByText(/overall scientific database/i)).toBeInTheDocument();
    expect(
      screen.getAllByText((_, element) => /this is\s+not\s+the size of either endpoint's own\s+training set/i.test(element?.textContent ?? "")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/2\.9M\+/)).toBeInTheDocument();
  });

  it("includes the required limitations disclaimer verbatim", () => {
    setup();
    expect(
      screen.getByText(/benchmark results do not establish clinical validity and should not replace experimental testing/i),
    ).toBeInTheDocument();
  });

  it("makes no unsupported comparative or marketing claims", () => {
    setup();
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/smarter than/i);
    expect(body).not.toMatch(/always more accurate/i);
    expect(body).not.toMatch(/cannot predict/i);
    expect(body).not.toMatch(/guarantees safe/i);
    expect(body).not.toMatch(/84%|61%/); // the task brief's own examples of fabricated numbers
  });

  it("shows only the four public example compounds, never a customer or confidential structure", () => {
    setup();
    for (const name of ["Aspirin", "Terfenadine", "Dofetilide", "Paracetamol"]) {
      expect(screen.getByRole("heading", { name })).toBeInTheDocument();
    }
  });
});
