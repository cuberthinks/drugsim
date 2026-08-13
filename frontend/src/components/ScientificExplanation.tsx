import { getEndpointCopy } from "../lib/endpointCopy";

export function ScientificExplanation({ endpoint }: { endpoint: string }) {
  const copy = getEndpointCopy(endpoint);

  return (
    <section aria-labelledby="what-this-means" className="rounded-lg border border-line bg-paper-alt p-6">
      <h3 id="what-this-means" className="font-display text-lg font-semibold text-ink">
        What does this mean?
      </h3>
      {copy.description.map((paragraph, i) => (
        <p key={i} className="mt-3 text-sm leading-relaxed text-ink-soft">
          {paragraph}
        </p>
      ))}
      <p className="mt-3 text-sm leading-relaxed text-ink-soft">
        This result is a computational estimate from a single validated model, not a
        clinical diagnosis or a guarantee of safety. A compound flagged as a likely
        positive is not necessarily unsafe in practice, and a compound flagged as unlikely
        is not confirmed safe — both require experimental follow-up, and the
        applicability-domain and uncertainty information above should always be read
        alongside the prediction itself.
      </p>
    </section>
  );
}
