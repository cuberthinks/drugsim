import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { MemoryRouter } from "react-router-dom";
import { ModelEvidencePanel } from "./ModelEvidencePanel";
import { makePrediction } from "../test/fixtures";

describe("ModelEvidencePanel", () => {
  it("starts collapsed and exposes its expanded state via aria-expanded", async () => {
    const user = userEvent.setup();
    render(
      <MemoryRouter>
        <ModelEvidencePanel prediction={makePrediction()} />
      </MemoryRouter>,
    );
    const toggle = screen.getByRole("button", { name: /model.*evidence/i });
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "true");
  });

  it("shows real provenance values once expanded, never invented ones", async () => {
    const user = userEvent.setup();
    const prediction = makePrediction();
    render(
      <MemoryRouter>
        <ModelEvidencePanel prediction={prediction} />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole("button", { name: /model.*evidence/i }));
    expect(
      screen.getByText(`${prediction.provenance.model_id} v${prediction.provenance.model_version}`),
    ).toBeInTheDocument();
    expect(screen.getByText(/6,792 compounds/)).toBeInTheDocument();
  });

  it("surfaces every field needed to reproduce this exact prediction (Phase 7)", async () => {
    const user = userEvent.setup();
    const prediction = makePrediction();
    render(
      <MemoryRouter>
        <ModelEvidencePanel prediction={prediction} />
      </MemoryRouter>,
    );
    await user.click(screen.getByRole("button", { name: /model.*evidence/i }));

    expect(screen.getByText(prediction.provenance.model_checksum)).toBeInTheDocument();
    expect(screen.getByText(prediction.provenance.standardization_pipeline_version)).toBeInTheDocument();
    expect(screen.getByText(prediction.provenance.descriptor_spec_version)).toBeInTheDocument();
    expect(screen.getByText(prediction.provenance.rdkit_version)).toBeInTheDocument();
    expect(screen.getByText(prediction.provenance.input_hash)).toBeInTheDocument();
  });
});
