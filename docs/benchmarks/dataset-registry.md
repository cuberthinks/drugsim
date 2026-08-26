# Benchmark Dataset Registry

Field-by-field citation trail for every number in
`frontend/src/lib/benchmarks.ts`. If a number on `/benchmarks` looks wrong,
this is where to check it against the original source.

## hERG (KCNH2/Kv11.1) inhibition

| Field | Value | Source |
|---|---|---|
| `benchmark_id` | `herg_inhibition_v1_scaffold_split` | — |
| `dataset` | ChEMBL, target CHEMBL240, IC50 activities | `models/admet/herg_inhibition/fetch_chembl_data.py` |
| `dataset_version` | v1 | `models/registry/herg_inhibition_v1.json` |
| `n_total` (final compound count) | 9,589 | `models/admet/herg_inhibition/phase4/02_validate_endpoint_report.json` |
| `n_test` (scaffold split) | 800 | `models/admet/herg_inhibition/evaluation_report.json` → `global_split.n_test` |
| `split_method` | Scaffold (ADR-009), split_group 9 held out | same file → `global_split.description` |
| `model_version` | 0.1.0 | `models/registry/herg_inhibition_v1.json` |
| `evaluation_date` | 2026-08-09 | `evaluation_report.json` → `generated_at` |
| ROC-AUC (scaffold split) | 0.7875 | `evaluation_report.json` → `global_split.roc_auc` |
| Balanced accuracy | 0.6495 | same file → `global_split.balanced_accuracy` |
| F1 / precision / recall | 0.7918 / 0.7008 / 0.91 | same file → `global_split.{f1,precision,recall}` |
| Confusion matrix | tn 121, fp 190, fn 44, tp 445 | same file → `global_split.confusion_matrix` |
| Random-split ablation, ROC-AUC gap | 0.8488, gap 0.0613 | same file → `benchmark_split`, `roc_auc_gap` |
| Baselines (majority/random/descriptor-only) | see page | `models/admet/herg_inhibition/phase4/08_baseline_comparison_report.json` |
| External validation dataset | PubChem AID 588834 (NCATS qHTS) | `models/admet/herg_inhibition/phase4/04_external_validation_report.json` → `external_source` |
| External validation metrics | n=3,919 (overlap excluded), ROC-AUC 0.8696 | same file → `performance.excluding_exact_training_overlap` |
| Applicability-domain tiers | 4 Tanimoto-range tiers | `models/admet/herg_inhibition/phase4/05_applicability_domain_report.json` → `tiers` |
| Calibration (Brier/ECE/coverage) | internal + external | `models/admet/herg_inhibition/phase4/06_uncertainty_calibration_report.json` |
| Licence | CC BY-SA 3.0 (ChEMBL, EMBL-EBI) | `datasets/registry.yaml` → `sources[chembl].license` |

## CYP3A4 metabolic inhibition

| Field | Value | Source |
|---|---|---|
| `benchmark_id` | `cyp3a4_inhibition_v1_scaffold_split` | — |
| `dataset` | ChEMBL, target CHEMBL340, IC50 activities | `models/admet/cyp3a4_inhibition/fetch_chembl_data.py` |
| `dataset_version` | v1 | `models/registry/cyp3a4_inhibition_v1.json` |
| `n_total` (final compound count) | 5,344 | `models/registry/cyp3a4_inhibition_v1.json` → `dataset.final_compound_count` |
| `n_test` (scaffold split) | 459 | `models/admet/cyp3a4_inhibition/evaluation_report.json` → `global_split.n_test` |
| `split_method` | Scaffold (ADR-009), split_group 9 held out | same file → `global_split.description` |
| `model_version` | 0.1.0 | `models/registry/cyp3a4_inhibition_v1.json` |
| `evaluation_date` | 2026-08-10 | `evaluation_report.json` → `generated_at` |
| ROC-AUC (scaffold split) | 0.7995, 95% CI [0.7593, 0.8382] | same file → `global_split.{roc_auc,confidence_interval_95pct}` |
| Balanced accuracy | 0.652 | same file → `global_split.balanced_accuracy` |
| F1 / precision / recall | 0.8185 / 0.7514 / 0.8987 | same file → `global_split.{f1,precision,recall}` |
| MCC / specificity | 0.3564 / 0.4052 | same file → `global_split.{matthews_corrcoef,specificity_recall_negative}` |
| Confusion matrix | tn 62, fp 91, fn 31, tp 275 | same file → `global_split.confusion_matrix` |
| Random-split ablation, ROC-AUC gap | 0.8391, gap 0.0396 | same file → `benchmark_split`, `roc_auc_gap` |
| Baselines (majority/logistic/RF-descriptors-only) | see page | `models/admet/cyp3a4_inhibition/baselines_report.json` |
| External validation dataset | TDC `CYP3A4_Veith` (PubChem AID 1851) | `models/admet/cyp3a4_inhibition/external_validation_report.json` → `external_dataset` |
| External validation metrics | n=12,152 (disjoint), ROC-AUC 0.7758 | same file → `metrics_on_disjoint_external_set` |
| Applicability-domain tiers | in-domain/borderline/out-of-domain, plain accuracy | `models/admet/cyp3a4_inhibition/reliability_report.json` → `applicability_domain.two_signal_accuracy_by_verdict` |
| Calibration (Brier/ECE/coverage) | `reliability_report.json` → `calibration`, `conformal_prediction.empirical_coverage` |
| Licence | CC BY-SA 3.0 (ChEMBL, EMBL-EBI) | `datasets/registry.yaml` → `sources[chembl].license` |

## Overall database scale (not either endpoint's training set)

| Field | Value | Source |
|---|---|---|
| Distinct compounds | 2,921,148 | `datasets/registry.yaml` → `sources[chembl].scale.distinct_compounds` |
| Bioactivity measurements | 24,527,044 | same → `scale.activities` |
| Assays | 1,970,438 | same → `scale.assays` |
| Targets | 18,552 | same → `scale.targets` |

These describe the ChEMBL release DrugSim's training data was drawn from —
**not** the size of either endpoint's own labelled training set (9,589 for
hERG, 5,344 for CYP3A4, both far smaller). The Benchmark page keeps these in
a visually and structurally separate section for exactly this reason.

## Endpoints considered and not built

The task that produced this page suggested checking DILI, Ames, aqueous
solubility, human intestinal absorption, bioavailability, Caco-2
permeability, BBB permeability, and half-life as benchmark candidates. None
of these has a live DrugSim model, so none appears on the Benchmark page.
Per `docs/phase9/endpoint-selection.md`, several TDC-sourced candidates in
this list (bioavailability, half-life, Caco-2, solubility, VDss, clearance,
LD50) were passed over specifically because TDC does not document units for
them — a real, disclosed reason, not an oversight. DILI and AMES were not
selected for Phase 9's endpoint expansion for reasons documented in that same
file. Nothing here should be read as "coming soon" — building a new endpoint
is a full validation undertaking (the same one hERG and CYP3A4 each went
through), not a page addition.

## Individual molecule explorer — ground truth citations

| Compound | Public ground truth | Citation |
|---|---|---|
| Aspirin | Non-blocker | No hERG signal reported in the pharmacovigilance literature. |
| Terfenadine | Blocker | Withdrawn from the US market in 1998 for hERG-mediated QT prolongation/torsades de pointes (Woosley RL et al., "Mechanism of the cardiotoxic actions of terfenadine," JAMA 1993;269(12):1532-6). |
| Dofetilide | Blocker | FDA-approved Class III antiarrhythmic; hERG (IKr) blockade is its labelled mechanism of action. |
| Paracetamol | Non-blocker | No hERG signal reported in the pharmacovigilance literature. |

Live predictions for all four were captured on 2026-08-24 against the
production API (`https://drugsim-predict-api.onrender.com/predict`). Values
will differ if the model is ever retrained — `evaluatedAt` on each entry in
`frontend/src/lib/benchmarks.ts` records exactly when these specific numbers
were captured, not a claim that they are permanent.

## Individual molecule explorer — Claude spot-check

Each card also carries a single Claude prediction (`claudeSpotCheck` in
`frontend/src/lib/benchmarks.ts`), recorded 2026-08-25 directly in a
development conversation: canonical SMILES only, with the compound name
withheld until after the prediction was made, matching the
"no identifying metadata" rule in `ai-comparison-protocol.md`. It is **not**
that protocol — one run per compound, not three; no temperature control; no
fresh session per run — and it does not fill in the aggregate table's
"Not evaluated" cells above, which require the full protocol run against
DrugSim's own held-out test set. Aspirin, Terfenadine, and Paracetamol have a
genuine blind estimate. Dofetilide does not: its ground truth was seen
(while retrieving its file entry) before an independent prediction could be
made, so `predictedLabel` is `null` and `notAvailableReason` states why,
rather than a retrofitted or estimated value standing in for a real one.

A GPT dataset was separately proposed for this same purpose but not used: the
compound name had been disclosed to GPT alongside the SMILES, which risks
recall of a well-known public fact about the drug (e.g. Terfenadine's 1998
market withdrawal) rather than structure-based reasoning — exactly what the
protocol's "no identifying metadata" rule exists to prevent. GPT remains
**not evaluated** anywhere on this page.

## Claude — 30-compound informal subset evaluation

A second, larger Claude evaluation (`CLAUDE_HERG_SUBSET_EVALUATION` in
`frontend/src/lib/benchmarks.ts`) runs against 30 compounds drawn from
DrugSim's actual 800-compound scaffold-split hERG test set (`split_group ==
9` in `datasets/processed/herg_inhibition_features.npz`, joined to SMILES via
`datasets/processed/herg_inhibition_dataset.csv`). The sample is
proportionally stratified (seed 42) to the real test set's 489/311
blocker/non-blocker split, giving 18 blocker / 12 non-blocker. Full
per-compound reasoning and verdicts:
`models/admet/herg_inhibition/claude_informal_subset_evaluation.json`.

**Independence, not the protocol.** Each of the 30 compounds was dispatched
to an isolated subagent with no shared context — SMILES only, no ground
truth, no visibility into any other compound's reasoning or answer. That is
genuine independence across compounds, but it is not the documented
protocol's "3 runs of the same compound in fresh sessions": that specific
requirement is not achievable within a single Claude conversation, since
there is no way to make a later turn forget an earlier one's answer to the
same question. Recorded 2026-08-25, single run per compound.

**A methodology failure during this run, corrected before any data was
used.** The first attempt used the ai-comparison-protocol.md's exact fixed
prompt (forced single-word "Yes"/"No", no reasoning permitted). All 10
compounds run this way returned "No" regardless of true label. Asked to
explain its own answer, the first subagent admitted the "No" was "a fast
pattern-based guess, not a rigorous pharmacophore workup," and on actual
inspection the correct read was "Yes" — a real basic-amine/aromatic-flanking
pharmacophore it had not engaged with under the terse format. All 10 results
from that attempt were discarded, and the prompt was changed to require 2-4
sentences of structural reasoning before the final verdict. This is a
disclosed deviation from the protocol's exact wording (which forces a bare
one-word answer for GPT), made because the terse format was directly shown
to produce non-representative shortcuts for Claude specifically, not because
matching GPT's format was undesirable in principle.

**ROC-AUC was initially not computable**, same reasoning as the GPT protocol:
a bare Yes/No verdict carries no probability. It was added afterward by
resuming each of the 30 already-dispatched subagents (not fresh dispatches,
to reuse their existing reasoning and cut token cost) and asking each for a
0-100 probability consistent with its own prior structural analysis. All 30
follow-up scores were directionally consistent with the original binary
verdicts (score >= 50 iff the original verdict was "blocker" — checked
programmatically, zero mismatches). ROC-AUC computed from those scores:
**0.6759**.

**The result is real and not flattering: balanced accuracy 56.9%, F1 68.4%,
both lower than DrugSim's own 65.0%/79.2% on the full 800.** This is
disclosed as such on the page, with an explicit note that 30 compounds is far
too small a sample to conclude DrugSim is "better" from this alone — the
same caution applied everywhere else GPT/Claude comparisons appear on this
page.

This is 30 of 800 compounds. It does not fill in the aggregate "DrugSim vs.
general-purpose AI" table's "Not evaluated" cells, which still require the
full protocol run against the complete held-out set.

## Claude — full 459-compound CYP3A4 evaluation (fills the aggregate table)

Unlike the hERG entries above, this one **does** fill in the aggregate
"DrugSim vs. general-purpose AI" table's Claude column for CYP3A4, because
it covers the complete real held-out test set, not a subset. Real data:
`aiComparison.claude` on the CYP3A4 entry in `frontend/src/lib/benchmarks.ts`.
Full per-compound reasoning, verdicts, and probabilities:
`models/admet/cyp3a4_inhibition/claude_full_test_set_evaluation.json`.

**Real held-out test set, verified.** All 459 compounds are `split_group ==
9` from `datasets/processed/cyp3a4_inhibition_features.npz`, joined to SMILES
via `datasets/processed/cyp3a4_inhibition_dataset.csv`. The label
distribution (306 inhibitor / 153 non-inhibitor) matches DrugSim's own
reported confusion matrix exactly (tp+fn = 275+31 = 306, tn+fp = 62+91 = 153)
— confirmation this is the genuine test set, not a stand-in.

**Batched, not fully isolated per compound — a real, disclosed methodology
difference from the hERG subset above.** Token cost made 459 individual
isolated subagent dispatches impractical, so compounds were split into 23
batches of ~20, each batch handled by one subagent that read its batch from
a file and wrote structured JSON results back to disk (avoiding any manual
SMILES retyping, which is where a real transcription error was caught and
fixed earlier in this same session). This means compounds *within* one batch
were seen by the same subagent and could condition on each other; only the
23 batches are independent of each other, a weaker property than the hERG
subset's fully-isolated one-subagent-per-compound design. Disclosed in the
`methodologyNote` field and in the page's tooltip, not presented as
equivalent.

**Correctness of the 459 results was verified programmatically before
scoring**: exactly 459 results collected (no drops, no duplicates), every id
matches a real test-set compound, every prediction is a valid label, every
probability is an integer in [0, 100]. The prediction/probability
distribution spans the full 0-100 range across all ten deciles (not
collapsed to one answer) — checked specifically because an earlier hERG
attempt did collapse this way under a different (terser) prompt format; this
run's prompt required brief reasoning per compound from the start.

**CYP3A4 uses a different pharmacophore than hERG in the prompt, correctly.**
hERG's basic-amine-flanked-by-aromatics rule does not apply to CYP3A4;
subagents were instead directed to weigh heme-iron-coordinating nitrogens
(the classic azole-antifungal mechanism), a large flexible lipophilic active
site, and overall lipophilic/aromatic bulk — the actual, different,
well-established CYP3A4 inhibition risk factors.

**The result is real and substantially weaker than DrugSim's own model**:
ROC-AUC 0.5602 (barely above the 0.5 chance level), balanced accuracy 53.6%,
F1 72.2% — versus DrugSim's real 79.9% / 65.2% / 81.8% on the same 459
compounds. This is shown directly in the aggregate table, not softened, with
the methodology caveats above disclosed in the same place rather than buried.

## Claude — full 800-compound hERG evaluation (fills the aggregate table)

Same treatment as CYP3A4 above, run afterward for hERG's own full held-out
set. Real data: `aiComparison.claude` on the hERG entry in
`frontend/src/lib/benchmarks.ts`. Full per-compound reasoning, verdicts, and
probabilities: `models/admet/herg_inhibition/claude_full_test_set_evaluation.json`.

**A genuine session-level failure happened first and is disclosed, not
hidden.** The first dispatch of 4 batches failed outright with an account
session-usage-limit error, not a data or methodology problem — nothing was
written, confirmed by checking for output files before retrying. A single
probe batch was sent first on retry to confirm capacity had actually
returned (rather than re-dispatching all 16 and risking a second mass
failure); once it succeeded, the remaining batches were sent.

**Larger batches than the CYP3A4 run, deliberately, to use fewer tokens for
a bigger job.** CYP3A4 (459 compounds) used batches of 20 (23 dispatches);
hERG (800 compounds, ~1.7x more) used batches of 50 (16 dispatches) —
fewer dispatches despite more compounds, since the fixed per-dispatch
overhead (system prompt, tool definitions) is what batching actually saves,
not the per-compound reasoning cost, which is roughly constant regardless of
batch size. Same independence caveat as CYP3A4: compounds within one batch
could condition on each other; only the 16 batches are independent of one
another.

**Verified before scoring**: exactly 800 results, no duplicates, no missing,
every id real, every prediction/probability well-formed, and the
probability distribution spans the full 0-100 range across every decile.

**Result: ROC-AUC 0.6539, balanced accuracy 61.5%, F1 59.4%** — all lower
than DrugSim's own 78.8% / 65.0% / 79.2% on the identical 800 compounds.
Recall is the specific weak point: 49.3% — Claude missed nearly half of the
true blockers at this scale, a real and disclosed finding, not smoothed into
the aggregate numbers.

## SwissADME, ADMETlab 2.0, and pkCSM — established ADMET tool comparison

Requested separately from the AI comparison above: how DrugSim compares to
purpose-built ADMET prediction web tools, not general-purpose LLMs. Real
data: `establishedToolComparison` on both benchmark entries in
`frontend/src/lib/benchmarks.ts`.

**SwissADME (swissadme.ch) was investigated and excluded, not silently
skipped.** Its Terms of Use state verbatim: "not to use any form of web
crawler or other data retrieval tool or service to access SwissADME in any
automated manner, including for the purpose of automatically collecting
[...]". Automating either held-out set through it would be a direct
violation of that clause. No data was collected from SwissADME for this
comparison.

**ADMETlab 2.0 (admetmesh.scbdd.com) was run against the complete real
held-out test set for both endpoints — 800 hERG compounds, 459 CYP3A4
compounds (`split_group 9`), the identical compounds used for DrugSim's own
evaluation and Claude's full-set runs.** Its "ADMET Screening" batch mode
supports up to 500 SMILES per submission via a plain textarea, so this was
submitted as a direct HTTP POST to its own form endpoint
(`/service/screening/cal`) rather than through slower browser automation —
reproducing exactly what the web form itself sends, not a scraping
workaround. One real methodological discovery along the way: the endpoint
silently truncates to the first line unless SMILES are joined with `\r\n`
(standard HTML `<textarea>` line-ending convention) rather than a bare `\n`
— confirmed by a controlled 3-line test before trusting any real submission.
hERG was split into 2 batches of 400 (both succeeded). CYP3A4's first
attempt (all 459 at once) was disconnected by the server after a long
processing time with no response; retried successfully as 2 sub-batches of
229 and 230 with a 3-retry backoff wrapper. Results were fetched directly
from the CSV URLs the tool itself returns (`/static/files/filter/result/tmp/*.csv`).

**Verified before scoring**: exact row counts matched the input counts on
both endpoints (800 and 459), zero invalid molecules reported by the tool
itself. A small number of rows (83/800 for hERG, 47/459 for CYP3A4) had a
different-looking output SMILES string than the input — checked with RDKit
and confirmed every one was the same molecule (identical molecular formula
once charge/isotope annotations are stripped), just RDKit's own tautomer or
stereo-descriptor normalization on the way back out, not a positional
misalignment.

Each molecule is scored independently by ADMETlab's underlying multi-task
graph-attention model. Unlike Claude's batched subagent dispatch, batching
here carries no cross-compound conditioning risk: this is deterministic
per-molecule ML inference, not an LLM context window where earlier
compounds in a batch could influence later ones.

**Results**: hERG ROC-AUC 72.8%, balanced accuracy 60.0%, F1 77.8% (n=800) —
recall 93.3% but specificity only 26.7%, meaning it predicts "blocker" for
most compounds. CYP3A4 ROC-AUC 62.7%, balanced accuracy 55.6%, F1 75.6%
(n=459) — the same pattern, recall 82.4% but specificity only 28.8%. Both
shown as real findings, not smoothed toward DrugSim's own higher numbers
(hERG 78.8%/65.0%/79.2%, CYP3A4 80.0%/65.2%/81.8%).

**pkCSM (biosig.lab.uq.edu.au/pkcsm) is an informal n=5-per-endpoint
spot-check only, explicitly not presented as a validated comparison.** Its
real batch mode needs a SMILES file upload (capped at 100 molecules) that
isn't automatable with the browser tools available here — there is no way
to programmatically attach a file to a native OS file picker through this
session's tooling. Its only scriptable input is a single-molecule text
field (`<input type="text" name="smiles_str">`), confirmed via DOM
inspection, not assumed. Looping dozens or hundreds of individual automated
submissions against a free academic server to reach the full 800/459 would
be the same kind of behavior SwissADME's own terms explicitly prohibit, even
though pkCSM has no equivalent written clause — so rather than do that, only
5 compounds per endpoint (a class-balanced sample: 3/2 split matching each
endpoint's real held-out class ratio) were submitted one at a time in
"ADMET" full-panel mode, reading both the relevant Toxicity (hERG) and
Metabolism (CYP3A4) rows from each result page.

hERG has two independent pkCSM submodels, hERG I and hERG II inhibitor —
never collapsed into a single number, since they disagreed completely on
this n=5: hERG I inhibitor predicted "No" for every single compound (a
constant predictor, balanced accuracy exactly 50% and F1 0.0% by
construction), hERG II inhibitor predicted "Yes" for every single compound
(also balanced accuracy exactly 50%, but F1 75.0% since it happened to catch
all 3 true blockers in this tiny sample). CYP3A4 inhibitor scored balanced
accuracy 16.7%, F1 33.3% on its own n=5 — worse than a coin flip, a real and
disclosed result, not smoothed over. ROC-AUC is not reported for any pkCSM
result: it returns only a categorical Yes/No verdict per property, never a
probability, so there is no score to compute a ranking metric from — the
same structural limitation as GPT's original bare Yes/No protocol, not a gap
that will be filled in later.

Raw per-compound results: `models/admet/herg_inhibition/admetlab2_full_test_set_evaluation.json`,
`models/admet/cyp3a4_inhibition/admetlab2_full_test_set_evaluation.json`,
`models/admet/herg_inhibition/pkcsm_spot_check_evaluation.json`,
`models/admet/cyp3a4_inhibition/pkcsm_spot_check_evaluation.json`.
