interface Entry {
  date: string;
  title: string;
  items: string[];
}

const ENTRIES: Entry[] = [
  {
    date: "2026-08-30",
    title: "Compound recognition fixes and expansion",
    items: [
      "Ethanol, water, methane, and benzene were incorrectly showing as \"not identified\" despite being some of the most well-known compounds there are — fixed. All four now resolve to their real name, synonyms, and a sourced description.",
      "Added around 50 common lab and industrial chemicals to the reference list — solvents (acetone, methanol, isopropanol, THF, DMSO, and others), everyday acids and bases, common gases, simple aromatics, and more.",
      "Compound recognition covers a curated reference list, not arbitrary chemistry — a compound outside that list is honestly labeled \"not identified\" rather than guessed at. If a compound you'd expect to be recognized isn't, that's worth reporting.",
      "DrugSim can now recognize 960 named compounds by structure, up from 904 at the start of today.",
    ],
  },
  {
    date: "2026-08-27",
    title: "Compound identification",
    items: [
      "A prediction now includes a verified compound-identity panel — name, common synonyms, database identifiers, and a sourced description — whenever the submitted structure matches one of DrugSim's own reference compounds.",
      "This is resolved entirely offline, from a snapshot built in advance: a submitted structure is never sent to any third party to look up its identity, the same guarantee already in place for predictions themselves.",
      "A structure outside that reference set is now honestly labeled \"not identified\" rather than showing nothing — the prediction itself proceeds exactly the same either way.",
      "Molecular weight is now shown directly on every result.",
    ],
  },
  {
    date: "2026-08-22",
    title: "Confidentiality hardening",
    items: [
      "Fixed a gap where a stored prediction could be retrieved by a different valid API key than the one that submitted it — retrieval is now scoped to the key that created it, with no change to what any legitimate caller could already do.",
      "Added a privacy notice next to the structure input stating plainly that submitted structures are never used to train DrugSim's models, linking to the full privacy policy.",
      "Added a \"Third parties\" section to the privacy policy naming exactly what does and does not receive a submitted structure — nothing does, beyond DrugSim's own backend.",
      "Published a full confidentiality audit and its results at docs/privacy/, including every finding and every automated test added to enforce it going forward.",
    ],
  },
  {
    date: "2026-08-21",
    title: "Scientific transparency",
    items: [
      "The limitations page and each endpoint's own explanation now name the specific, known weaknesses of that model — CYP3A4's real false-positive rate, hERG's lack of independent external validation, and the screening-convention nature of the 10 µM activity threshold — rather than only general disclaimers.",
    ],
  },
  {
    date: "2026-08-21",
    title: "Reliability fixes",
    items: [
      "Reduced the memory a single prediction allocates by caching reference data the applicability-domain check needs once per server start, instead of recomputing it on every request.",
      "Fixed a bug where the server's own internal health check could load a model twice into memory instead of reusing the copy already loaded — harmless on its own, but it made an unrelated memory fix ride closer to the server's limit than it should have.",
      "Raised the per-visitor request limit on the shared demo key.",
    ],
  },
  {
    date: "2026-08-18",
    title: "Product improvements",
    items: [
      "Added a local (browser-only) prediction history, never sent to or stored by the server.",
      "Added JSON/CSV export of a completed result, including its uncertainty, applicability domain, model version, and the scientific disclaimer.",
      "Expanded the single example molecule to four real, verified compounds demonstrating different actual outcomes.",
      "Added this changelog.",
    ],
  },
  {
    date: "2026-08-18",
    title: "Usability & accessibility",
    items: [
      "Added a plain-language explanation of what SMILES is and how to obtain one.",
      "Spelled out \"ADMET\" at its first use, and gave \"applicability domain\" a self-contained definition at its own point of use.",
      "Added a lightweight, skippable three-step guide to the prediction workflow.",
      "Fixed a color-contrast gap and a mobile layout gap found in an accessibility review.",
    ],
  },
  {
    date: "2026-08-17",
    title: "Scientific communication",
    items: [
      "The conformal p-values behind each prediction's uncertainty are now shown directly, with a plain-language explanation of what a p-value means here.",
      "The applicability-domain explanation now covers why common, simple molecules can still fall outside the model's training chemistry.",
      "Reorganised the results page's explanation into three explicit parts: the prediction, the uncertainty, and the applicability domain.",
    ],
  },
  {
    date: "2026-08-15 – 2026-08-16",
    title: "Reliability fixes",
    items: [
      "Fixed a memory limit that had been crashing every hERG prediction in production.",
      "Fixed a rate-limiting bug that made concurrent users on the shared demo key interfere with each other.",
      "Fixed a bug where a temporary connection error could erase a valid result still on screen.",
    ],
  },
];

export function ChangelogPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">What's new</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">Changelog</h1>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          What's changed recently, in plain terms. Model results and validated scientific
          calculations are never listed here as "improved" — see the{" "}
          <a href="/methodology" className="underline underline-offset-2 hover:text-ink">
            methodology page
          </a>{" "}
          for the actual validation history of each endpoint.
        </p>
      </header>

      <ol className="flex flex-col gap-6">
        {ENTRIES.map((entry) => (
          <li key={`${entry.date}-${entry.title}`} className="card p-6">
            <p className="font-mono text-xs text-ink-soft">{entry.date}</p>
            <h2 className="mt-1 font-display text-lg font-semibold text-ink">{entry.title}</h2>
            <ul className="mt-3 list-disc space-y-1.5 pl-5 text-sm leading-relaxed text-ink-soft">
              {entry.items.map((item) => (
                <li key={item}>{item}</li>
              ))}
            </ul>
          </li>
        ))}
      </ol>
    </div>
  );
}
