import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UncertaintyPanel } from "./UncertaintyPanel";
import { makePrediction } from "../test/fixtures";

describe("UncertaintyPanel", () => {
  it("shows the predicted set label for a singleton result", () => {
    const { reliability } = makePrediction();
    render(<UncertaintyPanel conformal={reliability.conformal} endpoint="herg_inhibition" />);
    expect(screen.getByText(/predicted non-inhibitor/i)).toBeInTheDocument();
    expect(screen.getByText(/only this outcome remains plausible/i)).toBeInTheDocument();
  });

  it("never states a per-prediction confidence percentage as a correctness probability", () => {
    const { reliability } = makePrediction();
    render(<UncertaintyPanel conformal={reliability.conformal} endpoint="herg_inhibition" />);
    expect(screen.getByText(/population-level coverage guarantee/i)).toBeInTheDocument();
    expect(screen.queryByText(/90% confidence this prediction is correct/i)).not.toBeInTheDocument();
  });

  it("explains a non-singleton (ambiguous) result honestly", () => {
    const prediction = makePrediction({
      reliability: {
        ...makePrediction().reliability,
        conformal: {
          predicted_set: ["blocker", "non_blocker"],
          p_value_blocker: 0.15,
          p_value_non_blocker: 0.2,
          nominal_confidence: 0.9,
          is_singleton: false,
          method: "split_conformal_prediction",
        },
      },
    });
    render(<UncertaintyPanel conformal={prediction.reliability.conformal} endpoint="herg_inhibition" />);
    expect(screen.getByText(/both outcomes remain plausible/i)).toBeInTheDocument();
  });

  it("maps a non-hERG endpoint's own label vocabulary", () => {
    const conformal = {
      predicted_set: ["inhibitor"],
      p_value_blocker: 0.7,
      p_value_non_blocker: 0.05,
      nominal_confidence: 0.9,
      is_singleton: true,
      method: "split_conformal_prediction",
    };
    render(<UncertaintyPanel conformal={conformal} endpoint="cyp3a4_inhibition" />);
    expect(screen.getByText(/predicted cyp3a4 inhibitor/i)).toBeInTheDocument();
  });
});
