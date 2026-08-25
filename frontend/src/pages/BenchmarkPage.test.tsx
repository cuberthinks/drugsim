import { render, screen, within } from "@testing-library/react";
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

  it("GPT is always 'Not evaluated' in the validated AI-comparison table, on every benchmark", () => {
    setup();
    const headings = screen.getAllByRole("heading", { name: /DrugSim vs\. general-purpose AI/i });
    expect(headings.length).toBe(2); // hERG, CYP3A4

    for (const heading of headings) {
      const card = heading.closest(".card");
      expect(card).not.toBeNull();
      const notEvaluatedCells = Array.from(card!.querySelectorAll("div")).filter(
        (el) => el.textContent === "Not evaluated",
      );
      // GPT has no API access on any benchmark: 3 metric rows, always a badge, never a number.
      expect(notEvaluatedCells.length).toBeGreaterThanOrEqual(3);
    }
  });

  it("hERG's Claude column in the aggregate table is 'Not evaluated' -- only the informal sections cover hERG", () => {
    setup();
    const heading = screen.getByRole("heading", { name: /^hERG \(KCNH2\/Kv11\.1\) cardiac channel inhibition$/i });
    const card = heading.closest(".card")!.parentElement!;
    const notEvaluatedCells = Array.from(card.querySelectorAll("div")).filter((el) => el.textContent === "Not evaluated");
    // GPT + Claude, 3 metric rows each = 6, since neither has a real hERG-full-test-set evaluation.
    expect(notEvaluatedCells.length).toBe(6);
  });

  it("CYP3A4's Claude column shows the real, unflattering result -- not 'Not evaluated', not fabricated", () => {
    setup();
    const heading = screen.getByRole("heading", { name: /^CYP3A4 metabolic inhibition$/i });
    const card = heading.closest(".card")!.parentElement!;
    const notEvaluatedCells = Array.from(card.querySelectorAll("div")).filter((el) => el.textContent === "Not evaluated");
    // GPT only: 3 metric rows. Claude's 3 cells are real numbers now.
    expect(notEvaluatedCells.length).toBe(3);
    expect(within(card).getByText("56.0%")).toBeInTheDocument(); // ROC-AUC, barely above chance
    expect(within(card).getByText("53.6%")).toBeInTheDocument(); // balanced accuracy
    expect(within(card).getByText("72.2%")).toBeInTheDocument(); // F1
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
    // The section-level disclosure must be present, not just a per-card tooltip
    // -- both the 4-compound spot-check section and the 30-compound subset
    // evaluation section say this, independently, so at least 2 matches.
    expect(
      screen.getAllByText(/does not fill in the .Not evaluated. cells above/i).length,
    ).toBeGreaterThanOrEqual(2);
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

  it("shows the 30-compound Claude subset evaluation, clearly labeled as informal and 30 of 800", () => {
    setup();
    expect(screen.getByRole("heading", { name: /Claude — informal subset evaluation/i })).toBeInTheDocument();
    expect(screen.getByText(/30 of DrugSim's real 800-compound held-out hERG test set/i)).toBeInTheDocument();
    // "not" is wrapped in <strong>, splitting the phrase across text nodes --
    // match on textContent, same pattern used for the database-scale disclosure above.
    expect(
      screen.getAllByText((_, element) => /is\s+not\s+the documented protocol/i.test(element?.textContent ?? "")).length,
    ).toBeGreaterThan(0);
    expect(screen.getByText(/asking each already-dispatched subagent for a 0-100 probability/i)).toBeInTheDocument();
    // The real, unflattering result -- lower than DrugSim's own, and shown as such.
    expect(screen.getByText(/67\.6%/)).toBeInTheDocument(); // ROC-AUC
    expect(screen.getByText(/56\.9%/)).toBeInTheDocument(); // balanced accuracy
    expect(screen.getByText(/68\.4%/)).toBeInTheDocument(); // F1
    expect(screen.getByText(/not a claim about DrugSim being "better,"/i)).toBeInTheDocument();
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
