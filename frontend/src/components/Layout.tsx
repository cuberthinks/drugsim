import { NavLink, Outlet } from "react-router-dom";

const navLinkClass = ({ isActive }: { isActive: boolean }) =>
  `text-sm font-medium transition-colors ${
    isActive ? "text-ink" : "text-ink-soft hover:text-ink"
  }`;

export function Layout() {
  return (
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:top-2 focus:left-2 focus:z-50 focus:rounded focus:bg-ink focus:px-4 focus:py-2 focus:text-paper"
      >
        Skip to content
      </a>
      <header className="border-b border-line">
        <div className="mx-auto flex max-w-5xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-6 py-4">
          <NavLink to="/" className="flex items-baseline gap-2">
            <span className="font-display text-xl font-semibold tracking-tight text-ink">
              DrugSim
            </span>
            <span className="font-mono text-[11px] text-ink-soft">research preview</span>
          </NavLink>
          <nav className="flex flex-wrap items-center gap-x-4 gap-y-1 sm:gap-x-6" aria-label="Primary">
            <NavLink to="/predict" className={navLinkClass}>
              Predict
            </NavLink>
            <NavLink to="/methodology" className={navLinkClass}>
              Methodology
            </NavLink>
            <NavLink to="/limitations" className={navLinkClass}>
              Limitations
            </NavLink>
          </nav>
        </div>
      </header>

      <main id="main" className="flex-1">
        <Outlet />
      </main>

      <footer className="border-t border-line">
        <div className="mx-auto max-w-5xl px-6 py-8 text-sm text-ink-soft">
          <p className="max-w-2xl">
            DrugSim produces computational estimates from a validated machine-learning
            model. Predictions are not experimental results and do not establish clinical
            safety. Read the{" "}
            <NavLink to="/limitations" className="underline underline-offset-2 hover:text-ink">
              limitations and disclaimer
            </NavLink>{" "}
            before interpreting any result.
          </p>
          <p className="mt-4 font-mono text-xs text-ink-soft">
            DrugSim internal research preview — not for clinical or regulatory use
          </p>
          <nav className="mt-4 flex flex-wrap gap-x-4 gap-y-1 text-xs" aria-label="Legal and about">
            <NavLink to="/about" className="underline underline-offset-2 hover:text-ink">
              About &amp; contact
            </NavLink>
            <NavLink to="/privacy" className="underline underline-offset-2 hover:text-ink">
              Privacy Policy
            </NavLink>
            <NavLink to="/terms" className="underline underline-offset-2 hover:text-ink">
              Terms of Use
            </NavLink>
          </nav>
        </div>
      </footer>
    </div>
  );
}
