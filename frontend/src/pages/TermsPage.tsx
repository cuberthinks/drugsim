import { Link } from "react-router-dom";

export function TermsPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Terms</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">Terms of Use</h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          By using DrugSim you agree to the terms below. This deployment is intended for
          controlled research and demonstration use, not for the general public or for any
          clinical, diagnostic, or regulatory purpose.
        </p>
      </header>

      <ul className="flex flex-col gap-4">
        <li className="rounded-lg border border-concern/30 bg-concern-soft p-5">
          <h2 className="font-medium text-ink">DrugSim provides computational predictions</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            Every result is a model output — a computational estimate — not a laboratory
            measurement, a clinical finding, or an experimental result of any kind.
          </p>
        </li>
        <li className="rounded-lg border border-concern/30 bg-concern-soft p-5">
          <h2 className="font-medium text-ink">Results are not clinical diagnoses</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            Nothing produced by DrugSim constitutes a medical or clinical diagnosis, for any
            compound, in any context.
          </p>
        </li>
        <li className="rounded-lg border border-concern/30 bg-concern-soft p-5">
          <h2 className="font-medium text-ink">Results are not guarantees of safety</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            A favourable prediction is not a safety guarantee, and an unfavourable one is
            not proof of harm. Both require experimental confirmation.
          </p>
        </li>
        <li className="rounded-lg border border-concern/30 bg-concern-soft p-5">
          <h2 className="font-medium text-ink">
            Predictions do not replace laboratory or clinical testing
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            DrugSim is a prioritisation aid. It does not substitute for in vitro, in vivo, or
            clinical evaluation at any stage of research or development.
          </p>
        </li>
        <li className="rounded-lg border border-concern/30 bg-concern-soft p-5">
          <h2 className="font-medium text-ink">Each model covers only its own validated endpoint</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            DrugSim currently offers validated predictions for hERG cardiac-channel
            inhibition and CYP3A4 metabolic inhibition, each independently validated and
            never combined into a single score. Neither says anything about any other
            property, endpoint, efficacy measure, or safety concern, and predictions do not
            combine into a simulation of a whole organism — see{" "}
            <Link to="/methodology" className="underline underline-offset-2 hover:text-ink">
              Methodology
            </Link>
            .
          </p>
        </li>
        <li className="rounded-lg border border-concern/30 bg-concern-soft p-5">
          <h2 className="font-medium text-ink">
            Results outside the applicability domain may be unreliable
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            A structure flagged as outside the model's known chemistry is an extrapolation
            and should be treated with reduced confidence — see the{" "}
            <Link to="/limitations" className="underline underline-offset-2 hover:text-ink">
              Limitations
            </Link>{" "}
            page.
          </p>
        </li>
      </ul>

      <section className="card p-5">
        <h2 className="font-display text-lg font-semibold text-ink">No regulatory status</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          DrugSim has not been evaluated, cleared, or approved by any regulatory authority
          for any purpose, and this deployment makes no claim of regulatory status,
          certification, or clinical validation. Use of this service does not create any
          professional, clinical, or regulatory relationship between you and its operators.
        </p>
      </section>

      <section className="card p-5">
        <h2 className="font-display text-lg font-semibold text-ink">Acceptable use</h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-soft">
          Do not submit structures you do not have the right to share with this
          deployment's operators (see{" "}
          <Link to="/privacy" className="underline underline-offset-2 hover:text-ink">
            Privacy Policy
          </Link>
          ), and do not use this service in a way that circumvents its rate limits or
          access controls.
        </p>
      </section>
    </div>
  );
}
