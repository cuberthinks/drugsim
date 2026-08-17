import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ScientificExplanation } from "./ScientificExplanation";

describe("ScientificExplanation", () => {
  it("separates the prediction, uncertainty, and applicability domain into distinct labelled sections", () => {
    render(<ScientificExplanation endpoint="herg_inhibition" />);
    expect(screen.getByText(/the prediction — what the model thinks/i)).toBeInTheDocument();
    expect(screen.getByText(/the uncertainty — how confident the math is/i)).toBeInTheDocument();
    expect(
      screen.getByText(/the applicability domain — whether the model has the right experience to guess/i),
    ).toBeInTheDocument();
  });

  it("still includes the endpoint-specific biological description", () => {
    render(<ScientificExplanation endpoint="herg_inhibition" />);
    expect(screen.getByText(/cardiac hERG potassium channel/i)).toBeInTheDocument();
  });

  it("falls back gracefully for an unrecognised endpoint", () => {
    render(<ScientificExplanation endpoint="some_future_endpoint" />);
    expect(screen.getByText(/the prediction — what the model thinks/i)).toBeInTheDocument();
    expect(screen.getByText(/no description is available for this endpoint yet/i)).toBeInTheDocument();
  });

  it("keeps the explicit not-a-diagnosis disclaimer", () => {
    render(<ScientificExplanation endpoint="herg_inhibition" />);
    expect(screen.getByText(/not a clinical diagnosis/i)).toBeInTheDocument();
  });
});
