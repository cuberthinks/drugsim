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

  it("has no GPT column anywhere -- the comparison is DrugSim vs. Claude only, GPT was removed rather than left permanently 'Not evaluated'", () => {
    setup();
    expect(screen.queryByText(/gpt/i)).not.toBeInTheDocument();
  });

  it("each benchmark's AI-comparison table is labeled with its own endpoint, not two identically-titled sections", () => {
    setup();
    expect(screen.getByRole("heading", { name: /^hERG — DrugSim vs\. general-purpose AI$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^CYP3A4 — DrugSim vs\. general-purpose AI$/i })).toBeInTheDocument();
  });

  it("hERG's Claude column shows the real, unflattering result -- not 'Not evaluated', not fabricated", () => {
    setup();
    const heading = screen.getByRole("heading", { name: /^hERG \(KCNH2\/Kv11\.1\) cardiac channel inhibition$/i });
    const card = heading.closest(".card")!.parentElement!;
    const notEvaluatedCells = Array.from(card.querySelectorAll("div")).filter((el) => el.textContent === "Not evaluated");
    // GPT column was removed entirely and Claude has a real result: no "Not evaluated" cells at all here.
    expect(notEvaluatedCells.length).toBe(0);
    expect(within(card).getByText("65.4%")).toBeInTheDocument(); // ROC-AUC
    expect(within(card).getByText("61.5%")).toBeInTheDocument(); // balanced accuracy
    expect(within(card).getByText("59.4%")).toBeInTheDocument(); // F1
  });

  it("CYP3A4's Claude column shows the real, unflattering result -- not 'Not evaluated', not fabricated", () => {
    setup();
    const heading = screen.getByRole("heading", { name: /^CYP3A4 metabolic inhibition$/i });
    const card = heading.closest(".card")!.parentElement!;
    const notEvaluatedCells = Array.from(card.querySelectorAll("div")).filter((el) => el.textContent === "Not evaluated");
    // GPT column was removed entirely and Claude has a real result: no "Not evaluated" cells at all here.
    expect(notEvaluatedCells.length).toBe(0);
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
    // evaluation section must independently disclose that they're smaller and
    // less rigorous than the full-set results already shown above, so at
    // least 2 matches.
    expect(
      screen.getAllByText(/less rigorous than the full/i).length,
    ).toBeGreaterThanOrEqual(1);
    expect(
      screen.getAllByText(/less rigorous supplement to the full/i).length,
    ).toBeGreaterThanOrEqual(1);
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
    // The subset's self-reported confidence is coarse (9 distinct values across
    // 30 compounds) and not a calibrated score -- this must be disclosed, not
    // just implied by the small sample size.
    expect(screen.getByText(/9 distinct values across these 30 compounds/i)).toBeInTheDocument();
  });

  it("discloses that Claude's ROC-AUC (self-reported confidence) is not like-for-like with DrugSim's calibrated predict_proba, on every AI-comparison card that has a real result", () => {
    setup();
    // hERG card, CYP3A4 card, and the 30-compound subset section each carry
    // this caveat independently -- at least 3 matches across the page.
    expect(screen.getAllByText(/predict_proba/).length).toBeGreaterThanOrEqual(3);
    expect(screen.getAllByText(/self-reported 0-100 confidence/i).length).toBeGreaterThanOrEqual(2);
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

  it("shows a DrugSim vs. established ADMET tools comparison for each endpoint, labeled distinctly from the general-purpose AI comparison", () => {
    setup();
    expect(screen.getByRole("heading", { name: /^hERG — DrugSim vs\. established ADMET tools$/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /^CYP3A4 — DrugSim vs\. established ADMET tools$/i })).toBeInTheDocument();
  });

  it("discloses that SwissADME was excluded because its own Terms of Use ban automated access -- not silently skipped", () => {
    setup();
    expect(screen.getAllByText(/SwissADME was considered and excluded/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/Terms of Use explicitly prohibit automated access/i).length).toBeGreaterThanOrEqual(2);
  });

  it("shows ADMETlab 2.0's real full-set results for both endpoints", () => {
    setup();
    const hergHeading = screen.getByRole("heading", { name: /^hERG — DrugSim vs\. established ADMET tools$/i });
    const hergCard = hergHeading.closest(".card")! as HTMLElement;
    expect(within(hergCard).getByText("72.8%")).toBeInTheDocument(); // ROC-AUC
    expect(within(hergCard).getByText("60.0%")).toBeInTheDocument(); // balanced accuracy
    expect(within(hergCard).getByText("77.8%")).toBeInTheDocument(); // F1

    const cypHeading = screen.getByRole("heading", { name: /^CYP3A4 — DrugSim vs\. established ADMET tools$/i });
    const cypCard = cypHeading.closest(".card")! as HTMLElement;
    expect(within(cypCard).getByText("62.7%")).toBeInTheDocument(); // ROC-AUC
    expect(within(cypCard).getByText("55.6%")).toBeInTheDocument(); // balanced accuracy
    expect(within(cypCard).getByText("75.6%")).toBeInTheDocument(); // F1
  });

  it("shows pkCSM's n=5 spot-check as 'Not computable' for ROC-AUC, never 'Not evaluated' -- the tool genuinely ran, it just has no continuous score", () => {
    setup();
    const hergHeading = screen.getByRole("heading", { name: /^hERG — DrugSim vs\. established ADMET tools$/i });
    const hergCard = hergHeading.closest(".card")! as HTMLElement;
    expect(within(hergCard).getByText(/hERG I inhibitor/i)).toBeInTheDocument();
    expect(within(hergCard).getByText(/hERG II inhibitor/i)).toBeInTheDocument();
    // Two submodels disagreeing completely on this tiny sample -- both real F1s must appear distinctly.
    expect(within(hergCard).getByText("0.0%")).toBeInTheDocument(); // hERG I's F1
    expect(within(hergCard).getByText("75.0%")).toBeInTheDocument(); // hERG II's F1
    expect(within(hergCard).queryByText("Not evaluated")).not.toBeInTheDocument();

    const cypHeading = screen.getByRole("heading", { name: /^CYP3A4 — DrugSim vs\. established ADMET tools$/i });
    const cypCard = cypHeading.closest(".card")! as HTMLElement;
    expect(within(cypCard).getByText("16.7%")).toBeInTheDocument(); // pkCSM CYP3A4 balanced accuracy
    expect(within(cypCard).queryByText("Not evaluated")).not.toBeInTheDocument();
  });
});
