import { useState } from "react";

const STORAGE_KEY = "drugsim_how_it_works_open_v1";

const STEPS = [
  { step: "Enter a molecule", detail: "Paste a SMILES string, or use an example." },
  { step: "Run a prediction", detail: "Validate the structure, then predict." },
  { step: "Review prediction + reliability", detail: "Read the result together with its uncertainty and applicability domain." },
];

/** Defaults open the first time (a first-time visitor benefits from seeing
 * it unprompted), then remembers whatever the user last chose -- collapse
 * it once and it stays collapsed on later visits, same private/local-only
 * pattern as this app's other small UI preferences. */
function readInitialOpen(): boolean {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    return raw === null ? true : raw === "true";
  } catch {
    return true;
  }
}

/** Collapsible "How this works" guide -- previously a 3-card grid always
 * visible above the input, duplicating the header paragraph's own
 * enter/validate/predict sentence. Collapsing it by default after first
 * dismissal removes that permanent clutter for a returning user while
 * keeping the guidance one click away, not deleted. */
export function HowThisWorksGuide() {
  const [open, setOpen] = useState(readInitialOpen);

  function toggle() {
    const next = !open;
    setOpen(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, String(next));
    } catch {
      // Storage disabled/full -- the toggle still works for this session,
      // it just won't be remembered next time. Never worth failing over.
    }
  }

  return (
    <div className="rounded-lg border border-line bg-paper-alt">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="how-this-works-content"
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="text-sm font-medium text-ink">How this works</span>
        <span className="text-ink-soft" aria-hidden="true">
          {open ? "−" : "+"}
        </span>
      </button>
      {open && (
        <ol
          id="how-this-works-content"
          className="grid gap-4 border-t border-line p-4 sm:grid-cols-3"
          aria-label="How this works"
        >
          {STEPS.map(({ step, detail }, i) => (
            <li key={step} className="rounded-lg border border-line bg-white p-4">
              <p className="font-mono text-xs text-ink-soft">{i + 1}</p>
              <p className="mt-1 text-sm font-medium text-ink">{step}</p>
              <p className="mt-1 text-xs leading-relaxed text-ink-soft">{detail}</p>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
