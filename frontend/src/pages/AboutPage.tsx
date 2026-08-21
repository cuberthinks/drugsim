import { Link } from "react-router-dom";

export function AboutPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">About</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">About DrugSim</h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          DrugSim is a computational research tool that estimates how a molecule may behave
          against a small set of independently validated ADMET endpoints — currently hERG
          cardiac-channel inhibition and CYP3A4 metabolic inhibition — using machine-learning
          models trained on curated public bioactivity data. It is built to help prioritise
          which compounds might be worth testing next, always alongside its uncertainty and
          applicability-domain information, never as a bare number, and never combined into a
          single overall score.
        </p>
      </header>

      <section className="card p-5">
        <h2 className="font-display text-lg font-semibold text-ink">What this deployment is</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          A controlled research and demonstration deployment. It is intended for
          researchers, collaborators, and reviewers evaluating the tool's approach — not for
          unsupervised public use, and not for any clinical or regulatory purpose. See{" "}
          <Link to="/terms" className="underline underline-offset-2 hover:text-ink">
            Terms of Use
          </Link>{" "}
          and{" "}
          <Link to="/limitations" className="underline underline-offset-2 hover:text-ink">
            Limitations
          </Link>{" "}
          before relying on any result.
        </p>
      </section>

      <section className="card p-5">
        <h2 className="font-display text-lg font-semibold text-ink">How it works</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Every prediction follows the same fixed, versioned pipeline — standardisation,
          feature computation, the validated model, uncertainty, and applicability domain —
          documented in full on the{" "}
          <Link to="/methodology" className="underline underline-offset-2 hover:text-ink">
            Methodology
          </Link>{" "}
          page.
        </p>
      </section>

      <section className="card p-5" aria-labelledby="credits-heading">
        <h2 id="credits-heading" className="font-display text-lg font-semibold text-ink">
          Credits
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Origin: Hong Kong.
        </p>
        <p className="mt-3 text-sm font-medium text-ink">Collaborators</p>
        <ul className="mt-1 text-sm leading-relaxed text-ink-soft">
          <li>Yiu Pak On</li>
          <li>Lee Man Hung</li>
        </ul>
      </section>

      <section className="rounded-lg border border-line bg-paper-alt p-5" aria-labelledby="contact-heading">
        <h2 id="contact-heading" className="font-display text-lg font-semibold text-ink">
          Contact
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          For questions about a result, a data-retention request under the{" "}
          <Link to="/privacy" className="underline underline-offset-2 hover:text-ink">
            Privacy Policy
          </Link>
          , or to report a problem with this deployment:
        </p>
        <p className="mt-3 font-mono text-sm text-ink">research@drugsim.example</p>
        <p className="mt-2 text-xs leading-relaxed text-ink-soft">
          Placeholder address (the reserved .example domain, per RFC 2606 — see the
          Caddyfile in this repository's deployment configuration for the same convention).
          Whoever operates a real deployment of DrugSim must replace this with an actual,
          monitored contact address before external use.
        </p>
      </section>
    </div>
  );
}
