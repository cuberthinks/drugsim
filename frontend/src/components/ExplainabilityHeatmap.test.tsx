import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { ExplainabilityHeatmap } from "./ExplainabilityHeatmap";
import { ApiError } from "../api/client";
import { cacheExplanation } from "../lib/explanationCache";
import { makePrediction } from "../test/fixtures";
import type { ExplainabilityResponse } from "../api/types";

const { explainPredictionMock } = vi.hoisted(() => ({ explainPredictionMock: vi.fn() }));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, explainPrediction: explainPredictionMock };
});

function makeExplanation(overrides: Partial<ExplainabilityResponse> = {}): ExplainabilityResponse {
  return {
    molecule: makePrediction().molecule,
    endpoint: "herg_inhibition",
    positive_class_label: "blocker",
    base_value: 0.36,
    atom_contributions: [
      { atom_index: 0, contribution: 0.02 },
      { atom_index: 1, contribution: -0.01 },
    ],
    descriptor_contributions: [
      { name: "mw_g_mol", value: 180.16, contribution: 0.05 },
      { name: "logp_crippen", value: 1.2, contribution: -0.03 },
    ],
    absent_substructure_contribution: 0.0,
    method: "shap_tree_explainer_interventional",
    ...overrides,
  };
}

describe("ExplainabilityHeatmap", () => {
  afterEach(() => {
    explainPredictionMock.mockReset();
    window.localStorage.clear();
  });

  it("renders nothing for an endpoint that does not support explainability yet", () => {
    const prediction = makePrediction({ estimate: { ...makePrediction().estimate, endpoint: "cyp3a4_inhibition" } });
    const { container } = render(<ExplainabilityHeatmap prediction={prediction} />);
    expect(container).toBeEmptyDOMElement();
    expect(screen.queryByRole("button", { name: /attention map/i })).not.toBeInTheDocument();
  });

  it("uses a cached explanation instead of refetching (retention)", async () => {
    const user = userEvent.setup();
    const prediction = makePrediction();
    cacheExplanation(prediction.id, makeExplanation());

    render(<ExplainabilityHeatmap prediction={prediction} />);
    await user.click(screen.getByRole("button", { name: /show attention map/i }));

    expect(screen.getByText(/molecular weight/i)).toBeInTheDocument();
    expect(explainPredictionMock).not.toHaveBeenCalled();
  });

  it("caches a freshly fetched explanation so a later mount does not refetch it", async () => {
    const user = userEvent.setup();
    explainPredictionMock.mockResolvedValue(makeExplanation());
    const prediction = makePrediction();

    const { unmount } = render(<ExplainabilityHeatmap prediction={prediction} />);
    await user.click(screen.getByRole("button", { name: /show attention map/i }));
    await waitFor(() => expect(screen.getByText(/molecular weight/i)).toBeInTheDocument());
    unmount();

    render(<ExplainabilityHeatmap prediction={prediction} />);
    await user.click(screen.getByRole("button", { name: /show attention map/i }));

    expect(screen.getByText(/molecular weight/i)).toBeInTheDocument();
    expect(explainPredictionMock).toHaveBeenCalledTimes(1);
  });

  it("does not fetch an explanation until the user asks for one", () => {
    render(<ExplainabilityHeatmap prediction={makePrediction()} />);
    expect(explainPredictionMock).not.toHaveBeenCalled();
    expect(screen.queryByText(/computing explanation/i)).not.toBeInTheDocument();
  });

  it("fetches and renders the explanation when toggled on", async () => {
    const user = userEvent.setup();
    explainPredictionMock.mockResolvedValue(makeExplanation());
    render(<ExplainabilityHeatmap prediction={makePrediction()} />);

    await user.click(screen.getByRole("button", { name: /show attention map/i }));

    expect(explainPredictionMock).toHaveBeenCalledWith(
      makePrediction().molecule.standardized_smiles,
      "smiles",
      "herg_inhibition",
    );
    await waitFor(() => expect(screen.getByText(/molecular weight/i)).toBeInTheDocument());
    expect(screen.getByText(/logp/i)).toBeInTheDocument();
  });

  it("only fetches once across repeated toggles", async () => {
    const user = userEvent.setup();
    explainPredictionMock.mockResolvedValue(makeExplanation());
    render(<ExplainabilityHeatmap prediction={makePrediction()} />);

    const button = () => screen.getByRole("button", { name: /(show|hide) attention map/i });
    await user.click(button());
    await waitFor(() => expect(screen.getByText(/molecular weight/i)).toBeInTheDocument());
    await user.click(button()); // hide
    await user.click(button()); // show again

    expect(explainPredictionMock).toHaveBeenCalledTimes(1);
  });

  it("shows a real error message, not a silent failure, when the backend rejects the request", async () => {
    const user = userEvent.setup();
    explainPredictionMock.mockRejectedValue(new ApiError("validation", "Molecular structure could not be processed"));
    render(<ExplainabilityHeatmap prediction={makePrediction()} />);

    await user.click(screen.getByRole("button", { name: /show attention map/i }));

    await waitFor(() => expect(screen.getByText(/could not be processed/i)).toBeInTheDocument());
  });

  it("discloses the absent-substructure contribution when it is non-trivial", async () => {
    const user = userEvent.setup();
    explainPredictionMock.mockResolvedValue(makeExplanation({ absent_substructure_contribution: 0.12 }));
    render(<ExplainabilityHeatmap prediction={makePrediction()} />);

    await user.click(screen.getByRole("button", { name: /show attention map/i }));

    await waitFor(() => expect(screen.getByText(/chemistry this molecule does/i)).toBeInTheDocument());
  });

  it("does not mention absence when the contribution is negligible", async () => {
    const user = userEvent.setup();
    explainPredictionMock.mockResolvedValue(makeExplanation({ absent_substructure_contribution: 0.0 }));
    render(<ExplainabilityHeatmap prediction={makePrediction()} />);

    await user.click(screen.getByRole("button", { name: /show attention map/i }));

    await waitFor(() => expect(screen.getByText(/molecular weight/i)).toBeInTheDocument());
    expect(screen.queryByText(/chemistry this molecule does/i)).not.toBeInTheDocument();
  });
});
