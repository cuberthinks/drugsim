import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, describe, expect, it } from "vitest";
import { HowThisWorksGuide } from "./HowThisWorksGuide";

describe("HowThisWorksGuide", () => {
  afterEach(() => {
    window.localStorage.clear();
  });

  it("is open by default for a first-time visitor", () => {
    render(<HowThisWorksGuide />);
    expect(screen.getByRole("list", { name: /how this works/i })).toBeInTheDocument();
  });

  it("collapses when the toggle is clicked", async () => {
    const user = userEvent.setup();
    render(<HowThisWorksGuide />);

    const toggle = screen.getByRole("button", { name: /how this works/i });
    expect(toggle).toHaveAttribute("aria-expanded", "true");

    await user.click(toggle);
    expect(toggle).toHaveAttribute("aria-expanded", "false");
    expect(screen.queryByRole("list", { name: /how this works/i })).not.toBeInTheDocument();
  });

  it("starts collapsed on a fresh mount if the user previously collapsed it", () => {
    window.localStorage.setItem("drugsim_how_it_works_open_v1", "false");
    render(<HowThisWorksGuide />);
    expect(screen.queryByRole("list", { name: /how this works/i })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /how this works/i })).toHaveAttribute("aria-expanded", "false");
  });

  it("starts open on a fresh mount if the user previously reopened it", () => {
    window.localStorage.setItem("drugsim_how_it_works_open_v1", "true");
    render(<HowThisWorksGuide />);
    expect(screen.getByRole("list", { name: /how this works/i })).toBeInTheDocument();
  });
});
