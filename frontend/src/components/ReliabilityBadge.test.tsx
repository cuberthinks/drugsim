import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ReliabilityBadge } from "./ReliabilityBadge";
import { makePrediction } from "../test/fixtures";

describe("ReliabilityBadge", () => {
  it("shows High for an in-domain, singleton prediction", () => {
    const { reliability } = makePrediction();
    render(<ReliabilityBadge reliability={reliability} />);
    expect(screen.getByText("High")).toBeInTheDocument();
  });

  it("discloses that the rating is a summary, not a separate backend field", () => {
    const { reliability } = makePrediction();
    render(<ReliabilityBadge reliability={reliability} />);
    expect(screen.getByText(/not a separate backend measurement/i)).toBeInTheDocument();
  });

  it("shows Low for an out-of-domain prediction", () => {
    const { reliability } = makePrediction();
    render(
      <ReliabilityBadge
        reliability={{
          ...reliability,
          applicability_domain: { ...reliability.applicability_domain, verdict: "out_of_domain" },
        }}
      />,
    );
    expect(screen.getByText("Low")).toBeInTheDocument();
  });
});
