import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { MoleculeInput } from "./MoleculeInput";
import { EXAMPLE_COMPOUNDS } from "../lib/exampleCompounds";

function setup(overrides: Partial<React.ComponentProps<typeof MoleculeInput>> = {}) {
  const props = {
    value: "",
    onChange: vi.fn(),
    name: "",
    onNameChange: vi.fn(),
    onValidate: vi.fn(),
    onPredict: vi.fn(),
    onClear: vi.fn(),
    onUseExample: vi.fn(),
    isBusy: false,
    isValidated: false,
    ...overrides,
  };
  render(
    <MemoryRouter>
      <MoleculeInput {...props} />
    </MemoryRouter>,
  );
  return props;
}

describe("MoleculeInput", () => {
  it("renders a labelled molecule input field", () => {
    setup();
    expect(screen.getByLabelText(/paste a smiles string/i)).toBeInTheDocument();
  });

  it("disables Validate, Predict, and Clear when the field is empty", () => {
    setup({ value: "" });
    expect(screen.getByRole("button", { name: /validate/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /predict/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /clear/i })).toBeDisabled();
  });

  it("enables Validate once text is entered, but keeps Predict disabled until validated", () => {
    setup({ value: "CCO", isValidated: false });
    expect(screen.getByRole("button", { name: /validate/i })).toBeEnabled();
    expect(screen.getByRole("button", { name: /predict/i })).toBeDisabled();
  });

  it("enables Predict once the molecule has been validated", () => {
    setup({ value: "CCO", isValidated: true });
    expect(screen.getByRole("button", { name: /predict/i })).toBeEnabled();
  });

  it("delegates to onUseExample with the full example when clicked -- filling and running are the parent's job, not this component's", async () => {
    const user = userEvent.setup();
    const props = setup();
    const first = EXAMPLE_COMPOUNDS[0];
    await user.click(screen.getByRole("button", { name: new RegExp(`^${first.name}`, "i") }));
    expect(props.onUseExample).toHaveBeenCalledWith(first);
    // Filling the field directly is no longer this component's job -- see
    // PredictPage.handleUseExample, which also runs a real prediction.
    expect(props.onChange).not.toHaveBeenCalled();
  });

  it("disables example buttons while a request is already in flight", () => {
    setup({ isBusy: true });
    const first = EXAMPLE_COMPOUNDS[0];
    expect(screen.getByRole("button", { name: new RegExp(`^${first.name}`, "i") })).toBeDisabled();
  });

  it("offers a small, varied set of real example compounds, each labelled as an example", () => {
    setup();
    expect(EXAMPLE_COMPOUNDS.length).toBeGreaterThanOrEqual(2);
    for (const example of EXAMPLE_COMPOUNDS) {
      expect(screen.getByRole("button", { name: new RegExp(`^${example.name}`, "i") })).toBeInTheDocument();
    }
  });

  it("calls onClear when Clear is pressed", async () => {
    const user = userEvent.setup();
    const props = setup({ value: "CCO" });
    await user.click(screen.getByRole("button", { name: /clear/i }));
    expect(props.onClear).toHaveBeenCalled();
  });

  it("shows a busy label and disables actions while a request is in flight", () => {
    setup({ value: "CCO", isBusy: true, isValidated: true });
    expect(screen.getByRole("button", { name: /validating/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /predicting/i })).toBeDisabled();
  });

  it("renders an optional compound name field and reports changes via onNameChange", async () => {
    const user = userEvent.setup();
    const props = setup();
    const nameField = screen.getByLabelText(/compound name/i);
    expect(nameField).toBeInTheDocument();
    await user.type(nameField, "Aspirin");
    expect(props.onNameChange).toHaveBeenCalledWith("A");
  });

  it("explains what SMILES is and how to obtain one, for a user who has never heard the term", () => {
    setup();
    expect(screen.getByText(/don't know what smiles is/i)).toBeInTheDocument();
    expect(screen.getByText(/simplified molecular input line entry system/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /pubchem/i })).toHaveAttribute(
      "href",
      "https://pubchem.ncbi.nlm.nih.gov/",
    );
  });

  it("discloses how the submitted structure is handled, with a link to the full policy", () => {
    setup();
    expect(screen.getByText(/never uses submitted structures to train its models/i)).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /full privacy policy/i })).toHaveAttribute("href", "/privacy");
  });

  it("only claims the format DrugSim actually accepts", () => {
    setup();
    expect(screen.getByText(/accepted format: smiles/i)).toBeInTheDocument();
    expect(screen.queryByText(/molblock|inchi/i)).not.toBeInTheDocument();
  });
});
