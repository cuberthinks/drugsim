import { render, screen, waitFor } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { CompoundProfile } from "./CompoundProfile";
import { ApiError } from "../api/client";
import { makePrediction } from "../test/fixtures";
import type { EndpointListItem } from "../api/types";

const { predictMock } = vi.hoisted(() => ({ predictMock: vi.fn() }));

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, predict: predictMock };
});

const HERG: EndpointListItem = {
  model_id: "herg_inhibition",
  endpoint_name: "hERG (KCNH2/Kv11.1) inhibition",
  category: "Toxicity",
  final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
  dataset_version: "v1",
  training_set_size: 9589,
  servable: true,
};

const CYP3A4: EndpointListItem = {
  model_id: "cyp3a4_inhibition",
  endpoint_name: "CYP3A4 inhibition",
  category: "Metabolism",
  final_report_status: "VALIDATED FOR INTERNAL RESEARCH",
  dataset_version: "v1",
  training_set_size: 5344,
  servable: true,
};

const EXPERIMENTAL: EndpointListItem = {
  model_id: "future_endpoint",
  endpoint_name: "Future endpoint",
  category: "Absorption",
  final_report_status: "EXPERIMENTAL",
  dataset_version: "v1",
  training_set_size: 100,
  servable: false,
};

describe("CompoundProfile", () => {
  afterEach(() => {
    predictMock.mockReset();
  });

  it("groups endpoints by category and shows each endpoint's own prediction/uncertainty/reliability", async () => {
    predictMock.mockImplementation((_value: string, _format: string, endpoint: string) =>
      Promise.resolve(makePrediction({ estimate: { ...makePrediction().estimate, endpoint } })),
    );

    render(<CompoundProfile structureValue="CCO" endpoints={[HERG, CYP3A4]} />);

    expect(screen.getByText(/toxicity/i)).toBeInTheDocument();
    expect(screen.getByText(/metabolism/i)).toBeInTheDocument();

    await waitFor(() => expect(predictMock).toHaveBeenCalledTimes(2));
    expect(await screen.findAllByText(/prediction$/i)).toHaveLength(2);
    expect(screen.getAllByText(/uncertainty/i).length).toBeGreaterThanOrEqual(2);
    expect(screen.getAllByText(/reliability/i).length).toBeGreaterThanOrEqual(2);
  });

  it("never shows a combined score across endpoints (only explains there isn't one)", async () => {
    predictMock.mockResolvedValue(makePrediction());
    render(<CompoundProfile structureValue="CCO" endpoints={[HERG, CYP3A4]} />);
    // No heading, badge, or number claiming to be a combined/overall score --
    // only the explanatory prose disclaiming one exists (checked separately).
    expect(screen.queryByRole("heading", { name: /score/i })).not.toBeInTheDocument();
    expect(screen.getByText(/no combined "drugsim score"/i)).toBeInTheDocument();
    await waitFor(() => expect(predictMock).toHaveBeenCalledTimes(2));
  });

  it("only displays servable (validated) endpoints, never an experimental one presented as available", async () => {
    predictMock.mockResolvedValue(makePrediction());
    render(<CompoundProfile structureValue="CCO" endpoints={[HERG, EXPERIMENTAL]} />);
    expect(screen.getByText(/hERG/)).toBeInTheDocument();
    expect(screen.queryByText(/future endpoint/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/absorption/i)).not.toBeInTheDocument();
    await waitFor(() => expect(predictMock).toHaveBeenCalledTimes(1));
  });

  it("shows an honest per-card error when one endpoint fails, without hiding the others", async () => {
    predictMock.mockImplementation((_value: string, _format: string, endpoint: string) => {
      if (endpoint === "cyp3a4_inhibition") {
        return Promise.reject(new ApiError("server_error", "An unexpected error occurred."));
      }
      return Promise.resolve(makePrediction({ estimate: { ...makePrediction().estimate, endpoint } }));
    });

    render(<CompoundProfile structureValue="CCO" endpoints={[HERG, CYP3A4]} />);

    expect(await screen.findByText(/could not complete this prediction/i)).toBeInTheDocument();
    expect(await screen.findByText(/predicted non-inhibitor/i)).toBeInTheDocument();
  });
});
