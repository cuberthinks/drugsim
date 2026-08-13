import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApplicabilityDomainGauge } from "./ApplicabilityDomainGauge";
import { makePrediction } from "../test/fixtures";

describe("ApplicabilityDomainGauge", () => {
  it("labels an in-domain verdict as known chemistry and shows the real rationale", () => {
    const { reliability } = makePrediction();
    render(<ApplicabilityDomainGauge applicabilityDomain={reliability.applicability_domain} />);
    expect(screen.getByText(/within known chemistry/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        (_, node) => !!node?.textContent?.includes(reliability.applicability_domain.rationale),
        { selector: "p" },
      ),
    ).toBeInTheDocument();
  });

  it("leads with the plain-language verdict description, not just the raw backend rationale", () => {
    const { reliability } = makePrediction();
    render(<ApplicabilityDomainGauge applicabilityDomain={reliability.applicability_domain} />);
    // Phase 7 finding: this plain-language sentence existed in the code but
    // was never rendered -- a heuristic non-cheminformatics-persona review
    // caught it. Pinned here so it cannot silently regress to dead code.
    expect(
      screen.getByText(/this structure closely resembles compounds the model was trained on/i),
    ).toBeInTheDocument();
    expect(screen.getByText(/supporting detail from the model/i)).toBeInTheDocument();
  });

  it("never implies applicability domain means the prediction is biologically correct", () => {
    const { reliability } = makePrediction();
    render(<ApplicabilityDomainGauge applicabilityDomain={reliability.applicability_domain} />);
    expect(screen.getByText(/does not mean the prediction itself is biologically correct/i)).toBeInTheDocument();
  });

  it("labels an out-of-domain verdict as novel chemistry", () => {
    const applicabilityDomain = {
      verdict: "out_of_domain" as const,
      max_tanimoto_to_training: 0.18,
      knn_distance: 2.1,
      knn_distance_threshold: 0.6,
      scaffold_seen_in_training: false,
      rationale: "This structure is substantially different from the training chemistry.",
      method: "tanimoto_knn_distance_scaffold_membership",
    };
    render(<ApplicabilityDomainGauge applicabilityDomain={applicabilityDomain} />);
    // "Novel chemistry" appears both as the verdict label and as the gauge's
    // fixed axis endpoint, so assert presence rather than a single match.
    expect(screen.getAllByText(/novel chemistry/i).length).toBeGreaterThan(0);
  });

  it("renders the gauge as an accessible image with a descriptive label", () => {
    const { reliability } = makePrediction();
    render(<ApplicabilityDomainGauge applicabilityDomain={reliability.applicability_domain} />);
    expect(screen.getByRole("img", { name: /applicability domain/i })).toBeInTheDocument();
  });
});
