import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ApplicabilityDomainGauge } from "./ApplicabilityDomainGauge";
import { makePrediction } from "../test/fixtures";

describe("ApplicabilityDomainGauge", () => {
  it("defines what applicability domain measures at the point of use, not only elsewhere on the page", () => {
    const { reliability } = makePrediction();
    render(<ApplicabilityDomainGauge applicabilityDomain={reliability.applicability_domain} />);
    expect(
      screen.getByText(/how closely this molecule resembles the chemistry the model was actually trained on/i),
    ).toBeInTheDocument();
  });

  it("labels an in-domain verdict as known chemistry and shows the real rationale", () => {
    const { reliability } = makePrediction();
    render(<ApplicabilityDomainGauge applicabilityDomain={reliability.applicability_domain} />);
    expect(screen.getByText(/within known chemistry/i)).toBeInTheDocument();
    // The rationale is shown formatted as a bullet list, not the raw
    // sentence verbatim in one block -- but every word of it must still
    // appear, unaltered, somewhere in that list (this revision: "make sure
    // the raw rationale string ... is formatted nicely as bullet points").
    const rationaleWithoutTrailingPeriod = reliability.applicability_domain.rationale.replace(/\.$/, "");
    expect(
      screen.getByText(
        (_, node) => !!node?.textContent?.includes(rationaleWithoutTrailingPeriod),
        { selector: "li" },
      ),
    ).toBeInTheDocument();
  });

  it("splits a multi-clause rationale into one bullet per clause", () => {
    const applicabilityDomain = {
      verdict: "out_of_domain" as const,
      max_tanimoto_to_training: 0.32,
      knn_distance: 2.56,
      knn_distance_threshold: 1.74,
      scaffold_seen_in_training: true,
      rationale:
        "Maximum similarity to any training compound is 0.32; scaffold is present in the training set; " +
        "descriptor-space distance to nearest training neighbours is 2.56 (training-internal threshold 1.74).",
      method: "tanimoto_knn_distance_scaffold_membership",
    };
    render(<ApplicabilityDomainGauge applicabilityDomain={applicabilityDomain} />);
    const items = screen.getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(items[0]).toHaveTextContent(/maximum similarity to any training compound is 0\.32/i);
    expect(items[1]).toHaveTextContent(/scaffold is present in the training set/i);
    expect(items[2]).toHaveTextContent(/descriptor-space distance to nearest training neighbours is 2\.56/i);
  });

  it("explains why a common, simple molecule can still be flagged as novel chemistry", () => {
    const applicabilityDomain = {
      verdict: "out_of_domain" as const,
      max_tanimoto_to_training: 0.2,
      knn_distance: 3.0,
      knn_distance_threshold: 1.5,
      scaffold_seen_in_training: false,
      rationale: "This structure is substantially different from the training chemistry.",
      method: "tanimoto_knn_distance_scaffold_membership",
    };
    render(<ApplicabilityDomainGauge applicabilityDomain={applicabilityDomain} />);
    expect(screen.getByText(/paracetamol or aspirin/i)).toBeInTheDocument();
  });

  it("does not show the simple-molecule note when the structure is within known chemistry", () => {
    const { reliability } = makePrediction();
    render(<ApplicabilityDomainGauge applicabilityDomain={reliability.applicability_domain} />);
    expect(screen.queryByText(/paracetamol or aspirin/i)).not.toBeInTheDocument();
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
