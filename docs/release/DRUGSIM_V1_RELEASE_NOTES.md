# DrugSim v1.0 — Release Notes

## Overview

DrugSim v1.0 is the first official release of a computational ADMET research and prioritisation platform. Given a molecular structure, it returns validated machine-learning predictions for a small set of independently evaluated endpoints, each shown together with its uncertainty, applicability domain, and full model provenance — never as a bare number, never combined into a single overall score.

This release is the product of ten development phases: scientific foundation and data architecture (Phase 1), data pipeline and golden dataset (Phase 2), the first validated endpoint — hERG inhibition (Phase 3, audited in Phase 3.5), independent reliability and robustness testing (Phase 4), a production prediction engine and API (Phase 5), a user-facing frontend (Phase 6), full-system hardening (Phase 7), controlled deployment infrastructure (Phase 8), a second validated endpoint — CYP3A4 inhibition (Phase 9), and final integration, audit, and release preparation (Phase 10, this release).

## Available endpoints

| Endpoint | Category | Model version | Dataset size | Status |
|---|---|---|---|---|
| hERG (KCNH2/Kv11.1) inhibition | Toxicity | 0.1.0 | 9,589 compounds | VALIDATED FOR INTERNAL RESEARCH |
| CYP3A4 inhibition | Metabolism | 0.1.0 | 5,344 compounds | VALIDATED FOR INTERNAL RESEARCH |

Both endpoints passed the same promotion gate on independently-evaluated evidence — CYP3A4 was not admitted on a lower bar than hERG. Full validation detail: [`../phase10/final-scientific-audit.md`](../phase10/final-scientific-audit.md).

## Major capabilities

- **Molecule validation and prediction** for either endpoint, via a web UI or a JSON API.
- **DrugSim Compound Profile** (new in v1.0): one molecule, every validated endpoint it has, grouped by ADMET category (currently Toxicity and Metabolism — a category only appears if a validated endpoint exists for it), each with its own prediction, uncertainty, and reliability. No combined score.
- **Uncertainty on every prediction**, via split conformal prediction with an empirically-verified coverage guarantee.
- **Applicability-domain assessment on every prediction**, via fingerprint similarity, descriptor-space distance, and scaffold membership — degradation from in-domain to out-of-domain chemistry is monotonic and verified for both endpoints.
- **Full provenance on every prediction**: model ID, version, checksum, dataset version, feature version, preprocessing version, uncertainty method, applicability-domain method, input hash, and timestamp — self-describing, without a separate registry lookup.
- **A promotion gate enforced in code**: only endpoints registered with status `VALIDATED FOR INTERNAL RESEARCH` can serve a prediction. No endpoint in this release is `EXPERIMENTAL` or `REJECTED`, but the gate that would refuse to serve one exists and is tested.

## Known limitations

- **CYP3A4's specificity (0.4052) is a real, disclosed weakness** — the model has an asymmetric tendency to over-call "inhibitor." Always shown with its full reliability context, never as a bare label.
- **hERG's external validation uses PubChem directly, not TDC** — TDC's own hERG download endpoint remains unreachable from this environment, so no TDC-canonical benchmark split exists for this dataset. A genuine independent validation was still performed via PubChem AID 588834 (NCATS qHTS screen, 4,030 disjoint compounds, ROC-AUC 0.8696) — strong ranking generalization, but its fixed decision threshold does not adapt to the external set's much lower prevalence (precision 0.22 there). CYP3A4's external validation uses TDC instead (12,152 disjoint compounds, ROC-AUC 0.7758).
- **Both endpoints' 10 µM thresholds are literature screening conventions**, not fixed biological or regulatory boundaries.
- **DrugSim covers exactly two endpoints.** It says nothing about any other ADMET property, drug-likeness, target engagement, efficacy, or clinical outcome.
- **Not a whole-organism simulation.** The two endpoints are never combined, and no version of this product implies they represent a complete picture of a compound's behaviour in a human body.
- Operational limitations (no per-user data isolation, in-memory rate limiting, no real TLS domain in this environment, no committed dependency lockfile) are unchanged from Phase 8 — see [`../deployment/index.md`](../deployment/index.md).
- **Licensing: ChEMBL's ShareAlike terms and the trained model weights — unresolved.** Both live endpoints train directly on ChEMBL data (CC BY-SA 3.0). Whether that copyleft reaches the trained weights and predictions is a genuinely unsettled legal question, flagged as a must-resolve-before-Phase-3 gate in the original risk register (`docs/tds/10-risk-register.md`, R1) but never actually resolved — no legal opinion was obtained, and no later phase re-raised it. This requires a specific legal opinion, not further engineering.

## Scientific disclaimer

> DrugSim provides computational predictions for selected ADMET properties (currently hERG inhibition and CYP3A4 inhibition). Predictions are estimates based on validated computational models and their underlying datasets. They do not constitute clinical advice, clinical safety determinations, or experimental evidence, and do not replace laboratory, preclinical, or clinical testing. DrugSim has not been evaluated, cleared, or approved by any regulatory authority for any purpose.

This disclaimer is also present on the frontend's Terms of Use page and in every prediction's `final_report_status` field.

## Changes from earlier (pre-v1.0) phases

- **Second endpoint added**: CYP3A4 inhibition (Phase 9), integrated through the same prediction pipeline, API, and frontend as hERG — not a parallel system.
- **hERG's model, dataset, and registry entry are unchanged** since Phase 4 — this release did not retrain or modify the validated hERG model.
- **API contract extended, not broken**: `endpoint` is a new optional request field (default: `herg_inhibition`); `predicted_probability` is a new generic response field; `predicted_label` and the conformal `predicted_set` were widened from a hERG-only literal type to a plain string (a type relaxation only — hERG's actual served values are unchanged); a new `method` field on both `conformal` and `applicability_domain` names their methodology explicitly (Phase 10 finding: a prediction previously required a separate registry lookup to know its own methodology by name).
- **New `GET /endpoints` route** for endpoint discovery, used by the frontend's endpoint selector and Compound Profile.
- **New frontend surfaces**: an endpoint selector (distinguishing available/experimental endpoints, never presenting an unvalidated one as normal), and the DrugSim Compound Profile.
- **Two real bugs found and fixed during Phase 10's audit**: `scripts/verify_model_integrity.py` and `scripts/smoke_test_deployment.py` previously only ever checked/exercised the hERG default endpoint — a deployment could have shipped with a silently broken CYP3A4 endpoint and both gates would still report success. Both now check every registered/servable endpoint.
- **One documentation-accuracy bug found and fixed**: the `GET /endpoints` route's own docstring incorrectly claimed it was unauthenticated like `/health`; the code was already correct (gated like `/model`), only the comment was wrong.
- **Stale product-positioning copy fixed**: the frontend's About and Terms pages still said DrugSim covered "a single validated endpoint — hERG... only," which became false the moment CYP3A4 was promoted in Phase 9 and was never updated until this release.

## Deployment information

Docker Compose deployment (FastAPI prediction service, static frontend behind Caddy, PostgreSQL+RDKit for the broader platform). Full guide: [`../deployment/index.md`](../deployment/index.md). Pre-deploy gates (`scripts/verify_model_integrity.py`, `scripts/smoke_test_deployment.py`) now cover every registered endpoint, not only hERG, as of this release.

## Final release decision

See [`../phase10/DRUGSIM_V1_FINAL_REPORT.md`](../phase10/DRUGSIM_V1_FINAL_REPORT.md) for the full release gate evaluation and final decision.
