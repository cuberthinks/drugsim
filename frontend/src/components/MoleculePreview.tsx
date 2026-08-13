import { MoleculeStructure } from "./MoleculeStructure";
import type { MoleculeInfo } from "../api/types";

interface Props {
  molecule: MoleculeInfo;
  /** User-supplied label (e.g. "Aspirin") -- purely for display, never sent
   * to or returned by the backend. Optional; omitted entirely when blank. */
  name?: string;
}

/**
 * Shows what the backend understood the input to be, before any prediction
 * is made. Everything here is input/structural information returned by the
 * standardisation pipeline — no predicted values appear in this component,
 * so the boundary between "what you gave us" and "what the model predicts"
 * (spec section 4) stays visually distinct from PredictionResults.
 */
export function MoleculePreview({ molecule, name }: Props) {
  return (
    <section aria-labelledby="molecule-preview-heading" className="rounded-lg border border-line bg-white p-6">
      <h2 id="molecule-preview-heading" className="font-display text-xl font-semibold text-ink">
        Molecule
      </h2>
      {name?.trim() && <p className="mt-1 text-base font-medium text-ink">{name.trim()}</p>}
      <p className="mt-1 text-xs font-medium tracking-wide text-ink-soft uppercase">Input information</p>

      <div className="mt-4 grid gap-6 sm:grid-cols-[320px_1fr]">
        <MoleculeStructure smiles={molecule.canonical_smiles} />
        <dl className="grid gap-4 content-start">
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Canonical SMILES</dt>
            <dd className="mt-1 font-mono text-sm break-all text-ink">{molecule.canonical_smiles}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Molecular formula</dt>
            <dd className="mt-1 font-mono text-sm text-ink">{molecule.molecular_formula}</dd>
          </div>
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">InChIKey</dt>
            <dd className="mt-1 font-mono text-sm break-all text-ink">{molecule.inchikey_full}</dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
