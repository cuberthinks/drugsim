import type { CompoundIdentity as CompoundIdentityInfo } from "../api/types";

interface Props {
  identity: CompoundIdentityInfo;
}

/**
 * DrugSim's own verified compound identity -- resolved offline against a
 * committed PubChem snapshot (see src/drugsim_identity), never invented,
 * never a live lookup. Deliberately separate from any free-text label the
 * user typed for their own submission (that stays in MoleculePreview's
 * `name` prop): this component only ever shows what DrugSim itself has
 * verified, so IDENTITY and the user's own annotation are never conflated.
 *
 * "Unidentified" is the normal outcome for a novel compound outside the
 * snapshot, not an error -- rendered plainly, with no implication that
 * something went wrong.
 */
export function CompoundIdentity({ identity }: Props) {
  if (identity.identity_status === "unidentified") {
    return (
      <section aria-labelledby="compound-identity-heading" className="card p-6">
        <h2 id="compound-identity-heading" className="font-display text-xl font-semibold text-ink">
          Unidentified Compound
        </h2>
        <p className="mt-1 text-xs font-medium tracking-wide text-ink-soft uppercase">Verified identity</p>
        <dl className="mt-4 grid gap-2 text-sm">
          <div className="flex items-center gap-2">
            <dt className="text-ink-soft">Structure validated</dt>
            <dd className="font-medium text-ink">✓</dd>
          </div>
          <div className="flex items-center gap-2">
            <dt className="text-ink-soft">Verified identity</dt>
            <dd className="font-medium text-ink">Not found</dd>
          </div>
        </dl>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          DrugSim could not match this structure to a known compound in its reference data. This
          does not affect prediction -- a valid, novel molecule can still be predicted below.
        </p>
      </section>
    );
  }

  return (
    <section aria-labelledby="compound-identity-heading" className="card p-6">
      <h2 id="compound-identity-heading" className="font-display text-xl font-semibold text-ink">
        {identity.compound_name}
      </h2>
      <p className="mt-1 text-xs font-medium tracking-wide text-ink-soft uppercase">Verified identity</p>

      <p className="mt-3 text-sm leading-relaxed text-ink">{identity.description}</p>

      <dl className="mt-4 grid gap-4 sm:grid-cols-2">
        {identity.synonyms && identity.synonyms.length > 0 && (
          <div className="sm:col-span-2">
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Synonyms</dt>
            <dd className="mt-1 text-sm text-ink">{identity.synonyms.join(", ")}</dd>
          </div>
        )}
        {identity.identifiers && Object.keys(identity.identifiers).length > 0 && (
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Database identifiers</dt>
            <dd className="mt-1 font-mono text-sm text-ink">
              {Object.entries(identity.identifiers)
                .map(([source, id]) => `${source}: ${id}`)
                .join(", ")}
            </dd>
          </div>
        )}
        {identity.source && (
          <div>
            <dt className="text-xs font-medium tracking-wide text-ink-soft uppercase">Source</dt>
            <dd className="mt-1 text-sm text-ink">
              {identity.description_source ?? identity.source}
              {identity.retrieved_at ? ` — retrieved ${identity.retrieved_at}` : ""}
            </dd>
          </div>
        )}
      </dl>
    </section>
  );
}
