import type { WarningItem } from "../api/types";

const SEVERITY_STYLE: Record<string, string> = {
  high: "border-concern/40 bg-concern-soft text-concern",
  medium: "border-caution/40 bg-caution-soft text-caution",
  low: "border-line bg-paper-alt text-ink-soft",
};

export function WarningsList({ warnings }: { warnings: WarningItem[] }) {
  if (warnings.length === 0) return null;
  return (
    <ul className="flex flex-col gap-2" aria-label="Prediction warnings">
      {warnings.map((warning, i) => (
        <li
          key={`${warning.code}-${i}`}
          className={`rounded-md border px-4 py-3 text-sm leading-relaxed ${SEVERITY_STYLE[warning.severity] ?? SEVERITY_STYLE.low}`}
        >
          {warning.message}
        </li>
      ))}
    </ul>
  );
}
