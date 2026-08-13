# Terms of Use

This mirrors the frontend's own Terms page (`frontend/src/pages/TermsPage.tsx`) — kept in sync deliberately; the frontend page is what a user actually agrees to and should be treated as authoritative if the two ever disagree.

By using DrugSim you agree to the terms below. This deployment is intended for controlled research and demonstration use, not for the general public or for any clinical, diagnostic, or regulatory purpose.

- **DrugSim provides computational predictions.** Every result is a model output — a computational estimate — not a laboratory measurement, a clinical finding, or an experimental result of any kind.
- **Results are not clinical diagnoses.** Nothing produced by DrugSim constitutes a medical or clinical diagnosis, for any compound, in any context.
- **Results are not guarantees of safety.** A favourable prediction is not a safety guarantee, and an unfavourable one is not proof of harm. Both require experimental confirmation.
- **Predictions do not replace laboratory or clinical testing.** DrugSim is a prioritisation aid. It does not substitute for in vitro, in vivo, or clinical evaluation at any stage of research or development.
- **Each model covers only its own validated endpoint.** DrugSim currently offers validated predictions for hERG cardiac-channel inhibition and CYP3A4 metabolic inhibition, each independently validated and never combined into a single score. Neither says anything about any other property, endpoint, efficacy measure, or safety concern, and predictions do not combine into a simulation of a whole organism.
- **Results outside the applicability domain may be unreliable.** A structure flagged as outside a model's known chemistry is an extrapolation and should be treated with reduced confidence.

## No regulatory status

DrugSim has not been evaluated, cleared, or approved by any regulatory authority for any purpose, and this deployment makes no claim of regulatory status, certification, or clinical validation. Use of this service does not create any professional, clinical, or regulatory relationship between you and its operators.

## Acceptable use

Do not submit structures you do not have the right to share with this deployment's operators (see [`../privacy/index.md`](../privacy/index.md)), and do not use this service in a way that circumvents its rate limits or access controls.
