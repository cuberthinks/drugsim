# Phase 3 Model Validation Report — hERG Inhibition Baseline

**Model:** `herg_inhibition` v0.1.0 · **Status: EXPERIMENTAL**

---

## 1. Endpoint selection and justification

**Blocker: Phase 2's database has no real bioactivity data to inspect.** Phase 2 built the full ETL/registry/bulk-load infrastructure but never populated a live Postgres (no Docker in that environment either) — the only data actually processed was a 28-compound synthetic chemistry reference set with no ADMET labels. "Analyze the validated Phase 2 database" as literally specified was not possible; this is reported here rather than silently substituted without comment, per the instruction to stop and report missing critical data.

**Resolution taken:** TDC (Therapeutics Data Commons), the source Phase 1's own registry pre-approved specifically for ADMET training (`datasets/registry.yaml`, `role: admet_training`, tier `mixed` with FreeSolv hard-gated black), was the natural first choice — but its Harvard Dataverse download endpoint is blocked by an AWS WAF challenge from this environment (verified: `curl -sI` returns `403`/`x-amzn-waf-action: challenge`; general HTTPS to other hosts works fine). ChEMBL — the top-ranked, cleanest-licensed source in the same registry — was used directly via its public REST API instead, which **is** reachable and supports full pagination.

**Candidates compared by live query before choosing** (total IC50/binding records available):

| Candidate | Target | Total records | Notes |
|---|---|---|---|
| **hERG (selected)** | CHEMBL240, KCNH2/Kv11.1, confidence 9 | 17,099 | Cardiotoxicity; the most externally-benchmarked safety endpoint in cheminformatics |
| CYP3A4 | CHEMBL340, confidence 9 | 13,887 | Metabolism/DDI risk |
| P-glycoprotein | CHEMBL4302, confidence 9 | 2,654 | Efflux transporter |

*Correction (Phase 3.5 audit): originally reported as "19,807 across all potency bands", computed by summing seven overlapping potency-band queries. Each of the six internal boundaries (100/1,000/4,000/10,000/40,000/100,000 nM) was inclusive on both sides, double-counting every record at exactly a boundary value — a real, verified artifact (2,708 excess), not a second, larger population. The correct total, matching the single unfiltered query `fetch_chembl_data.py` actually paginated over, is 17,099. This does not change the endpoint-selection conclusion — hERG remains the largest of the three candidates by a wide margin — only the cited figure.*

hERG won on **usable compound count** (most data of the three), **endpoint definition** (single, unambiguous, direct-binding confidence-9 target — no target-family ambiguity), and **external validation potential** (the deepest published QSAR literature of any ADMET/Tox endpoint, enabling real comparison). It was not chosen because it "sounds impressive" — the comparison table above was computed and reviewed before selecting it.

**Unit consistency, label quality, missingness:** IC50 in nM is ChEMBL's own standardised field (`standard_units`/`standard_value`), not a self-reported or free-text value; missingness is handled by dropping non-`nM` and censored (`>`,`<`,`~`, etc.) records rather than coercing them. **Conflicting measurements:** discordant compounds (>10× IC50 spread) are excluded from training entirely, never averaged over.

---

## 2. Dataset

Built by `models/admet/herg_inhibition/fetch_chembl_data.py` + `build_dataset.py`, reusing Phase 2's `drugsim_chem.process_structure` (parsing/standardisation/identity) and `drugsim_quality.aggregation.aggregate_continuous` (discordance-aware aggregation) directly — no chemistry or aggregation logic was reimplemented.

| Field | Value |
|---|---|
| Dataset ID / version | `herg_inhibition` / `v1` |
| Endpoint | hERG inhibition, binary: blocker if aggregated IC50 ≤ 10,000 nM (10 µM), else non-blocker |
| Threshold justification | Literature convention (1–30 µM range used across published hERG QSAR studies); **not** a universal biological constant — stated as a modelling choice |
| Source | ChEMBL REST API, direct, complete population (17,097 raw IC50/nM records for CHEMBL240 on 2026-08-08 — not a sample) |
| Filtering rules | `standard_relation == '='` only (censored excluded per TDS §6.3.1); ChEMBL-flagged "Potential transcription/author error" records excluded; structures standardised via `drugsim_chem` (0 quarantined); flagged mixtures excluded (27); measurements grouped by **standardised inchikey_full** (merges salt forms of the same entity before aggregating potency); discordant entities (>10× spread) excluded (148) |
| Aggregation method | Geometric mean of nM values (`aggregate_continuous`, `is_potency=True`) |
| Final compound count | **9,589** |
| Label distribution | 6,363 blocker (66.4%) / 3,226 non-blocker (33.6%) |
| Chemical diversity | 5,079 distinct Bemis-Murcko scaffolds across 9,589 compounds |
| Provenance | `datasets/raw/chembl_herg_ic50_manifest.json` (sha256 `098527c1...`), `datasets/processed/herg_inhibition_dataset_manifest.json` (sha256 `6c0ecaaf...`) — both reproducible via the committed scripts, though re-running `fetch_chembl_data.py` queries a live API that may have gained records since retrieval (stated limitation, §9) |

Raw/processed CSVs are gitignored per existing project convention (`datasets/raw/*`, `datasets/processed/*` — data lives outside git, only the reproducing code and manifests are tracked); this report and `models/registry/herg_inhibition_v1.json` are the durable record of what was built.

---

## 3. Features

Computed by `models/admet/herg_inhibition/prepare_features.py`, exclusively via `drugsim_chem` (no reimplementation):

- **18 physicochemical descriptors** (MW, exact mass, Crippen LogP, molar refractivity, TPSA, rotatable bonds, aromatic rings, ring count, heavy atoms, formal charge, HBD/HBA in both Lipinski and strict conventions, heteroatom count, fraction Csp3, stereocentre count, largest ring size).
- **Morgan/ECFP4-equivalent fingerprints**, radius 2, 2048 bits, **chirality-aware** (see the bug found and fixed in §5).
- `feature_set_id` (ADR-005 content addressing): `a3ee2afe...` — pins descriptor spec, RDKit version (2025.03.3), and standardisation pipeline version together.

---

## 4. Model

Three classical candidates trained and compared on the validation split — none assumed in advance:

| Candidate | Validation ROC-AUC |
|---|---|
| **Random Forest (selected)** | **0.8394** |
| Gradient Boosting | 0.7766 |
| Logistic Regression | 0.7056 |

- Algorithm: `sklearn.ensemble.RandomForestClassifier`
- Hyperparameters: `n_estimators=500, max_depth=None, class_weight="balanced"` (selected via a small grid on the validation split only)
- Random seed: 42 (fixed throughout: model, y-scrambling permutations, train/test proxy split)
- ~9.6k compounds is squarely the small-data regime (TDS §6.1); no deep learning architecture was used or needed.

---

## 5. Validation methodology

Global scaffold-level `split_group` (0–9) per **ADR-009**: `sha256(scaffold_key || split_salt) mod 10`, deterministic, assigned once. Acyclic compounds (no Bemis-Murcko scaffold) fall back to their own standardised SMILES as a singleton scaffold key rather than collapsing onto one shared group (1 compound affected).

| Group(s) | Role | n |
|---|---|---|
| 0–6 | Train | 6,792 |
| 7 | Calibration (conformal only, never used for training/validation) | 976 |
| 8 | Validation (hyperparameter selection) | 1,021 |
| 9 | Test (touched once, at evaluation) | 800 |

### Leakage checks (`check_leakage.py`) — **overall PASS**

| Check | Result |
|---|---|
| Duplicate leakage | PASS — 0 compounds appear in more than one split group |
| Scaffold leakage | PASS — direct re-check from the dataset CSV: 0 of 5,079 scaffolds span more than one split group |
| Preprocessing leakage | PASS — `StandardScaler` fit only on train; feature computation is per-compound, no cross-row statistic |
| Target leakage | PASS — feature columns and label-adjacent columns (`aggregated_ic50_nm`, `label`, `value_spread_log10`) have zero overlap |
| Near-duplicate leakage | REVIEW — 15 train/test pairs (1.88% of test) at Tanimoto ≥ 0.95 despite different scaffolds; expected occasionally, not a construction defect |
| Exact feature collision | REVIEW — 3 of 800 test compounds (0.375%) share a folded fingerprint with a training compound; manually inspected, confirmed to be a stereo-specified-vs-unspecified pair (a residual folding collision), distinct from the bug below |

**A real bug was found and fixed during this check**, not merely reported: `compute_morgan_fingerprint` used RDKit's achiral default, so 30 of 800 test compounds were exact fingerprint duplicates of a training compound purely because they were unflagged stereoisomer pairs — the model could not distinguish inputs its own labels treat as different entities. Fixed (`include_chirality=True` by default in `src/drugsim_chem/fingerprints.py`); collision count dropped 30→3. Model retrained after the fix; performance was materially unchanged (0.8385→0.8394 validation ROC-AUC), confirming this was a correctness fix, not a performance lever.

### y-scrambling (`y_scrambling.py`) — **PASS**

10 repeats, same algorithm/hyperparameters/seed as the real model, labels permuted before training:

| | ROC-AUC |
|---|---|
| Real model (validation) | 0.8394 |
| Scrambled (mean ± std, n=10) | 0.4890 ± 0.0427 |

Clean collapse to chance, clearly separated (>3 std) from the real model. No evidence of a leak, duplicate, or confounded descriptor driving performance.

---

## 6. Evaluation (dual-split, TDS §6.4.1)

Held-out test group (split_group 9), touched exactly once:

| Metric | Global split (honest) | Benchmark-proxy (random split) |
|---|---|---|
| n | 800 | 800 |
| ROC-AUC | **0.7875** | 0.8488 |
| Average precision | 0.8446 | 0.9136 |
| Balanced accuracy | 0.6495 | 0.7418 |
| Precision / Recall | 0.70 / 0.91 | 0.81 / 0.89 |
| Confusion matrix | TN 121, FP 190, FN 44, TP 445 | TN 160, FP 109, FN 59, TP 472 |

**Limitation on the benchmark column:** this dataset was built directly from ChEMBL, not via TDC, so no true TDC-canonical split exists for these exact 9,589 compounds. The "benchmark_split" column is a **random-split proxy** on the same data/model/procedure, not a genuine external leaderboard number. **ROC-AUC gap: +0.0613** — this is the leakage the scaffold split removes, consistent with ADR-009's expectation that global splits report lower but honest numbers. Reporting only the favourable column would have been the easiest and most damaging misrepresentation available; both are published per the TDS data contract.

The model favours recall over precision (0.91 vs 0.70) — it catches most true blockers at the cost of real false-alarm volume. For a triage/screening tool, erring toward sensitivity on a cardiac safety endpoint is a defensible operating point, but it is a choice, not a neutral default, and is not currently tuned to any specific cost ratio.

---

## 7. Applicability domain (TDS §6.8)

Three components: max Tanimoto similarity to the training set, k-NN distance in standardised descriptor space (k=5, threshold = 95th percentile of training-internal distances), and scaffold-seen-in-training (boolean).

**Structural finding, not a defect:** the literal 3-signal verdict gives **0/800 "in_domain"** on this test set. This is mathematically forced: ADR-009's scaffold split guarantees every test-group scaffold is absent from training, so the "scaffold seen" indicator is always triggered here by construction — it only becomes a meaningful signal for a real query compound at serving time, never on a leakage-preventing holdout set. Reported plainly rather than silently redefining the AD to manufacture an "in_domain" bucket on this particular evaluation.

A supplementary 2-signal verdict (Tanimoto + k-NN only, scaffold excluded) shows the AD carries real, validated signal:

| Verdict | n | Accuracy |
|---|---|---|
| in_domain | 500 | **75.4%** |
| borderline | 166 | 66.9% |
| out_of_domain | 134 | **58.2%** |

Monotonic degradation from in-domain to out-of-domain — exactly the behaviour an applicability domain should show.

---

## 8. Uncertainty and calibration (TDS §6.7)

**Split (inductive) conformal prediction**, calibration group (split_group 7, n=976) used for the first and only time in this pipeline:

| | Value |
|---|---|
| Nominal confidence | 90% |
| **Empirical coverage (test group)** | **89.88%** |
| Within tolerance | Yes |
| Singleton (confident) predictions | see `reliability_report.json` |

Empirical coverage validated directly, not assumed, per TDS §6.7's promotion-gate requirement.

**Post-hoc calibration** (Platt and isotonic, fit on the calibration group only) was evaluated and **did not improve** on the raw model output:

| | Brier score | ECE |
|---|---|---|
| Raw | 0.1864 | 0.0597 |
| Platt | 0.1896 | 0.0725 |
| Isotonic | 0.1866 | 0.0627 |

**Recommendation: use raw `predict_proba`.** This is reported as a negative result rather than forcing a calibration step that does not help.

---

## 9. Limitations

- **No real Postgres in this environment** (same limitation as Phase 2). The model registry entry (`models/registry/herg_inhibition_v1.json`) is a file-based substitute for the Core DB `model`/`model_version`/`model_validation_record` rows — complete in content, not queryable as a real registry row.
- **No true TDC-canonical benchmark split** exists for this exact dataset (§6); the "benchmark_split" figure is a same-data random-split proxy, not an external leaderboard comparison.
- **Not independently externally validated.** No second, wholly separate dataset (e.g. a different hERG source) was used to confirm generalisation beyond this ChEMBL pull.
- **Single-pass hyperparameter search** (a small fixed grid on one validation split), not cross-validated or bootstrapped for confidence intervals on the reported metrics.
- **Fetch is not bit-reproducible long-term**: `fetch_chembl_data.py` queries a live external API; ChEMBL may add records between runs, so exact re-runs will not reproduce the identical 17,097-row raw file (the manifest's sha256 pins the exact version used here).
- **Precision/recall trade-off is untuned** to any specific downstream cost ratio (missed blocker vs. false alarm).
- **Known, separate identity-model limitation carried over from Phase 2**: `inchikey_full`/`parent_inchikey` coincide for parent-identified compounds, so two distinct salt-form ChEMBL records that standardise to the same entity are correctly merged for potency aggregation here (§2) but would collide as duplicates in `compound_split_assignment` if loaded into the real schema — unresolved, flagged in the Phase 2 report, still applicable.
- **No QMRF or multi-reviewer sign-off.** This is a single-pass baseline, not a reviewed regulatory artefact.

---

## 10. Final status

**EXPERIMENTAL**

Justification: the model shows real, non-artifactual signal (y-scrambling collapses cleanly to chance), generalises honestly under a leakage-controlled scaffold split (test ROC-AUC 0.79), has a validated uncertainty method (conformal coverage within 0.1% of nominal) and a working, empirically-confirmed applicability domain (monotonic accuracy gradient). It has **not** completed the TDS §6.4.2 promotion-gate process to `champion` (no QMRF, no independent external validation set, no multi-reviewer review, single-pass hyperparameter search) and was built as this project's first ADMET model end-to-end proof, not a production candidate. It is **not** production-ready and **not** clinically validated.
