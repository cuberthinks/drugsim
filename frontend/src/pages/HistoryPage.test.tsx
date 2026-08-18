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
});
