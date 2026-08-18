interface Entry {
  date: string;
  title: string;
  items: string[];
}

const ENTRIES: Entry[] = [
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
          <li key={`${entry.date}-${entry.title}`} className="rounded-lg border border-line bg-white p-6">
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
