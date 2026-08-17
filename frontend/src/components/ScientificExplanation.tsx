import { getEndpointCopy } from "../lib/endpointCopy";

/**
 * User feedback (this revision): "the overall scientific interpretation is
 * unclear" — the previous version was one undifferentiated block of prose
 * that mixed what the model predicted, how sure the math is, and whether
 * the model has relevant experience, all in the same paragraph. Nothing
 * here changes what any panel says; it only groups the same three ideas
 * under plain headings so a reader can tell which question each piece of
 * the page above is actually answering.
 */
export function ScientificExplanation({ endpoint }: { endpoint: string }) {
  const copy = getEndpointCopy(endpoint);

  return (
    <section aria-labelledby="what-this-means" className="rounded-lg border border-line bg-paper-alt p-6">
      <h3 id="what-this-means" className="font-display text-lg font-semibold text-ink">
        How to read this result
      </h3>
      <p className="mt-2 text-sm leading-relaxed text-ink-soft">
        Three separate questions are answered above. Each one can be right or wrong on its
        own — a confident-looking number does not mean the model actually has relevant
        experience, and vice versa. Read all three together, not just the headline number.
      </p>

      <div className="mt-4 flex flex-col gap-4">
        <div>
          <p className="text-sm font-semibold text-ink">1. The prediction — what the model thinks</p>
          <p className="mt-1 text-sm leading-relaxed text-ink-soft">
            The model's direct output for this molecule: which class it lands in, and how
            strongly. This is a statistical estimate produced by a trained model, not a lab
            measurement — it describes what the model thinks, not a fact about the molecule.
          </p>
        </div>

        <div>
          <p className="text-sm font-semibold text-ink">2. The uncertainty — how confident the math is</p>
          <p className="mt-1 text-sm leading-relaxed text-ink-soft">
            Whether the model can actually tell the two outcomes apart for this specific
            molecule, expressed as p-values with a real statistical guarantee behind them
            (see "Uncertainty" above) — not a made-up confidence score.
          </p>
        </div>

        <div>
          <p className="text-sm font-semibold text-ink">
            3. The applicability domain — whether the model has the right experience to guess
          </p>
          <p className="mt-1 text-sm leading-relaxed text-ink-soft">
            Whether this molecule actually resembles the chemistry the model was trained on.
            A model can sound confident about something it has never really seen before —
            this is the check for that. It is entirely possible for a well-known, simple
            molecule to score poorly here for reasons that have nothing to do with how
            dangerous or well-understood it is; see "Applicability domain" above.
          </p>
        </div>
      </div>

      {copy.description.length > 0 && (
        <div className="mt-4 border-t border-line pt-4">
          <p className="text-sm font-semibold text-ink">About this endpoint</p>
          {copy.description.map((paragraph, i) => (
            <p key={i} className="mt-2 text-sm leading-relaxed text-ink-soft">
              {paragraph}
            </p>
          ))}
        </div>
      )}

      <p className="mt-4 border-t border-line pt-4 text-sm leading-relaxed text-ink-soft">
        This result is a computational estimate from a single validated model, not a
        clinical diagnosis or a guarantee of safety. A compound flagged as a likely
        positive is not necessarily unsafe in practice, and a compound flagged as unlikely
        is not confirmed safe — both require experimental follow-up.
      </p>
    </section>
  );
}
