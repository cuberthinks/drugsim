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
    <div className="rounded-lg border border-line bg-paper-alt transition-shadow duration-200 hover:shadow-sm">
      <button
        type="button"
        onClick={toggle}
        aria-expanded={open}
        aria-controls="how-this-works-content"
        className="flex w-full items-center justify-between gap-3 px-4 py-3 text-left"
      >
        <span className="text-sm font-medium text-ink">How this works</span>
        <span className="text-ink-soft transition-transform duration-200" aria-hidden="true" style={{ transform: open ? "rotate(0deg)" : "rotate(90deg)" }}>
          {open ? "−" : "+"}
        </span>
      </button>
      {/* A grid-rows tween rather than mount/unmount -- collapsing this
          used to be an instant pop, the opposite of the "smoother" the
          rest of this pass is going for. Always in the DOM, just clipped
          to zero height when closed; aria-hidden keeps it (correctly)
          out of the accessibility tree either way, so this is invisible
          to the existing open/closed tests and to screen readers.
          The row track's own item (the inner div) carries NO padding or
          border of its own -- those live one level deeper, on the <ol> --
          because padding/border on the collapsing item itself can't
          shrink past their own size even at grid-template-rows: 0fr,
          which left a fixed ~33px sliver permanently visible when they
          were on the same element. */}
      <div
        className={`grid overflow-hidden transition-[grid-template-rows] duration-300 ease-out ${open ? "grid-rows-[1fr]" : "grid-rows-[0fr]"}`}
      >
        <div className="min-h-0 overflow-hidden">
          <ol
            id="how-this-works-content"
            aria-hidden={!open}
            className="grid gap-4 border-t border-line p-4 sm:grid-cols-3"
            aria-label="How this works"
          >
            {STEPS.map(({ step, detail }, i) => (
              <li key={step} className="card p-4">
                <p className="font-mono text-xs text-ink-soft">{i + 1}</p>
                <p className="mt-1 text-sm font-medium text-ink">{step}</p>
                <p className="mt-1 text-xs leading-relaxed text-ink-soft">{detail}</p>
              </li>
            ))}
          </ol>
        </div>
      </div>
    </div>
  );
}
