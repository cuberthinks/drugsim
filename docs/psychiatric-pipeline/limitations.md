# Limitations — everything in one place

Scattered across six `evaluation_report.json` files and several docs
otherwise. Consolidated here so nobody has to hunt for the caveats.

## Scientific claims this pipeline does NOT make

(Full reasoning: [scientific-foundation.md](scientific-foundation.md).)

- **DRD2/HRH1/CYP2D6/BBB/hERG scores are not safety or efficacy
  claims.** A favorable multi-objective profile does not mean a
  compound is effective, safe, or ready for any further development
  step.
- **HRH1-selectivity does not mean "won't cause weight gain."** The
  HRH1-weight-gain correlation is real but not the sole mechanism —
  5-HT2C antagonism is at least as strong a correlate in the
  literature.
- **CYP2D6 inhibition-liability is not the same as a patient's
  metabolizer genotype/phenotype.** "Not an inhibitor" does not mean
  "safe for poor metabolizers" — these are genuinely distinct concepts
  a computational inhibition model cannot bridge.
- **BBB-permeant does not mean "clinically active in the CNS."** This
  is a binary passive/measured brain-plasma partitioning call, not a
  therapeutic-exposure claim. Higher LogP correlating with BBB
  permeability is a SIMPLIFIED claim, not a reliable rule — active
  transport and TPSA/HBD often matter more.
- **hERG affinity is a screening proxy, not a clinical arrhythmia
  prediction.** Real Torsades risk depends on multi-channel effects,
  metabolites, and patient factors this model does not capture.

## Data and modeling limitations

- **No external (independent second-source) validation** for DRD2,
  HRH1, CYP2D6, or BBB. Only within-dataset scaffold-split evaluation.
- **HRH1's dataset is small** (1,395 compounds) — comparable in size to
  CYP2D6's *original, wrongly-identified* rejected dataset. Every HRH1
  metric should be read with that size in mind; its out-of-domain test
  subgroup (n=21) is too small for a stable R² estimate.
- **BBB's raw source is class-imbalanced** (~76% BBB-permeant) — ROC-AUC
  and balanced accuracy should be read alongside precision/recall/MCC,
  not alone.
- **The 10 μM inhibitor threshold** (CYP2D6, same convention as
  hERG/CYP3A4) is a literature screening convention, not a universal
  biological constant.
- **Classical models only** for every new endpoint (Random Forest /
  Gradient Boosting / Logistic Regression or Ridge) — no GNN benchmark.
  Justified by small-data regime (largest new dataset is DRD2's 8,204
  compounds) and no existing GNN infrastructure in this repository; not
  mandated by the brief.
- **Selectivity's uncertainty is deliberately conservative** — the sum
  of both models' conformal half-widths, not a variance-reduced
  combination, because assuming the two models' errors are independent
  and Gaussian is not verified.

## Deployment / architecture limitations

- **A live endpoint was attempted and reverted the same day.**
  `POST /v1/psychiatric-screening` was built, deployed, and crashed the
  live `drugsim-predict-api` service on a real test request (confirmed
  OOM restart in Render's own logs — loading hERG + CYP2D6 together
  was already enough to exceed the container's memory budget, before
  BBB/DRD2/HRH1 were even touched). Reverted the same day; see
  api-integration.md for the full incident.
- **Nothing in this pipeline is currently wired into the live
  `drugsim-predict-api` service.** CYP2D6 and BBB remain registered
  (`models/registry/`) but their artifacts are not fetched into the
  live Docker image; DRD2 and HRH1 have no live serving path at all.
  All results in this pipeline come from running the pipeline's own
  scripts locally, against local (or `models-v1` GitHub Release)
  artifacts.
- **DRD2's model was retrained for a smaller footprint** as part of
  the live attempt above — kept even after reverting, since 41MB is
  strictly better than the original 248MB for any future attempt. Real
  R² cost: 0.5994 → 0.4980. See validation.md's "Deployment note."
- **No frontend exists for this pipeline.**

## Process limitations, disclosed rather than hidden

- **Phase 9's original CYP2D6 rejection used the wrong ChEMBL target
  ID** (CHEMBL2035, the muscarinic M5 receptor, not CYP2D6/CHEMBL289).
  This was caught and corrected during this pipeline's own audit — see
  `docs/phase9/endpoint-selection.md`'s erratum and
  data-sources.md's CYP2D6 section. Anything downstream of Phase 9's
  original table should be re-checked against the erratum, not the
  original row.
- **PyTDC's own downloader fails in this environment** (HTTP 403 from
  Harvard Dataverse, no User-Agent set) — BBB's data was fetched via a
  direct httpx call to the same public file instead. Same limitation
  Phase 9 already documented for CYP3A4's own TDC external-validation
  attempt.
