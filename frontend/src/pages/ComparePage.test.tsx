import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it } from "vitest";
import { ComparePage } from "./ComparePage";
import { saveToHistory } from "../lib/history";
import { makePrediction } from "../test/fixtures";

function renderPage() {
  render(
    <MemoryRouter>
      <ComparePage />
    </MemoryRouter>,
  );
}

describe("ComparePage", () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it("asks the user to run more predictions when fewer than two exist", () => {
    saveToHistory(makePrediction(), "Only one", "2026-01-01T00:00:00Z");
    renderPage();
    expect(screen.getByText(/run at least two predictions to compare them/i)).toBeInTheDocument();
  });

  it("lets the user pick two same-endpoint compounds and shows them side by side, with no combined score", async () => {
    const user = userEvent.setup();
    saveToHistory(makePrediction({ id: "a" }), "Compound A name", "2026-01-01T00:00:00Z");
    saveToHistory(makePrediction({ id: "b" }), "Compound B name", "2026-01-02T00:00:00Z");
    renderPage();

    await user.selectOptions(screen.getByLabelText(/^compound a$/i), "a");
    await user.selectOptions(screen.getByLabelText(/^compound b$/i), "b");

    expect(screen.getByText("Compound A name")).toBeInTheDocument();
    expect(screen.getByText("Compound B name")).toBeInTheDocument();
    // Same fixture predicted twice -- both show "Predicted non-inhibitor" as
    // independent per-compound results, not merged into one verdict.
    expect(screen.getAllByText(/predicted non-inhibitor/i)).toHaveLength(2);
    expect(screen.queryByText(/better|winner|recommended|overall score/i)).not.toBeInTheDocument();
  });

  it("restricts comparison to compounds analysed on the same endpoint", async () => {
    saveToHistory(
      makePrediction({ id: "herg-1", estimate: { ...makePrediction().estimate, endpoint: "herg_inhibition" } }),
      "hERG compound",
      "2026-01-01T00:00:00Z",
    );
    saveToHistory(
      makePrediction({
        id: "cyp-1",
        estimate: { ...makePrediction().estimate, endpoint: "cyp3a4_inhibition" },
        provenance: { ...makePrediction().provenance, model_id: "cyp3a4_inhibition" },
      }),
      "CYP3A4 compound",
      "2026-01-02T00:00:00Z",
    );
    renderPage();

    // Only one compound exists per endpoint here, so comparison isn't
    // possible for either -- the endpoint filter is doing its job.
    expect(screen.getByText(/need at least two predictions for this endpoint/i)).toBeInTheDocument();
  });
});
