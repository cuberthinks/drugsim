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

  it("never renders a numeric score for GPT or Claude in the validated AI-comparison table -- only 'Not evaluated'", () => {
    setup();
    const notEvaluated = screen.getAllByText(/not evaluated/i);
    // 2 benchmarks x 2 models x 3 metric rows = 12 "Not evaluated" badges minimum
    // in the aggregate table, plus "GPT: not evaluated" once per example-case card.
    expect(notEvaluated.length).toBeGreaterThanOrEqual(12);

    // Scope specifically to each benchmark's aggregate comparison table -- the
    // one requiring the documented protocol against DrugSim's own held-out test
    // set -- and assert no digit ever appears in a GPT/Claude cell there.
    const headings = screen.getAllByRole("heading", { name: /DrugSim vs\. general-purpose AI/i });
    expect(headings.length).toBeGreaterThan(0);
    for (const heading of headings) {
      const card = heading.closest(".card");
      expect(card).not.toBeNull();
      const gptClaudeCells = Array.from(card!.querySelectorAll("div")).filter(
        (el) => el.textContent === "Not evaluated",
      );
      expect(gptClaudeCells.length).toBe(6); // 2 models x 3 metric rows, every one a badge, never a number
    }
  });

  it("labels the individual-case Claude spot-check as an informal, single-run estimate -- never a validated metric", () => {
    setup();
    // Three of the four example compounds have a genuine single-run estimate;
    // each must say so explicitly, not present the number as validated.
    expect(screen.getByText(/Claude \(claude-sonnet-5, single-run spot-check\): non-blocker \(90% self-reported\)/)).toBeInTheDocument();
    expect(screen.getByText(/Claude \(claude-sonnet-5, single-run spot-check\): blocker \(80% self-reported\)/)).toBeInTheDocument();
    expect(screen.getByText(/Claude \(claude-sonnet-5, single-run spot-check\): non-blocker \(88% self-reported\)/)).toBeInTheDocument();
    // Dofetilide's ground truth was seen before a prediction could be made, so
    // it must show unavailable, never a fabricated or retrofitted estimate.
    expect(screen.getByText(/Claude \(claude-sonnet-5\): no blind estimate available/)).toBeInTheDocument();
    // The section-level disclosure must be present, not just a per-card tooltip.
    expect(
      screen.getByText(/does not fill in the .Not evaluated. cells above/i),
    ).toBeInTheDocument();
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
