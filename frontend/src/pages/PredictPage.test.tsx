import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import { PredictPage } from "./PredictPage";
import { ApiError } from "../api/client";
import { makePrediction } from "../test/fixtures";
import { getHistory } from "../lib/history";

const { predictMock } = vi.hoisted(() => ({ predictMock: vi.fn() }));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, predict: predictMock };
});

function renderPage() {
  render(
    <MemoryRouter>
      <PredictPage />
    </MemoryRouter>,
  );
}

async function enterAndValidate(user: ReturnType<typeof userEvent.setup>, smiles = "CC(=O)Oc1ccccc1C(=O)O") {
  await user.type(screen.getByLabelText(/paste a smiles string/i), smiles);
  await user.click(screen.getByRole("button", { name: /^validate$/i }));
}

describe("PredictPage", () => {
  afterEach(() => {
    predictMock.mockReset();
  });

  it("sends a prediction request with the entered structure", async () => {
    const user = userEvent.setup();
    predictMock.mockResolvedValue(makePrediction());
    renderPage();

    await enterAndValidate(user);

    await waitFor(() =>
      expect(predictMock).toHaveBeenCalledWith("CC(=O)Oc1ccccc1C(=O)O", "smiles", "herg_inhibition"),
    );
  });

  it("shows a loading state while a request is in flight", async () => {
    const user = userEvent.setup();
    let resolveRequest: (value: ReturnType<typeof makePrediction>) => void = () => {};
    predictMock.mockReturnValue(new Promise((resolve) => (resolveRequest = resolve)));
    renderPage();

    await enterAndValidate(user);

    expect(await screen.findByRole("button", { name: /validating/i })).toBeInTheDocument();
    resolveRequest(makePrediction());
  });

  it("shows a lightweight, always-visible three-step guide to the workflow", () => {
    renderPage();
    const steps = within(screen.getByRole("list", { name: /how this works/i }));
    expect(steps.getByText(/enter a molecule/i)).toBeInTheDocument();
    expect(steps.getByText(/run a prediction/i)).toBeInTheDocument();
    expect(steps.getByText(/review prediction \+ reliability/i)).toBeInTheDocument();
  });

  it("renders the molecule preview after validation", async () => {
    const user = userEvent.setup();
    predictMock.mockResolvedValue(makePrediction());
    renderPage();

    await enterAndValidate(user);

    expect(await screen.findByText(/canonical smiles/i)).toBeInTheDocument();
  });

  it("renders prediction results, including uncertainty, applicability domain, and reliability, once predicted", async () => {
    const user = userEvent.setup();
    predictMock.mockResolvedValue(makePrediction());
    renderPage();

    await enterAndValidate(user);
    await user.click(await screen.findByRole("button", { name: /predict herg inhibition/i }));

    expect(await screen.findByRole("heading", { name: /predicted non-inhibitor/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /uncertainty/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /applicability domain/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /reliability/i })).toBeInTheDocument();
  });

  it("saves a completed prediction to local history but not a mere validation", async () => {
    const user = userEvent.setup();
    predictMock.mockResolvedValue(makePrediction());
    window.localStorage.clear();
    renderPage();

    await enterAndValidate(user);
    expect(getHistory()).toHaveLength(0);

    await user.click(await screen.findByRole("button", { name: /predict herg inhibition/i }));
    await waitFor(() => expect(getHistory()).toHaveLength(1));
  });

  it("offers JSON and CSV export of the completed result", async () => {
    const user = userEvent.setup();
    predictMock.mockResolvedValue(makePrediction());
    renderPage();

    await enterAndValidate(user);
    await user.click(await screen.findByRole("button", { name: /predict herg inhibition/i }));

    expect(await screen.findByRole("button", { name: /download json/i })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /download csv/i })).toBeInTheDocument();
  });

  it("shows an honest error state for an invalid molecule instead of a fabricated result", async () => {
    const user = userEvent.setup();
    predictMock.mockRejectedValue(new ApiError("validation", "The SMILES string could not be parsed."));
    renderPage();

    await enterAndValidate(user, "not-a-smiles-string");

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.getByText(/could not be processed/i)).toBeInTheDocument();
    expect(screen.queryByText(/predicted non-inhibitor/i)).not.toBeInTheDocument();
  });

  it("shows an honest error state when the API is unreachable", async () => {
    const user = userEvent.setup();
    predictMock.mockRejectedValue(new ApiError("network", "Could not reach the prediction service."));
    renderPage();

    await enterAndValidate(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/could not reach the prediction service/i);
  });

  it("shows an honest error state on an unexpected server error, distinct from a network failure", async () => {
    const user = userEvent.setup();
    predictMock.mockRejectedValue(new ApiError("server_error", "An unexpected error occurred."));
    renderPage();

    await enterAndValidate(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/something went wrong on our end/i);
    expect(screen.queryByText(/predicted non-inhibitor/i)).not.toBeInTheDocument();
  });

  it("shows an honest error state on a request timeout", async () => {
    const user = userEvent.setup();
    predictMock.mockRejectedValue(new ApiError("timeout", "The prediction service did not respond in time."));
    renderPage();

    await enterAndValidate(user);

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(/took too long/i);
  });

  it("renders an out-of-domain prediction as a successful result, not an error", async () => {
    const user = userEvent.setup();
    const outOfDomain = makePrediction({
      reliability: {
        conformal: makePrediction().reliability.conformal,
        applicability_domain: {
          verdict: "out_of_domain",
          max_tanimoto_to_training: 0.12,
          knn_distance: 5.0,
          knn_distance_threshold: 1.7,
          scaffold_seen_in_training: false,
          rationale: "Far from any training compound.",
          method: "tanimoto_knn_distance_scaffold_membership",
        },
      },
      warnings: [
        { code: "out_of_domain", severity: "high", message: "This prediction is an extrapolation.", field: "applicability_domain" },
      ],
    });
    predictMock.mockResolvedValue(outOfDomain);
    renderPage();

    await enterAndValidate(user);
    await user.click(await screen.findByRole("button", { name: /predict herg inhibition/i }));

    expect(await screen.findByText(/this prediction is an extrapolation/i)).toBeInTheDocument();
    expect(screen.getAllByText(/novel chemistry/i).length).toBeGreaterThan(0);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  // A failed re-run used to reset the stage to "idle", and every result
  // below is gated on the stage -- so a transient backend error silently
  // wiped a result the user was still reading and made them run the whole
  // request again to get it back.
  it("keeps the existing result on screen when a later request fails", async () => {
    const user = userEvent.setup();
    predictMock.mockResolvedValue(makePrediction());
    renderPage();

    await enterAndValidate(user);
    await user.click(await screen.findByRole("button", { name: /predict herg inhibition/i }));
    expect(await screen.findByRole("heading", { name: /predicted non-inhibitor/i })).toBeInTheDocument();

    // The next run fails the way a backend restart does.
    predictMock.mockRejectedValue(new ApiError("unavailable", "The prediction service is temporarily unavailable."));
    await user.click(screen.getByRole("button", { name: /predict herg inhibition/i }));

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    // The earlier result is still there, and labelled as the previous one.
    expect(screen.getByRole("heading", { name: /predicted non-inhibitor/i })).toBeInTheDocument();
    expect(screen.getByText(/from your last successful run/i)).toBeInTheDocument();
  });

  it("does not claim a previous result exists when the very first request fails", async () => {
    const user = userEvent.setup();
    predictMock.mockRejectedValue(new ApiError("unavailable", "The prediction service is temporarily unavailable."));
    renderPage();

    await enterAndValidate(user);

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(screen.queryByText(/from your last successful run/i)).not.toBeInTheDocument();
  });
});
