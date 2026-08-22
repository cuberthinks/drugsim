import { Link } from "react-router-dom";

export function HomePage() {
  return (
    <div>
      {/* Hero */}
      <section className="relative overflow-hidden border-b border-line bg-paper-alt">
        {/* Signature: a quiet teal glow, the same signal color that marks
            "known chemistry" on the applicability-domain gauge below --
            the one ambient-motion accent this page spends. */}
        <div
          aria-hidden="true"
          className="signal-glow pointer-events-none absolute top-1/2 left-1/2 h-[36rem] w-[36rem] -translate-x-1/2 -translate-y-1/2 rounded-full bg-signal/10 blur-3xl"
        />
        <div className="relative mx-auto max-w-3xl px-6 py-20 text-center">
          <p className="rise-in font-mono text-xs tracking-wide text-signal uppercase">
            Computational ADMET prediction
          </p>
          <h1 className="rise-in mt-4 font-display text-4xl font-semibold leading-tight text-ink sm:text-5xl" style={{ animationDelay: "60ms" }}>
            Explore how a molecule may behave, before it ever reaches a bench.
          </h1>
          <p className="rise-in mx-auto mt-6 max-w-xl text-lg leading-relaxed text-ink-soft" style={{ animationDelay: "120ms" }}>
            DrugSim estimates individual ADMET (Absorption, Distribution, Metabolism,
            Excretion, Toxicity) endpoints — currently hERG cardiac-channel inhibition and
            CYP3A4 metabolic inhibition — from a molecular structure you provide, using
            machine-learning models statistically validated on held-out data — not clinically
            validated — always shown alongside their uncertainty and applicability domain,
            never as a bare number.
          </p>
          <div className="rise-in mt-8 flex items-center justify-center gap-4" style={{ animationDelay: "180ms" }}>
            <Link
              to="/predict"
              className="rounded-md bg-ink px-6 py-3 text-sm font-medium text-paper shadow-sm transition-[box-shadow,transform,opacity] duration-200 hover:-translate-y-0.5 hover:opacity-90 hover:shadow-md active:scale-[0.97]"
            >
              Enter a molecule
            </Link>
            <Link
              to="/methodology"
              className="text-sm font-medium text-ink-soft underline underline-offset-4 transition-colors hover:text-ink"
            >
              How it works
            </Link>
          </div>
        </div>
      </section>

      {/* What DrugSim is / is not */}
      <section className="mx-auto max-w-5xl px-6 py-16">
        <div className="grid gap-10 sm:grid-cols-2">
          <div>
            <h2 className="font-display text-xl font-semibold text-ink">What DrugSim does</h2>
            <p className="mt-3 leading-relaxed text-ink-soft">
              Given a molecular structure, DrugSim standardises it, computes the same
              features its validated models were trained on, and returns a prediction for
              whichever endpoint you select — always paired with a conformal uncertainty
              estimate and an applicability-domain assessment describing how much relevant
              evidence the model actually has for chemistry like this.
            </p>
          </div>
          <div>
            <h2 className="font-display text-xl font-semibold text-ink">What it is not</h2>
            <p className="mt-3 leading-relaxed text-ink-soft">
              Predictions are computational estimates, not experimental results. They do
              not replace laboratory testing, do not establish clinical safety, do not
              combine into a simulation of a whole organism, and are each scoped to the
              specific validated endpoints described on the{" "}
              <Link to="/methodology" className="underline underline-offset-2 hover:text-ink">
                methodology page
              </Link>
              . See the full{" "}
              <Link to="/limitations" className="underline underline-offset-2 hover:text-ink">
                limitations and disclaimer
              </Link>
              .
            </p>
          </div>
        </div>
      </section>

      {/* Why a dedicated pipeline, not a general AI */}
      <section className="mx-auto max-w-5xl px-6 py-16">
        <h2 className="font-display text-xl font-semibold text-ink">Why not just ask a general AI?</h2>
        <div className="mt-6 grid gap-10 sm:grid-cols-2">
          <p className="leading-relaxed text-ink-soft">
            A general-purpose AI is built to answer a broad range of questions in natural
            language, from whatever it can recall or infer about a topic. DrugSim is built
            around one specific scientific workflow instead: a structure runs through the
            same standardisation, the same validated model, and the same uncertainty and
            applicability-domain checks every time — never a different answer depending on
            how the question was phrased, and never a plausible-sounding guess offered in
            place of "the model doesn't have enough relevant training data for this."
          </p>
          <p className="leading-relaxed text-ink-soft">
            That also shapes how a submitted structure is handled: DrugSim exists to run
            one computation on it and record that it did, not to hold a conversation about
            it, retain it for general reference, or feed it into a language model's future
            responses. See the{" "}
            <Link to="/privacy" className="underline underline-offset-2 hover:text-ink">
              Privacy Policy
            </Link>{" "}
            for exactly what is stored, for how long, and why.
          </p>
        </div>
      </section>

      {/* Flow */}
      <section className="border-t border-line bg-paper-alt">
        <div className="mx-auto max-w-5xl px-6 py-16">
          <h2 className="font-display text-xl font-semibold text-ink">From structure to interpretation</h2>
          <ol className="mt-8 grid gap-6 sm:grid-cols-3">
            <FlowStep
              label="Enter & validate"
              text="Provide a SMILES string. DrugSim parses and standardises it using the same chemistry pipeline the model was trained on."
            />
            <FlowStep
              label="Run the model"
              text="The validated model for your chosen endpoint scores the standardised structure and returns its result with reliability data attached."
            />
            <FlowStep
              label="Interpret the result"
              text="Read the prediction together with its uncertainty and applicability domain — what it means, and how much evidence supports it."
            />
          </ol>
        </div>
      </section>
    </div>
  );
}

function FlowStep({ label, text }: { label: string; text: string }) {
  return (
    <li className="border-l-2 border-signal pl-4">
      <p className="font-medium text-ink">{label}</p>
      <p className="mt-1 text-sm leading-relaxed text-ink-soft">{text}</p>
    </li>
  );
}
