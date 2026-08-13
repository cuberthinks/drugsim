import { Link } from "react-router-dom";

export function PrivacyPage() {
  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-6 py-12">
      <header>
        <p className="font-mono text-xs text-ink-soft uppercase tracking-wide">Privacy</p>
        <h1 className="mt-1 font-display text-3xl font-semibold text-ink">Privacy Policy</h1>
        <p className="mt-3 text-sm leading-relaxed text-ink-soft">
          This page describes what DrugSim does with the information you provide when you
          submit a molecule for prediction. It is written for a controlled research/
          demonstration deployment, not a public consumer product — see{" "}
          <Link to="/terms" className="underline underline-offset-2 hover:text-ink">
            Terms of Use
          </Link>{" "}
          for who this service is intended for.
        </p>
      </header>

      <section className="flex flex-col gap-4">
        <div className="rounded-lg border border-line bg-white p-5">
          <h2 className="font-display text-lg font-semibold text-ink">What we receive</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            The molecular structure you submit (as SMILES text), and standard request
            metadata (timestamp, a correlation ID, and the structure's cryptographic hash —
            never the structure itself — in server logs). DrugSim does not require an
            account, and does not collect names, email addresses, or other personal
            information to run a prediction.
          </p>
        </div>

        <div className="rounded-lg border border-line bg-white p-5">
          <h2 className="font-display text-lg font-semibold text-ink">
            How submitted structures are handled
          </h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            A submitted structure may be a compound you consider confidential or pre-patent.
            It is stored in the prediction audit record (so that a result can later be
            retrieved and so predictions are traceable — see{" "}
            <Link to="/methodology" className="underline underline-offset-2 hover:text-ink">
              Methodology
            </Link>
            ) but is deliberately kept out of the application's general log stream, which
            only ever records a one-way hash of it. Do not submit a structure to this
            deployment if its confidentiality could not withstand being stored in that
            audit record.
          </p>
        </div>

        <div className="rounded-lg border border-line bg-white p-5">
          <h2 className="font-display text-lg font-semibold text-ink">Retention</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            Prediction records are retained for as long as this deployment operates, to
            preserve scientific traceability and provenance. There is currently no
            self-service mechanism to request deletion of a specific submission — contact
            the operators below if you need one removed.
          </p>
        </div>

        <div className="rounded-lg border border-line bg-white p-5">
          <h2 className="font-display text-lg font-semibold text-ink">What we do not do</h2>
          <p className="mt-2 text-sm leading-relaxed text-ink-soft">
            DrugSim does not sell, share, or use submitted structures for any purpose other
            than producing and recording the prediction you requested. It does not use
            submissions to train or retrain the underlying model — the model is a fixed,
            validated artifact (see{" "}
            <Link to="/methodology" className="underline underline-offset-2 hover:text-ink">
              Methodology
            </Link>
            ), not something this deployment learns from over time.
          </p>
        </div>
      </section>

      <p className="text-sm text-ink-soft">
        Questions about this policy: see{" "}
        <Link to="/about" className="underline underline-offset-2 hover:text-ink">
          About &amp; contact
        </Link>
        .
      </p>
    </div>
  );
}
