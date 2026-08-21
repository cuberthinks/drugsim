import { useId } from "react";
import { EXAMPLE_COMPOUNDS, type ExampleCompound } from "../lib/exampleCompounds";

const EXAMPLE_SMILES = EXAMPLE_COMPOUNDS[0].smiles;

interface Props {
  value: string;
  onChange: (value: string) => void;
  name: string;
  onNameChange: (name: string) => void;
  onValidate: () => void;
  onPredict: () => void;
  onClear: () => void;
  /** Fills the structure/name AND immediately runs a real prediction against
   * the live model — a single live API call, not a canned/cached result
   * (see PredictPage's handleUseExample). */
  onUseExample: (example: ExampleCompound) => void;
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
  onUseExample,
  isBusy,
  isValidated,
  predictLabel = "Predict",
}: Props) {
  const inputId = useId();
  const nameInputId = useId();

  return (
    <div className="card p-6">
      <label htmlFor={nameInputId} className="text-sm font-medium text-ink">
        Compound name <span className="font-normal text-ink-soft">(optional)</span>
      </label>
      <input
        id={nameInputId}
        type="text"
        value={name}
        onChange={(e) => onNameChange(e.target.value)}
        placeholder="e.g. Aspirin"
        className="mt-2 w-full rounded-md border border-line bg-paper px-3 py-2 text-sm text-ink transition-[border-color,box-shadow] duration-150 focus:border-signal focus:shadow-[0_0_0_3px_var(--color-signal-soft)]"
      />
      <p className="mt-1 text-xs text-ink-soft">
        For your own reference only — shown alongside the result, never sent to the prediction
        engine and never used in the prediction itself.
      </p>

      <label htmlFor={inputId} className="mt-5 block text-sm font-medium text-ink">
        Enter a chemical structure — paste a SMILES string
      </label>
      <textarea
        id={inputId}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        rows={3}
        spellCheck={false}
        placeholder={`e.g. ${EXAMPLE_SMILES}`}
        className="mt-2 w-full resize-none rounded-md border border-line bg-paper px-3 py-2 font-mono text-sm text-ink transition-[border-color,box-shadow] duration-150 focus:border-signal focus:shadow-[0_0_0_3px_var(--color-signal-soft)]"
      />
      <div className="mt-2 flex justify-end">
        <p className="text-xs text-ink-soft">Accepted format: SMILES</p>
      </div>

      <div className="mt-3">
        <p className="text-xs font-medium text-ink">Try an example</p>
        <p className="mt-1 text-xs leading-relaxed text-ink-soft">
          Four real compounds chosen to show different actual outcomes — not hypothetical
          scenarios. Clicking one runs a real prediction immediately, the same as clicking
          Predict yourself.
        </p>
        <div className="mt-2 grid gap-2 sm:grid-cols-2">
          {EXAMPLE_COMPOUNDS.map((example) => (
            <button
              key={example.name}
              type="button"
              onClick={() => onUseExample(example)}
              disabled={isBusy}
              title={example.note}
              className="card-interactive rounded-md border border-line bg-paper-alt px-3 py-2 text-left text-xs hover:bg-signal-soft disabled:cursor-not-allowed disabled:opacity-50"
            >
              <span className="font-medium text-ink">{example.name}</span>
              <span className="mt-0.5 block leading-relaxed text-ink-soft">{example.note}</span>
            </button>
          ))}
        </div>
      </div>

      <details className="mt-2 text-xs text-ink-soft">
        <summary className="cursor-pointer select-none font-medium text-ink hover:underline">
          Don't know what SMILES is?
        </summary>
        <div className="mt-2 space-y-2 leading-relaxed">
          <p>
            SMILES (Simplified Molecular Input Line Entry System) is a short line of text that
            represents a molecule's structure — for example, <code className="font-mono">CCO</code> is
            ethanol. It's the standard way chemistry software exchanges structures as plain text.
          </p>
          <p>
            If you have a compound in mind but not its SMILES: search the compound's name on{" "}
            <a
              href="https://pubchem.ncbi.nlm.nih.gov/"
              target="_blank"
              rel="noopener noreferrer"
              className="underline underline-offset-2 hover:text-ink"
            >
              PubChem
            </a>{" "}
            and copy the SMILES text from its record page, then paste it above.
          </p>
        </div>
      </details>

      <div className="mt-5 flex flex-wrap gap-3">
        <button
          type="button"
          onClick={onValidate}
          disabled={isBusy || value.trim().length === 0}
          className="rounded-md border border-line bg-white px-5 py-2.5 text-sm font-medium text-ink shadow-sm transition-[box-shadow,transform,background-color] duration-200 hover:-translate-y-0.5 hover:bg-paper-alt hover:shadow-md disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 disabled:hover:shadow-sm"
        >
          {isBusy ? "Validating…" : "Validate"}
        </button>
        <button
          type="button"
          onClick={onPredict}
          disabled={isBusy || !isValidated}
          className="rounded-md bg-ink px-5 py-2.5 text-sm font-medium text-paper shadow-sm transition-[box-shadow,transform,opacity] duration-200 hover:-translate-y-0.5 hover:opacity-90 hover:shadow-md disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:translate-y-0 disabled:hover:shadow-sm"
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
