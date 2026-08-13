import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { ErrorPanel } from "./ErrorPanel";
import { ApiError } from "../api/client";

describe("ErrorPanel", () => {
  it("announces itself as an alert for assistive technology", () => {
    render(<ErrorPanel error={new ApiError("network", "Could not reach the prediction service.")} />);
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("shows distinct, honest copy for an invalid-molecule (validation) failure", () => {
    render(<ErrorPanel error={new ApiError("validation", "The SMILES string could not be parsed.")} />);
    expect(screen.getByText(/could not be processed/i)).toBeInTheDocument();
    expect(screen.getByText(/the smiles string could not be parsed/i)).toBeInTheDocument();
  });

  it("shows distinct copy for a timeout", () => {
    render(<ErrorPanel error={new ApiError("timeout", "The prediction service did not respond in time.")} />);
    expect(screen.getByText(/took too long/i)).toBeInTheDocument();
  });

  it("shows distinct copy for an unavailable service, without fabricating a result", () => {
    render(<ErrorPanel error={new ApiError("unavailable", "The model could not be loaded.")} />);
    expect(screen.getByText(/temporarily unavailable/i)).toBeInTheDocument();
  });

  it("invokes onRetry when the retry button is pressed", async () => {
    const user = userEvent.setup();
    const onRetry = vi.fn();
    render(<ErrorPanel error={new ApiError("server_error", "Unexpected error.")} onRetry={onRetry} />);
    await user.click(screen.getByRole("button", { name: /try again/i }));
    expect(onRetry).toHaveBeenCalled();
  });
});
