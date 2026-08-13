import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { WarningsList } from "./WarningsList";

describe("WarningsList", () => {
  it("renders nothing when there are no warnings", () => {
    const { container } = render(<WarningsList warnings={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("renders each warning's message", () => {
    render(
      <WarningsList
        warnings={[
          { code: "low_similarity", severity: "medium", message: "Similarity to training data is low.", field: "structure" },
        ]}
      />,
    );
    expect(screen.getByText(/similarity to training data is low/i)).toBeInTheDocument();
  });
});
