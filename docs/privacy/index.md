# Privacy Policy

This mirrors the frontend's own Privacy page (`frontend/src/pages/PrivacyPage.tsx`) — the two are kept in sync deliberately; if they ever disagree, the frontend page is what a user actually sees and should be treated as authoritative.

Written for a controlled research/demonstration deployment, not a public consumer product — see [`../terms/index.md`](../terms/index.md) for who this service is intended for.

## What we receive

The molecular structure you submit (as SMILES text), and standard request metadata (timestamp, a correlation ID, and the structure's cryptographic hash — never the structure itself — in server logs). DrugSim does not require an account, and does not collect names, email addresses, or other personal information to run a prediction.

## How submitted structures are handled

A submitted structure may be a compound you consider confidential or pre-patent. It is stored in the prediction audit record (so that a result can later be retrieved and so predictions are traceable — see [`../methodology/index.md`](../methodology/index.md)) but is deliberately kept out of the application's general log stream, which only ever records a one-way hash of it — enforced by an automated test (`tests/security/test_no_structure_in_logs.py`) that fails the build if a real structure ever appears in a log line. Retrieving a stored prediction by ID (`GET /predict/{id}`) is restricted to the same API key that submitted it, whenever key-based access control is configured (`tests/security/test_prediction_ownership.py`) — see `docs/privacy/confidentiality-audit.md` for the finding this closed. Do not submit a structure to this deployment if its confidentiality could not withstand being stored in that audit record.

## Third parties

No analytics, error-tracking, or AI/LLM service of any kind runs in this application, and none receives a submitted structure — there is nothing here to opt out of. The only external network request the frontend makes is a standard font stylesheet load (Google Fonts), which carries no molecule data. The prediction service itself runs on Render's hosting infrastructure, which operates the servers this deployment runs on but does not independently access or process submitted structures. See `docs/privacy/confidentiality-audit.md` for the full accounting of every dependency and external call this project makes.

## Retention

Prediction records are retained for as long as this deployment operates, to preserve scientific traceability and provenance. There is currently no self-service mechanism to request deletion of a specific submission — contact the operators (see the frontend's About page) if you need one removed. See `docs/privacy/confidentiality-audit.md` for the current backup behaviour (local-disk, unredacted, checksummed) and the recommendation to encrypt/relocate it off-host, which has not been implemented.

## What we do not do

DrugSim does not sell or share submitted structures with any third party, and uses them for nothing beyond producing and recording the prediction you requested. It does not use submissions to train or retrain the underlying models — every model is a fixed, validated, checksummed artifact, not something this deployment learns from over time. This is not only a policy statement: `tests/security/test_training_pipeline_isolation.py` scans the codebase and fails the build if any training-related code is ever wired to read from the prediction records at all. If that ever changes, it will require its own explicit, separately documented consent mechanism — never a silent default.
