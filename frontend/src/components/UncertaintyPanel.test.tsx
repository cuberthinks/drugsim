import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { UncertaintyPanel } from "./UncertaintyPanel";
import { makePrediction } from "../test/fixtures";

describe("UncertaintyPanel", () => {
  it("shows the predicted set label for a singleton result", () => {
    const { reliability } = makePrediction();
    render(<UncertaintyPanel conformal={reliability.conformal} endpoint="herg_inhibition" />);
    // Restricted to the pill badge specifically: this revision also shows
    // the same label text again as a p-value row caption further down, so
    // an unrestricted query now matches both, correctly.
    expect(screen.getByText(/predicted non-inhibitor/i, { selector: "span" })).toBeInTheDocument();
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
    expect(screen.getByText(/predicted cyp3a4 inhibitor/i, { selector: "span" })).toBeInTheDocument();
  });

  it("shows both raw p-values from the API response, not just the predicted set", () => {
    const { reliability } = makePrediction();
    render(<UncertaintyPanel conformal={reliability.conformal} endpoint="herg_inhibition" />);
    // Fixture: p_value_blocker 0.03, p_value_non_blocker 0.62 -- both real
    // numbers from the response, not derived/rounded/invented.
    expect(screen.getByText("0.030")).toBeInTheDocument();
    expect(screen.getByText("0.620")).toBeInTheDocument();
  });

  it("labels each p-value with the class it belongs to, not just 'blocker'/'non_blocker'", () => {
    const conformal = {
      predicted_set: ["inhibitor"],
      p_value_blocker: 0.7,
      p_value_non_blocker: 0.05,
      nominal_confidence: 0.9,
      is_singleton: true,
      method: "split_conformal_prediction",
    };
    render(<UncertaintyPanel conformal={conformal} endpoint="cyp3a4_inhibition" />);
    expect(screen.getByText(/p-value.*predicted cyp3a4 inhibitor/i)).toBeInTheDocument();
    expect(screen.getByText(/p-value.*predicted non-inhibitor/i)).toBeInTheDocument();
  });

  it("explains what a conformal p-value means in plain English", () => {
    const { reliability } = makePrediction();
    render(<UncertaintyPanel conformal={reliability.conformal} endpoint="herg_inhibition" />);
    expect(screen.getByText(/what is a p-value here/i)).toBeInTheDocument();
    expect(
      screen.getByText(/fraction of training examples that look more extreme than your molecule/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/a low p-value means the model strongly doubts that class/i)).toBeInTheDocument();
  });
});
