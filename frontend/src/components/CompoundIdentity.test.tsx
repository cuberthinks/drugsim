import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { CompoundIdentity } from "./CompoundIdentity";
import type { CompoundIdentity as CompoundIdentityInfo } from "../api/types";

const IDENTIFIED: CompoundIdentityInfo = {
  identity_status: "identified",
  compound_name: "Caffeine",
  synonyms: ["1,3,7-Trimethylxanthine", "Guaranine"],
  identifiers: { pubchem_cid: "2519" },
  description: "A central nervous system stimulant of the methylxanthine class.",
  description_source: "PubChem (ChEBI)",
  source: "PubChem",
  retrieved_at: "2026-08-30T00:00:00Z",
};

const UNIDENTIFIED: CompoundIdentityInfo = {
  identity_status: "unidentified",
  compound_name: null,
  synonyms: null,
  identifiers: null,
  description: null,
  description_source: null,
  source: null,
  retrieved_at: null,
};

describe("CompoundIdentity", () => {
  it("renders the compound name, description, synonyms, identifiers, and source when identified", () => {
    render(<CompoundIdentity identity={IDENTIFIED} />);
    expect(screen.getByRole("heading", { name: "Caffeine" })).toBeInTheDocument();
    expect(screen.getByText(/central nervous system stimulant/)).toBeInTheDocument();
    expect(screen.getByText(/1,3,7-Trimethylxanthine, Guaranine/)).toBeInTheDocument();
    expect(screen.getByText(/pubchem_cid: 2519/)).toBeInTheDocument();
    expect(screen.getByText(/PubChem/)).toBeInTheDocument();
  });

  it("shows a placeholder description rather than blank text when identified but description is unavailable", () => {
    render(
      <CompoundIdentity
        identity={{ ...IDENTIFIED, description: "Verified description unavailable.", description_source: null }}
      />,
    );
    expect(screen.getByText("Verified description unavailable.")).toBeInTheDocument();
  });

  it("renders the unidentified state plainly, without implying an error", () => {
    render(<CompoundIdentity identity={UNIDENTIFIED} />);
    expect(screen.getByRole("heading", { name: "Unidentified Compound" })).toBeInTheDocument();
    expect(screen.getByText("✓")).toBeInTheDocument();
    expect(screen.getByText("Not found")).toBeInTheDocument();
    expect(screen.getByText(/could not match this structure/)).toBeInTheDocument();
    expect(screen.getByText(/can still be predicted/)).toBeInTheDocument();
  });

  it("omits the synonyms row entirely when there are none, rather than showing an empty list", () => {
    render(<CompoundIdentity identity={{ ...IDENTIFIED, synonyms: null }} />);
    expect(screen.queryByText("Synonyms")).not.toBeInTheDocument();
  });
});
