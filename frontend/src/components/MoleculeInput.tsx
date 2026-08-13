import { useId } from "react";

const EXAMPLE_SMILES = "CC(=O)Oc1ccccc1C(=O)O";
const EXAMPLE_LABEL = "aspirin";

interface Props {
  value: string;
  onChange: (value: string) => void;
  name: string;
  onNameChange: (name: string) => void;
  onValidate: () => void;
  onPredict: () => void;
  onClear: () => void;
  isBusy: boolean;
  isValidated: boolean;
  predictLabel?: string;
}

export function MoleculeInput({
  value,
  onChange,
  name,
  onNameChange,
  onValidate,
  onPredict,
  onClear,
  isBusy,
  isValidated,
  predictLabel = "Predict",
}: Props) {
  const inputId = useId();
  const nameInputId = useId();

  return (
    <div className="rounded-lg border border-line bg-white p-6">
      <label htmlFor={nameInputId} className="text-sm font-medium text-ink">
        Compound name <span className="font-normal text-ink-soft">(optional)</span>
      </label>
      <input
        id={nameInputId}
        type="text"
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        placeholder="e.g. Aspirin"
        className="mt-2 w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink focus:border-signal"
      />
      <p className="mt-1 text-xs text-ink-soft">
        For your own reference only — shown alongside the result, never sent to the prediction
        engine and never used in the prediction itself.
      </p>

      <label htmlFor={inputId} className="mt-5 block text-sm font-medium text-ink">
        Molecule (SMILES)
      </label>
      <textarea
        id={inputId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        spellCheck={false}
        placeholder={`e.g. ${EXAMPLE_SMILES}`}
        className="mt-2 w-full resize-none rounded-md border border-line bg-paper px-3 py-2 font-mono text-sm text-ink focus:border-signal"
      />
      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <button
          type="button"
          onClick={() => {
            onChange(EXAMPLE_SMILES);
            if (!name.trim()) onNameChange("Aspirin");
          }}
          className="text-xs text-ink-soft underline underline-offset-2 hover:text-ink"
        >
          Use example ({EXAMPLE_LABEL})
        </button>
        <p className="text-xs text-ink-soft">Supported format: SMILES</p>
      </div>

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onValidate}
          disabled={isBusy || value.trim().length === 0}
          className="rounded-md border border-line bg-white px-5 py-2.5 text-sm font-medium text-ink hover:bg-paper-alt disabled:cursor-not-allowed disabled:opacity-50"
        >
          {isBusy ? "Validating…" : "Validate"}
        </button>
        <button
          type="button"
          onClick={onPredict}
          disabled={isBusy || !isValidated}
          className="rounded-md bg-ink px-5 py-2.5 text-sm font-medium text-paper hover:opacity-90 disabled:cursor-not-allowed disabled:opacity-40"
          title={!isValidated ? "Validate the molecule first" : undefined}
        >
          {isBusy ? "Predicting…" : predictLabel}
        </button>
        <button
          type="button"
          onClick={onClear}
          disabled={isBusy || value.trim().length === 0}
          className="rounded-md px-5 py-2.5 text-sm font-medium text-ink-soft hover:text-ink disabled:cursor-not-allowed disabled:opacity-50"
        >
          Clear
        </button>
      </div>
    </div>
  );
}
