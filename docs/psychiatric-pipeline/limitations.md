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

- **Two live attempts both crashed the service and were reverted.**
  `POST /v1/psychiatric-screening` was built and deployed twice; both
  times a real test request crashed `drugsim-predict-api` (confirmed
  OOM kills in Render's own logs). DRD2, then also CYP2D6 and BBB,
  were retrained with bounded hyperparameter grids between attempts —
  a real ~14x reduction in the four new models' local measured
  footprint, which still wasn't enough (see validation.md's
  "Deployment note" for exact sizes/accuracy costs). Currently
  offline-only; see api-integration.md for the full two-incident story
  and what an actual fix would need.
- **Nothing in this pipeline is currently wired into the live
  `drugsim-predict-api` service.** CYP2D6 and BBB remain registered
  (`models/registry/`) but their artifacts are not fetched into the
  live Docker image; DRD2 and HRH1 have no live serving path at all.
  All results come from running the pipeline's own scripts locally.
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
