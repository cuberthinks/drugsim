# DrugSim Benchmarks

What's on `/benchmarks` (the "Benchmark Explorer" page), where every number
on it comes from, and what has and has not actually been evaluated.

## Available benchmarks

Two, matching the two live, validated models. No other endpoint (DILI, Ames,
solubility, HIA, bioavailability, Caco-2, BBB, half-life) has a live DrugSim
model, so none is benchmarked here — adding a benchmark for an endpoint that
doesn't exist would be exactly the kind of fabrication this page exists to
avoid. See `docs/benchmarks/dataset-registry.md` for why each of those
candidates was or wasn't built, where that's documented elsewhere in the repo.

| Benchmark ID | Endpoint | Dataset | n (test) | Split |
|---|---|---|---|---|
| `herg_inhibition_v1_scaffold_split` | hERG (KCNH2/Kv11.1) inhibition | ChEMBL CHEMBL240, v1 | 800 | Scaffold (ADR-009) |
| `cyp3a4_inhibition_v1_scaffold_split` | CYP3A4 inhibition | ChEMBL CHEMBL340, v1 | 459 | Scaffold (ADR-009) |

## Where the numbers come from

Every statistic on the Benchmark page is copied verbatim from a JSON report
already checked into the repository — never recomputed for the page, never
estimated. The frontend reads them from one structured module,
`frontend/src/lib/benchmarks.ts`, which cites its source file per benchmark.
See `docs/benchmarks/dataset-registry.md` for the full field-by-field
citation trail back to the original report files under `models/admet/`.

## Metrics used

Both endpoints are binary classification tasks, so classification metrics
apply: ROC-AUC, average precision (PR-AUC), balanced accuracy, F1,
precision/recall, and — where the source report computed them — Matthews
correlation coefficient and specificity. Regression metrics (MAE, RMSE, R²,
Pearson/Spearman) do not apply to either current endpoint and are not shown,
since DrugSim has no regression endpoint live today.

## Evaluation methodology

Both models use the project's established scaffold-split methodology
(ADR-009): the training/test division is by molecular scaffold, not random
assignment, so structurally related compounds cannot appear in both sets. A
random-split figure is also shown for each endpoint, labelled explicitly as
an ablation illustrating the leakage a random split would introduce — never
presented as the "real" number. Neither endpoint has a canonical external
benchmark split (e.g. from Therapeutics Data Commons) for its exact
ChEMBL-sourced compound set; where a genuinely independent dataset was
available (a different lab, different assay technology), it's reported as
"external validation," clearly distinguished from the primary scaffold-split
test result.

## AI comparison status

**GPT: not evaluated**, on either benchmark. DrugSim has no API access
configured for it. See `docs/benchmarks/ai-comparison-protocol.md` for the
full protocol that would need to be followed and recorded before any GPT
comparison could be shown here.

**Claude: evaluated, but not via that documented protocol.** On 2026-08-25,
Claude was run against the complete real held-out test set for both
endpoints — all 800 hERG compounds and all 459 CYP3A4 compounds
(`split_group 9`) — via SMILES-only subagent dispatches, each producing a
genuine per-compound verdict plus a self-reported 0-100 confidence value.
This is a real, disclosed deviation from the documented protocol (3
independent runs per compound in fresh sessions; this was a single run,
batched for tractability) and fills the "DrugSim vs. general-purpose AI"
table on the Benchmark page for both endpoints. Its ROC-AUC is not
like-for-like with DrugSim's: the number comes from self-reported confidence,
not a calibrated `predict_proba` output. A smaller 30-compound informal
subset and a 4-compound spot-check are also shown on the page, both clearly
labelled as lower-rigor supplements to these two full-set results, not
substitutes for the documented protocol. Full per-compound results and the
complete methodology (including a caught-and-discarded systematic bug and a
session-limit failure/recovery) are in
`docs/benchmarks/dataset-registry.md`.

## Established ADMET tool comparison status

Separate from the AI comparison above: purpose-built ADMET prediction tools,
arguably a fairer comparison than an LLM since both sides are narrow models
trained for exactly this kind of task.

**SwissADME: excluded, not evaluated.** Its Terms of Use explicitly state
users must "not use any form of web crawler or other data retrieval tool or
service to access SwissADME in any automated manner." Running the held-out
sets through it would violate that clause directly, so it was not attempted —
this is a deliberate exclusion on legal/ToS grounds, not a technical gap.

**ADMETlab 2.0: evaluated against the complete real held-out test set.** On
2026-08-26, both the full 800-compound hERG set and the full 459-compound
CYP3A4 set were submitted directly to ADMETlab 2.0's own batch-screening
endpoint (`admetmesh.scbdd.com/service/screening/cal`) via a direct HTTP POST
matching its published form (discovered the hard way: the endpoint silently
drops all but the first line unless SMILES are joined with `\r\n`, not `\n`).
hERG was split into 2 submissions of 400; CYP3A4's first single-request
attempt was disconnected server-side after a long processing time and was
retried successfully as 2 sub-batches of 229 and 230. Every molecule is
scored independently by ADMETlab's underlying graph-attention model, so
unlike Claude's batched subagent dispatch, batch size carries no
cross-compound conditioning risk. This fills the "DrugSim vs. established
ADMET tools" table for both endpoints.

**pkCSM: an informal n=5 spot-check only, not a validated comparison.**
pkCSM's true batch mode requires a file upload that isn't automatable with
the tools available here; its scriptable path (a plain single-molecule text
field) only ever accepts one compound per submission. Rather than loop
dozens of automated one-at-a-time requests against a free academic server —
the same kind of behavior SwissADME's terms explicitly ban, even though
pkCSM has no equivalent written clause — only 5 compounds per endpoint were
submitted, by hand-driven single-molecule requests. hERG has two independent
pkCSM submodels (hERG I and hERG II inhibitor); on this n=5 they disagreed
completely — hERG I predicted "No" for every compound, hERG II predicted
"Yes" for every compound — both are shown separately, never collapsed into
one number. ROC-AUC is not shown for any pkCSM result: it returns only a
categorical Yes/No verdict, never a probability. Full per-compound results
and methodology for all three tools are in
`docs/benchmarks/dataset-registry.md`.

## Individual molecule explorer

Four public, well-known compounds (Aspirin, Terfenadine, Dofetilide,
Paracetamol) — the same four used elsewhere in the app as the guided
examples, and already verified against the live hERG endpoint before being
written. Ground truth for each is well-documented public pharmacology (cited
per compound on the page: FDA withdrawal history for Terfenadine, approved
mechanism of action for Dofetilide, absence of any hERG signal in the
literature for the other two) — never a confidential or customer structure,
and never DrugSim's own private training or test data.

## Reproducing a reported number

Each benchmark entry in `frontend/src/lib/benchmarks.ts` records its
`sourceFile`. Open that file under `models/admet/` and the number on the page
matches it exactly. To regenerate a report from scratch, re-run the
corresponding evaluation script in that endpoint's `phase3`/`phase4`
directory (hERG) or top-level directory (CYP3A4) — see each script's own
docstring for its exact inputs and the frozen artifacts (dataset checksum,
model checksum) it evaluates against.

## Known gaps

- CYP3A4 has no per-Tanimoto-tier applicability-domain breakdown the way
  hERG does — its reliability report computed AD-verdict-based accuracy
  instead (a different but genuinely reported metric), shown on the page as
  such, not converted into a shape it wasn't measured in.
- Neither endpoint has ROC/PR curve *point data* stored anywhere in the
  repository, only the summary AUC scalar — so the Benchmark page reports the
  AUC number and a real confusion matrix, but does not draw a curve, since
  drawing one would require inventing intermediate points that were never
  actually computed.
