# Phase 12: retrain on curated data, compare against production

**Scope, stated plainly**: this phase builds a curated-data training path
for both live endpoints, retrains a candidate model on it, and compares it
against production. **It does not deploy anything.** No registry file,
`final_report_status`, or served artifact changed as a result of this
work — verified by SHA-256 before and after (see "Verification" below).

## Why this exists

Phase 11 (`docs/data-curation/`) built `drugsim_curation`, which reproduces
the hERG/CYP3A4 ChEMBL pipeline but retains and tags discordant or
otherwise-excluded measurements instead of silently dropping them, gating
a compound into `training_eligible=True` only if it has a usable,
non-discordant, licence-resolved measurement. That phase explicitly
stopped short of retraining, deferring to "a future modelling phase [that]
would explicitly choose to consume `datasets/curated/`." This is that
phase.

## Set expectations before reading the numbers

`datasets/curated/{endpoint}_curated_compounds.csv` has the same
`training_eligible=True` count as production's `final_compound_count` for
both endpoints (9,589 / 5,344). Both pipelines share the same source data,
aggregation policy, and discordance threshold — curation only reorganises
*what happens* to a discordant compound, not the threshold itself. So this
comparison was always more likely to be a **validation that curation
didn't degrade anything** than a search for an uplift. That is exactly
what it found, for both endpoints — reported honestly below rather than
reframed as something it isn't.

## Methodology

For each endpoint, three new scripts mirror the production pipeline
exactly except for the data source, isolating the effect of curated vs.
processed data from any confound of a different training recipe:

- `prepare_features_curated.py` — reads
  `datasets/curated/{endpoint}_curated_compounds.csv`, filters to
  `training_eligible == True`, and computes features with the **identical**
  scaffold-split logic (`SPLIT_SALT`, `_split_group`) and the **identical**
  descriptor/fingerprint code (`drugsim_chem.compute_descriptors`/
  `compute_morgan_fingerprint`) as production's `prepare_features.py`.
  Asserts `descriptor_spec_version`/`rdkit_version`/
  `standardization_pipeline_version` match production's committed
  manifest before proceeding, so the two pipelines can't silently diverge.
- `train_curated.py` — the same three-candidate comparison (Random
  Forest grid, Gradient Boosting, Logistic Regression), same
  `RANDOM_SEED=42`, same train/validation groups as production's
  `train.py`. Writes to `experiments/curated_v1/artifact/`, never to the
  production `artifact/` directory.
- `evaluate_curated.py` — the same held-out scaffold-split (test group 9)
  metrics as production's `evaluate.py`, plus a cross-evaluation grid:
  both the production model and the new curated-data model, scored
  against both test sets. Valid because both feature sets are built by
  the same descriptor/fingerprint code, so a 2066-column feature vector
  means the same thing in either dataset.

## Result: identical training populations, for both endpoints

Independently verified by inchikey before any training happened:

| | hERG | CYP3A4 |
|---|---|---|
| Curated `training_eligible=True` compounds | 9,589 | 5,344 |
| Compounds shared with production's set | 9,589 / 9,589 | 5,344 / 5,344 |
| Label mismatches among shared compounds | 0 | 0 |
| `split_group` mismatches among shared compounds | 0 | 0 |

Curation reproduces the exact same eligible population, labels, and
scaffold-split assignment as production, for both endpoints. There was
never a different training set for the candidate model to learn from.

## Result: hyperparameter selection matched exactly

Both endpoints' `train_curated.py` runs selected the same algorithm and
hyperparameters as production, with the same validation-group ROC-AUC on
every candidate:

| | hERG (validation ROC-AUC) | CYP3A4 (validation ROC-AUC) |
|---|---|---|
| Random Forest (selected) | 0.8394 (both) | 0.7870 (both) |
| Gradient Boosting | 0.7766 (both) | 0.7298 (both) |
| Logistic Regression | 0.7056 (both) | 0.6866 (both) |

## Result: cross-evaluation grid

### CYP3A4 — clean, direct comparison (no confounds)

CYP3A4's deployed model has no tree-count truncation (500 trees both
sides), so this is a single, unambiguous grid:

| | scored on production test | scored on curated test |
|---|---|---|
| **Production model** | ROC-AUC 0.7995 | ROC-AUC 0.7995 |
| **Curated-data model** | ROC-AUC 0.7995 | ROC-AUC 0.7995 |

**Headline delta: +0.0000.** All four cells are numerically identical —
the strongest possible confirmation that curation didn't change what the
model learns for CYP3A4.

### hERG — one real-world wrinkle surfaced by this comparison

Building this comparison surfaced something not previously visible from
either endpoint's own evaluation report in isolation: **the deployed
`artifact/model.joblib` for hERG is not the model `evaluation_report.json`
was computed from.** Per `models/registry/herg_inhibition_v1.json`'s
`deployment_variant` block (a pre-existing, disclosed fact — not
introduced here), the deployed artifact is the first 200 of an
originally-trained 500-tree ensemble, truncated post-hoc to fit a 512MB
Render memory limit. The committed `evaluation_report.json` (ROC-AUC
0.7875) reflects the full, untruncated 500-tree model.
`train_curated.py`'s hyperparameter search independently selected 500
trees for the curated model — so comparing it straight against the
*deployed* 200-tree artifact would conflate "effect of curated data" with
"effect of ensemble size." `evaluate_curated.py` therefore scores against
both:

| | scored on production test | scored on curated test |
|---|---|---|
| **Production model (deployed, 200 trees)** | ROC-AUC 0.7843 | ROC-AUC 0.7843 |
| **Production model (full backup, 500 trees)** | ROC-AUC 0.7875 | ROC-AUC 0.7875 |
| **Curated-data model (500 trees)** | ROC-AUC 0.7875 | ROC-AUC 0.7875 |

**Equal-tree-count headline delta (500 vs. 500): +0.0000.** The
as-deployed delta (+0.0032) is entirely explained by ensemble size, not
data quality — the identical-population finding above already rules out a
data-driven explanation for it.

## Recommendation

**Do not deploy.** Not because the curated candidate is worse — it is
numerically identical to production on every metric, for both endpoints —
but because there is nothing to deploy: the curated pipeline reproduces
today's production training set exactly, so a curated-data retrain is not
a different model, just the same model re-derived through a more
auditable, better-provenanced pipeline. The value delivered here is
Phase 11's traceability and discordance-handling infrastructure, already
shipped, not a new model.

Where this *would* matter: the moment a second, non-ChEMBL data source is
added, or new ChEMBL records arrive that shift what's discordant, curation
and the current `build_dataset.py` will start to diverge in practice
rather than only in principle. This comparison should be re-run at that
point, since its current "no difference" result is a direct consequence of
today's single-source, identical-threshold setup, not a general property
of the curation pipeline.

## Verification

- Independent per-compound inchikey comparison (training-eligible set,
  labels, split_group) confirmed identical for both endpoints — before
  any training ran, not inferred after the fact.
- SHA-256 of `datasets/processed/{herg,cyp3a4}_inhibition_{dataset.csv,
  features.npz}`, `fetch_chembl_data.py`, `build_dataset.py`,
  `prepare_features.py`, `train.py`, `evaluate.py`, the deployed
  `artifact/model.joblib`/`scaler.joblib` for both endpoints, and both
  `models/registry/*.json` files — all unchanged, checked before and
  after this phase's entire implementation.
- All new outputs live under new files only: `prepare_features_curated.py`,
  `train_curated.py`, `evaluate_curated.py` per endpoint, and
  `experiments/curated_v1/` (train manifest, own-evaluation report,
  cross-evaluation report — the `artifact/` subdirectory holding the
  actual `.joblib` files is gitignored, same convention as production's).

## What a future deployment phase would need to do

Nothing here is a blocker — quite the opposite, this phase found the two
pipelines agree. A future phase that *does* want to promote a
curated-data-trained model would still need to: register it properly in
`models/registry/` (there is no automated promotion path today — see
Phase 11's audit of `model_registry.py` — registration is a manual JSON
edit), run the existing golden-regression and leakage-check suites against
it, and decide how to handle the eventual case where curated and processed
populations actually diverge.
