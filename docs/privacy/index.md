# Privacy Policy

This mirrors the frontend's own Privacy page (`frontend/src/pages/PrivacyPage.tsx`) — the two are kept in sync deliberately; if they ever disagree, the frontend page is what a user actually sees and should be treated as authoritative.

Written for a controlled research/demonstration deployment, not a public consumer product — see [`../terms/index.md`](../terms/index.md) for who this service is intended for.

## What we receive

The molecular structure you submit (as SMILES text), and standard request metadata (timestamp, a correlation ID, and the structure's cryptographic hash — never the structure itself — in server logs). DrugSim does not require an account, and does not collect names, email addresses, or other personal information to run a prediction.

## How submitted structures are handled

A submitted structure may be a compound you consider confidential or pre-patent. It is stored in the prediction audit record (so that a result can later be retrieved and so predictions are traceable — see [`../methodology/index.md`](../methodology/index.md)) but is deliberately kept out of the application's general log stream, which only ever records a one-way hash of it. Do not submit a structure to this deployment if its confidentiality could not withstand being stored in that audit record.

## Retention

Prediction records are retained for as long as this deployment operates, to preserve scientific traceability and provenance. There is currently no self-service mechanism to request deletion of a specific submission — contact the operators (see the frontend's About page) if you need one removed.

## What we do not do

DrugSim does not sell, share, or use submitted structures for any purpose other than producing and recording the prediction you requested. It does not use submissions to train or retrain the underlying models — every model is a fixed, validated, checksummed artifact, not something this deployment learns from over time.
