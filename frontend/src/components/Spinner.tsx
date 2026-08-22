/** Inline busy indicator, shared wherever a button's own text already says
 * what's happening ("Validating…", "Predicting…", "Running prediction…") --
 * this only adds a motion cue on top of that existing text, so it's purely
 * decorative and safe to freeze under prefers-reduced-motion (the global
 * rule in index.css already does that for every animation, this one
 * included). */
export function Spinner({ className = "" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-block h-3.5 w-3.5 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent ${className}`}
    />
  );
}
