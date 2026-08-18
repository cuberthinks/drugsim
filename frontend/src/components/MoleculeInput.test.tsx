import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { MoleculeInput } from "./MoleculeInput";

function setup(overrides: Partial<React.ComponentProps<typeof MoleculeInput>> = {}) {
  const props = {
    value: "",
    onChange: vi.fn(),
    name: "",
    onNameChange: vi.fn(),
    onValidate: vi.fn(),
    onPredict: vi.fn(),
    onClear: vi.fn(),
    isBusy: false,
    isValidated: false,
    ...overrides,
  };
  render(<MoleculeInput {...props} />);
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

  it("fills in the example molecule when the example link is used", async () => {
    const user = userEvent.setup();
    const props = setup();
    await user.click(screen.getByRole("button", { name: /use example/i }));
    expect(props.onChange).toHaveBeenCalledWith("CC(=O)Oc1ccccc1C(=O)O");
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

  it("fills in the example name alongside the example structure when no name was set", async () => {
    const user = userEvent.setup();
    const props = setup({ name: "" });
    await user.click(screen.getByRole("button", { name: /use example/i }));
    expect(props.onNameChange).toHaveBeenCalledWith("Aspirin");
  });

  it("does not overwrite a name the user already typed when using the example", async () => {
    const user = userEvent.setup();
    const props = setup({ name: "My custom label" });
    await user.click(screen.getByRole("button", { name: /use example/i }));
    expect(props.onNameChange).not.toHaveBeenCalled();
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

  it("only claims the format DrugSim actually accepts", () => {
    setup();
    expect(screen.getByText(/accepted format: smiles/i)).toBeInTheDocument();
    expect(screen.queryByText(/molblock|inchi/i)).not.toBeInTheDocument();
  });
});
