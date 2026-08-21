/**
 * Per-endpoint display copy (Phase 9). Nothing here changes what a
 * prediction IS — every number and label still comes straight from the
 * API response. This only maps an endpoint's own label vocabulary and a
 * short, endpoint-specific description onto something readable, so the UI
 * never has to guess or invent wording for an endpoint it doesn't
 * recognise (the fallback path below handles that case explicitly).
 */

export interface EndpointCopy {
  displayName: string;
  /** Short noun phrase for buttons/headings, e.g. "hERG inhibition". */
  shortName: string;
  positiveLabelText: string;
  negativeLabelText: string;
  probabilityCaption: string;
  /** One or two paragraphs of biological context for "What does this mean?" */
  description: string[];
}

export const ENDPOINT_COPY: Record<string, EndpointCopy> = {
  herg_inhibition: {
    displayName: "hERG (cardiac channel) inhibition",
    shortName: "hERG inhibition",
    positiveLabelText: "Predicted hERG inhibitor",
    negativeLabelText: "Predicted non-inhibitor",
    probabilityCaption: "Estimated probability of hERG inhibition",
    description: [
      "hERG inhibition refers to the potential for a compound to interfere with the cardiac hERG potassium channel (KCNH2 / Kv11.1). Strong inhibition can be associated with QT-interval prolongation and cardiac safety concerns, which is why it is one of the most widely screened properties early in drug discovery.",
      "This model labels a compound a blocker when its aggregated literature IC50 is at or below 10 µM, a screening convention rather than a fixed biological cutoff. Unlike this platform's CYP3A4 model, it has not been validated against an independent external dataset — every reported metric comes from held-out portions of its own training source.",
    ],
  },
  cyp3a4_inhibition: {
    displayName: "CYP3A4 (metabolism) inhibition",
    shortName: "CYP3A4 inhibition",
    positiveLabelText: "Predicted CYP3A4 inhibitor",
    negativeLabelText: "Predicted non-inhibitor",
    probabilityCaption: "Estimated probability of CYP3A4 inhibition",
    description: [
      "CYP3A4 (cytochrome P450 3A4) is the single most important drug-metabolising enzyme in humans, responsible for clearing roughly half of all marketed small-molecule drugs. A compound that inhibits CYP3A4 can slow the clearance of other drugs metabolised by the same enzyme, raising their blood levels — the mechanism behind many clinically significant drug-drug interactions.",
      "This model labels a compound an inhibitor when its aggregated literature IC50 is at or below 10 µM, a screening convention rather than a fixed biological cutoff. It says nothing about interaction risk at any particular clinical dose.",
      "This model has a documented weakness: on its own held-out test set, specificity is only 40.5% — a real, asymmetric tendency to call a compound an inhibitor when it is not. Treat a 'Predicted CYP3A4 inhibitor' result as a reason to investigate further, not as strong evidence on its own.",
    ],
  },
};

const FALLBACK_COPY: EndpointCopy = {
  displayName: "this endpoint",
  shortName: "this endpoint",
  positiveLabelText: "Positive",
  negativeLabelText: "Negative",
  probabilityCaption: "Estimated probability of the positive class",
  description: [
    "No description is available for this endpoint yet. Read the prediction together with its uncertainty and applicability-domain information below.",
  ],
};

export function getEndpointCopy(modelId: string): EndpointCopy {
  return ENDPOINT_COPY[modelId] ?? FALLBACK_COPY;
}

export function labelText(modelId: string, label: string): string {
  const copy = ENDPOINT_COPY[modelId];
  if (!copy) return label;
  // The positive/negative label STRINGS themselves come from the backend
  // (e.g. "blocker"/"inhibitor") -- this only maps them to prose, and only
  // for the exact strings the endpoint is documented to use.
  if (label === "blocker" || label === "inhibitor") return copy.positiveLabelText;
  if (label === "non_blocker" || label === "non_inhibitor") return copy.negativeLabelText;
  return label;
}
