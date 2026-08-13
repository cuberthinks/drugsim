import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { MoleculeStructure } from "./MoleculeStructure";

describe("MoleculeStructure", () => {
  it("renders an accessible image for the structure depiction", () => {
    render(<MoleculeStructure smiles="CC(=O)Oc1ccccc1C(=O)O" />);
    expect(screen.getByRole("img")).toBeInTheDocument();
  });

  it("uses a custom accessible label when one is provided", () => {
    render(<MoleculeStructure smiles="CCO" label="Ethanol structure" />);
    expect(screen.getByRole("img", { name: "Ethanol structure" })).toBeInTheDocument();
  });
});
