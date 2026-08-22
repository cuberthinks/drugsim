import { Link } from "react-router-dom";
import { ACTIVE_SOURCES, DEFERRED_SOURCE_NAMES, EXCLUDED_SOURCES, FUTURE_SOURCES } from "../lib/dataSources";

function ExternalLink({ href, children }: { href: string; children: React.ReactNode }) {
  return (
    <a href={href} target="_blank" rel="noopener noreferrer" className="underline underline-offset-2 hover:text-ink">
      {children}
    </a>
  );
}

export function SourcesPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">References</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">Data Sources &amp; References</h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          DrugSim is built using publicly available scientific resources and datasets. Sources are
          used for chemical and bioactivity information where applicable — this page names exactly
          which ones, and states plainly which are not currently used.
        </p>
      </header>

      <section className="flex flex-col gap-4">
        <h2 className="font-display text-lg font-semibold text-ink">Primary data sources</h2>
        <p className="text-sm leading-relaxed text-ink-soft">
          The only sources that genuinely produced training or validation data for a live model.
        </p>
        {ACTIVE_SOURCES.map((source) => (
          <div key={source.id} className="card p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-display text-base font-semibold text-ink">
                {source.officialUrl ? <ExternalLink href={source.officialUrl}>{source.name}</ExternalLink> : source.name}
              </h3>
              <span className="rounded-full bg-signal-soft px-2.5 py-0.5 font-mono text-[11px] font-medium tracking-wide text-signal uppercase">
                Active
              </span>
            </div>
            <p className="mt-1 text-xs text-ink-soft">{source.provider}</p>
            <p className="mt-2 text-sm leading-relaxed text-ink-soft">{source.purpose}</p>
            {source.usedIn && (
              <p className="mt-2 text-sm leading-relaxed text-ink">
                <span className="font-medium">Used for:</span> {source.usedIn}
              </p>
            )}
            <dl className="mt-3 grid grid-cols-1 gap-2 text-xs text-ink-soft sm:grid-cols-3">
              {source.license && (
                <div>
                  <dt className="font-medium text-ink">Licence</dt>
                  <dd>{source.license}</dd>
                </div>
              )}
              {source.lastVerified && (
                <div>
                  <dt className="font-medium text-ink">Last verified</dt>
                  <dd className="font-mono">{source.lastVerified}</dd>
                </div>
              )}
            </dl>
            {source.note && <p className="mt-2 text-xs leading-relaxed text-ink-soft italic">{source.note}</p>}
          </div>
        ))}
      </section>

      <section className="card flex flex-col gap-3 p-5">
        <h2 className="font-display text-lg font-semibold text-ink">Key institutions &amp; providers</h2>
        <p className="text-sm leading-relaxed text-ink-soft">
          Named here only to credit where the data above actually comes from — not to imply any
          collaboration, review, or endorsement (see the disclaimer at the end of this page).
        </p>
        <ul className="mt-1 grid grid-cols-1 gap-x-6 gap-y-1.5 text-sm text-ink-soft sm:grid-cols-2">
          <li>EMBL-EBI — ChEMBL</li>
          <li>National Library of Medicine (NCBI/NIH) — PubChem</li>
          <li>Harvard University (Zitnik Lab) — Therapeutics Data Commons</li>
          <li>UC San Diego — BindingDB</li>
          <li>U.S. EPA — ToxCast / Tox21</li>
          <li>UniProt Consortium — UniProt</li>
          <li>RCSB — Protein Data Bank</li>
          <li>University of New Mexico — DrugCentral</li>
          <li>Open Targets Platform — Open Targets</li>
          <li>U.S. Food and Drug Administration — openFDA</li>
          <li>U.S. National Library of Medicine — DailyMed</li>
        </ul>
      </section>

      <section className="card flex flex-col gap-2 p-5">
        <h2 className="font-display text-lg font-semibold text-ink">Licensing &amp; attribution</h2>
        <p className="text-sm leading-relaxed text-ink-soft">
          Each external dataset is used subject to its own licence, terms of use, and attribution
          requirements — these differ by source and are not uniform across this page. ChEMBL is CC
          BY-SA 3.0; PubChem's own content is US public domain, though individual depositor records
          may carry other terms; Therapeutics Data Commons sets a licence per dataset, and one of
          its datasets (FreeSolv) is explicitly excluded from DrugSim over its own, incompatible
          licence — see below.
        </p>
      </section>

      <section className="flex flex-col gap-4">
        <h2 className="font-display text-lg font-semibold text-ink">Sources not used</h2>
        <p className="text-sm leading-relaxed text-ink-soft">
          Genuinely excluded, each for a specific, verified reason — not a source we simply haven't
          gotten to yet.
        </p>
        {EXCLUDED_SOURCES.map((source) => (
          <div key={source.id} className="rounded-lg border border-line bg-paper-alt p-5">
            <div className="flex flex-wrap items-baseline justify-between gap-2">
              <h3 className="font-medium text-ink">{source.name}</h3>
              <span className="rounded-full bg-paper px-2.5 py-0.5 font-mono text-[11px] font-medium tracking-wide text-ink-soft uppercase">
                Not used
              </span>
            </div>
            {source.license && <p className="mt-1 text-xs text-ink-soft">Licence: {source.license}</p>}
            <p className="mt-2 text-sm leading-relaxed text-ink-soft">{source.note}</p>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-3">
        <h2 className="font-display text-lg font-semibold text-ink">Potential future sources</h2>
        <p className="text-sm leading-relaxed text-ink-soft">
          Not currently used by DrugSim. These do not contribute to any current prediction — some
          are catalogued in DrugSim's internal source registry with their licensing already
          reviewed, and others are only names identified as candidates in project planning
          documents, with no review done yet.
        </p>
        <div className="card p-5">
          <p className="text-xs font-medium tracking-wide text-ink-soft uppercase">
            Catalogued for potential future ingestion
          </p>
          <ul className="mt-2 grid grid-cols-1 gap-2 text-sm text-ink-soft sm:grid-cols-2">
            {FUTURE_SOURCES.map((source) => (
              <li key={source.id}>
                <span className="font-medium text-ink">
                  {source.officialUrl ? <ExternalLink href={source.officialUrl}>{source.name}</ExternalLink> : source.name}
                </span>
                {" — "}
                {source.purpose}
              </li>
            ))}
          </ul>
        </div>
        <div className="card p-5">
          <p className="text-xs font-medium tracking-wide text-ink-soft uppercase">Evaluated, not yet scheduled</p>
          <ul className="mt-2 grid grid-cols-1 gap-2 text-sm text-ink-soft sm:grid-cols-2">
            {DEFERRED_SOURCE_NAMES.map((source) => (
              <li key={source.name}>
                <span className="font-medium text-ink">{source.name}</span> — {source.value}
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="rounded-lg border border-line bg-paper-alt p-5">
        <h2 className="font-display text-base font-semibold text-ink">Independent project</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          DrugSim is an independent project and is not affiliated with, endorsed by, or officially
          associated with Oxford University or any institution named on this page. Using a
          published, publicly available dataset does not imply a relationship with, review by, or
          collaboration with the organisation that publishes it.
        </p>
      </section>

      <p className="text-sm text-ink-soft">
        See also{" "}
        <Link to="/methodology" className="underline underline-offset-2 hover:text-ink">
          Methodology
        </Link>{" "}
        for how this data is turned into a prediction, and{" "}
        <Link to="/limitations" className="underline underline-offset-2 hover:text-ink">
          Limitations
        </Link>{" "}
        for what the resulting models do not tell you.
      </p>
    </div>
  );
}
