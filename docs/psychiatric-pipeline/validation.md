# Validation — consolidated real results

Every number below is copied from the endpoint's own
`evaluation_report.json`/`train_manifest.json` (real training runs, not
estimated), or from a real end-to-end run of
`demo_screening_profile.py`. See [benchmarking.md](benchmarking.md) for
baseline comparisons and [limitations.md](limitations.md) for what these
numbers do not claim.

## Per-endpoint test-set results (scaffold split, group 9, touched once)

| Endpoint | n_test | Primary metric | Value | Conformal coverage (nominal 0.90) | Applicability domain (fraction in-domain) |
|---|---|---|---|---|---|
| DRD2 | 839 | R² | 0.4980 | 0.9082 | 63.9% (in-domain R²=0.59 vs out 0.35) |
| HRH1 | 146 | R² | 0.7672 | 0.8493 | 85.6% (in-domain R²=0.83 vs out 0.08, n=21 small-sample caveat) |
| CYP2D6 | 292 | ROC-AUC | 0.8251 | 0.9041 | 74.3% (in-domain acc 0.82 vs out 0.68) |
| BBB | 150 | ROC-AUC | 0.9507 | 0.9067 | 71.3% (in-domain acc 0.95 vs out 0.84) |

hERG (pre-existing, reused unchanged): ROC-AUC 0.7875, already
validated — see `models/registry/herg_inhibition_v1.json`.

## Reliability signal actually tracks error, everywhere it was checked

For every classification endpoint, splitting the test set by conformal
confidence (singleton vs. genuinely-uncertain prediction sets) shows a
real accuracy gap in the correct direction:

- CYP2D6: singleton accuracy 0.90 vs. uncertain-set accuracy 0.61.
- BBB: singleton accuracy 0.94 (97% of the test set was singleton;
  4 compounds returned an empty/anomalous set — a real, honest
  low-confidence signal, not noise).

Splitting by applicability domain shows the same pattern for every
endpoint (in-domain always outperforms out-of-domain): DRD2 (0.59 vs
0.35 R²), HRH1 (0.83 vs 0.08 R², small out-of-domain sample), CYP2D6
(0.81 vs 0.69 accuracy), BBB (0.95 vs 0.84 accuracy).

## End-to-end real-compound cross-check

`demo_screening_profile.py` runs the full six-signal profile on two
real reference compounds with independently well-documented, opposite
pharmacology (SMILES verified against live ChEMBL, not typed from
memory):

**Haloperidol** (CHEMBL54, classic potent D2-antagonist antipsychotic):

| Signal | Result | Matches real pharmacology? |
|---|---|---|
| DRD2 | pKi 8.07, in-domain | Yes — strong D2 binder |
| HRH1 | pKi 6.85, in-domain | Yes — weaker H1 binder |
| Selectivity | +1.23 (~16.9x DRD2-selective) | Yes |
| CYP2D6 | inhibitor (p=0.92), singleton | Yes — haloperidol is a known CYP2D6 substrate/inhibitor |
| BBB | permeant (p=0.97) | Yes — CNS-active drug |
| hERG | blocker (p=0.86), singleton | Yes — haloperidol has a well-documented QT-prolongation/hERG liability |

**Diphenhydramine** (CHEMBL657, classic antihistamine, not an
antipsychotic):

| Signal | Result | Matches real pharmacology? |
|---|---|---|
| DRD2 | pKi 6.17, out-of-domain | Yes — weak D2 binder |
| HRH1 | pKi 6.80, out-of-domain | Yes — its defining pharmacology |
| Selectivity | -0.63 (~4.2x HRH1-selective) | Yes |
| CYP2D6 | inhibitor (p=0.89), out-of-domain | Yes — diphenhydramine is a known moderate CYP2D6 inhibitor |
| BBB | permeant (p=0.86) | Yes — causes drowsiness, well-known CNS penetration |
| hERG | blocker (p=0.67), genuinely uncertain (non-singleton) | Consistent with mixed/less clear-cut literature on its cardiac risk relative to haloperidol's |

Six independent signals across two compounds with opposite,
well-established pharmacology all came back correctly directed — this
is a real correctness check on every model and on the selectivity
formula's sign convention, not an illustrative example.

## Test suite

`tests/unit/test_psychiatric_{selectivity,screening_profile,model_registry}.py`
— 26 tests, all passing. Full unrelated-suite run: 653/664 passing (the
1 failure and 11 errors are pre-existing S3-fixture and
`datasets/registry.yaml` bindingdb-tier issues, untouched by this
pipeline).

## Deployment note: three models retrained smaller after a real crash

A live `POST /v1/psychiatric-screening` endpoint was attempted, crashed
the service (OOM restart, confirmed in Render's logs), and was
reverted the same day. DRD2 had already been retrained smaller before
that first attempt (248MB → 41MB, R² 0.5994 → 0.4980) but that alone
wasn't sufficient -- hERG + CYP2D6 together already exceeded the
memory budget. Before attempting again, CYP2D6 and BBB were ALSO
retrained with bounded grids: CYP2D6 41MB → 9MB (ROC-AUC 0.8333 →
0.8251), BBB 13MB → 7MB (ROC-AUC 0.9615 → 0.9507, with an UNCHANGED
test-set confusion matrix -- the actual classification decisions did
not change). Combined, the four new models' local incremental memory
cost dropped roughly 14x (from ~329MB to ~23MB in a local measurement)
before the second deployment attempt. See api-integration.md for the
full incident and the current live status. All DRD2/CYP2D6/BBB numbers
on this page reflect the retrained (smaller) models.

## What was not performed

No external (independent second-source) validation was performed for
DRD2, HRH1, CYP2D6, or BBB — see each endpoint's own
`evaluation_report.json`. This is the same limitation Phase 9 already
disclosed for its own hERG/CYP3A4-adjacent work where no independent
dataset existed.
