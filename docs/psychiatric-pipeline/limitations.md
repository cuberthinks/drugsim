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

- **CYP2D6 and BBB are live but still registered EXPERIMENTAL, not
  promoted.** Both are served through `POST /v1/psychiatric-screening`
  (`drugsim_predict.psychiatric_pipeline`), a separate, explicitly-
  labelled surface from `/predict` -- `run_inference`'s own promotion
  gate would still correctly refuse to serve either through `/predict`
  itself. Every signal from these two carries `reliability_tier:
  "experimental"` in the response; promotion to `VALIDATED FOR INTERNAL
  RESEARCH` was not attempted -- that gate exists for a reason and
  clearing it is a separate, real review step, not a checkbox.
- **DRD2 and HRH1 have no `/predict`-shaped serving path** (no
  classification schema fits a continuous value), but ARE served live
  through the same `POST /v1/psychiatric-screening` endpoint, scored
  directly against their own artifacts. Both also carry
  `reliability_tier: "experimental"`.
- **DRD2's model was retrained for a smaller footprint before going
  live.** Real Render memory metrics showed the existing 2-model
  service already near its 512MB limit; DRD2's original 248MB model
  would very likely have crashed the whole service. Retrained
  (`n_estimators=200, max_depth=20`) to 41MB, at a real, disclosed R²
  cost (0.5994 → 0.4980). See validation.md's "Deployment note."
- **No frontend audit-log/history surface exists for this endpoint
  yet** — unlike `/predict`, results from `/v1/psychiatric-screening`
  are not persisted or retrievable by ID.

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
