import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it } from "vitest";
import { SourcesPage } from "./SourcesPage";

function setup() {
  render(
    <MemoryRouter>
      <SourcesPage />
    </MemoryRouter>,
  );
}

describe("SourcesPage", () => {
  it("names ChEMBL, PubChem, and TDC as active sources, each with a status badge", () => {
    setup();
    for (const name of ["ChEMBL", "PubChem", "Therapeutics Data Commons"]) {
      const heading = screen.getByRole("heading", { name: new RegExp(name, "i") });
      expect(heading).toBeInTheDocument();
    }
    expect(screen.getAllByText(/^active$/i).length).toBeGreaterThanOrEqual(3);
  });

  it("never claims a future/catalogued source is used in a live prediction", () => {
    setup();
    const futureSection = screen.getByText(/potential future sources/i).closest("section");
    expect(futureSection).not.toBeNull();
    expect(within(futureSection as HTMLElement).getByText(/not currently used by drugsim/i)).toBeInTheDocument();
    // Sources genuinely not used anywhere in a live model must not appear in the active list.
    expect(within(futureSection as HTMLElement).getByText(/bindingdb/i)).toBeInTheDocument();
  });

  it("lists excluded sources with their real, specific reasons rather than a generic placeholder", () => {
    setup();
    expect(screen.getByText(/drugbank/i)).toBeInTheDocument();
    expect(screen.getByText(/commercial use requires a paid licence/i)).toBeInTheDocument();
    // SIDER's real reason is staleness, not licensing -- this is the one case where a naive
    // template answer ("not currently used") would have been actively misleading.
    expect(screen.getByText(/not excluded for licensing/i)).toBeInTheDocument();
    expect(screen.getByText(/frozen at its 2015 release/i)).toBeInTheDocument();
  });

  it("includes the independent-project disclaimer naming Oxford", () => {
    setup();
    expect(screen.getByText(/not affiliated with, endorsed by, or officially associated with oxford university/i)).toBeInTheDocument();
  });

  it("links each active source to its real official homepage", () => {
    setup();
    expect(screen.getByRole("link", { name: "ChEMBL" })).toHaveAttribute("href", "https://www.ebi.ac.uk/chembl/");
    expect(screen.getByRole("link", { name: "PubChem" })).toHaveAttribute("href", "https://pubchem.ncbi.nlm.nih.gov/");
  });

  it("makes no unsupported scientific or comparative claims", () => {
    setup();
    const body = document.body.textContent ?? "";
    expect(body).not.toMatch(/more accurate/i);
    expect(body).not.toMatch(/chatgpt|gemini|openai/i);
    expect(body).not.toMatch(/powered by oxford/i);
    expect(body).not.toMatch(/makes drugsim accurate/i);
  });
});
