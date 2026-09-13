import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { HistoryPage } from "./HistoryPage";
import { saveToHistory } from "../lib/history";
import { makePrediction } from "../test/fixtures";

function renderPage() {
  render(
    <MemoryRouter>
      <HistoryPage />
    </MemoryRouter>,
  );
}

describe("HistoryPage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("shows an empty state with a link to run a prediction when nothing is saved", () => {
    renderPage();
    expect(screen.getByText(/no predictions saved yet/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /run one/i })).toHaveAttribute("href", "/predict");
  });

  it("lists a saved prediction with its endpoint, prediction, reliability, and applicability domain", () => {
    saveToHistory(makePrediction(), "Aspirin", "2026-01-01T00:00:00Z");
    renderPage();

    expect(screen.getByText("Aspirin")).toBeInTheDocument();
    expect(screen.getByText(/predicted non-inhibitor/i)).toBeInTheDocument();
    expect(screen.getByText(/in domain/i)).toBeInTheDocument();
  });

  it("never claims a name for an unnamed entry -- shows the structure instead", () => {
    saveToHistory(makePrediction(), "", "2026-01-01T00:00:00Z");
    renderPage();
    expect(screen.getByText(makePrediction().molecule.canonical_smiles)).toBeInTheDocument();
  });

  it("removes a single entry without clearing the rest", async () => {
    const user = userEvent.setup();
    saveToHistory(makePrediction({ id: "keep" }), "Keep me", "2026-01-01T00:00:00Z");
    saveToHistory(makePrediction({ id: "drop" }), "Drop me", "2026-01-02T00:00:00Z");
    renderPage();

    await user.click(screen.getByRole("button", { name: /remove drop me from history/i }));
    expect(screen.queryByText("Drop me")).not.toBeInTheDocument();
    expect(screen.getByText("Keep me")).toBeInTheDocument();
  });

  it("clears all history when asked", async () => {
    const user = userEvent.setup();
    saveToHistory(makePrediction(), "Aspirin", "2026-01-01T00:00:00Z");
    renderPage();

    await user.click(screen.getByRole("button", { name: /clear history/i }));
    expect(screen.getByText(/no predictions saved yet/i)).toBeInTheDocument();
  });

  it("only offers to compare once at least two predictions are saved", () => {
    saveToHistory(makePrediction({ id: "one" }), "", "2026-01-01T00:00:00Z");
    renderPage();
    expect(screen.queryByRole("link", { name: /compare two compounds/i })).not.toBeInTheDocument();
  });

  it("exposes the conformal statistics behind a disclosure, with a plain-language caveat", async () => {
    const user = userEvent.setup();
    saveToHistory(makePrediction(), "Aspirin", "2026-01-01T00:00:00Z");
    renderPage();

    // Closed by default -- the summary label is present, the p-values are not
    // yet the *only* thing on the card.
    expect(screen.getByText(/statistical detail/i)).toBeInTheDocument();

    await user.click(screen.getByText(/statistical detail/i));

    expect(screen.getByText("0.030 / 0.620")).toBeInTheDocument();
    expect(screen.getByText(/90%/)).toBeInTheDocument();
    expect(screen.getByText(/split_conformal_prediction/)).toBeInTheDocument();
    expect(screen.getByText(/not a significance test and carries no clinical meaning/i)).toBeInTheDocument();
  });

  it("renders a non-singleton conformal set with its both-classes-retained caveat", async () => {
    const user = userEvent.setup();
    saveToHistory(
      makePrediction({
        reliability: {
          ...makePrediction().reliability,
          conformal: {
            ...makePrediction().reliability.conformal,
            predicted_set: ["blocker", "non_blocker"],
            is_singleton: false,
          },
        },
      }),
      "Ambiguous compound",
      "2026-01-01T00:00:00Z",
    );
    renderPage();

    await user.click(screen.getByText(/statistical detail/i));
    expect(screen.getByText(/could not separate them at this confidence level/i)).toBeInTheDocument();
  });

  it("renders history entries saved before the statistics field existed without the disclosure", () => {
    const legacyEntry = {
      id: "legacy-1",
      timestamp: "2026-01-01T00:00:00Z",
      compoundName: "Legacy Compound",
      endpoint: "herg_inhibition",
      structure: "CCO",
      predictedLabel: "non_blocker",
      reliabilityRating: "High",
      applicabilityDomainVerdict: "in_domain",
      modelId: "herg_inhibition",
      modelVersion: "0.1.0",
      // no `statistics` field -- exactly what a pre-migration row looks like.
    };
    window.localStorage.setItem("drugsim_prediction_history_v1", JSON.stringify([legacyEntry]));
    renderPage();

    expect(screen.getByText("Legacy Compound")).toBeInTheDocument();
    expect(screen.queryByText(/statistical detail/i)).not.toBeInTheDocument();
  });
});
