# DrugSim vs. General-Purpose AI — Comparison Protocol

**Status: not yet run.** This document specifies exactly how a GPT/Claude
comparison must be conducted before any result from it appears on the
Benchmark page. No comparison has been run — DrugSim has no API access
configured for either service, and this page's own standard (see
`docs/benchmarks/README.md`) is that a result is either produced this way,
or it does not appear at all. Nothing here is a result; it is the
precondition for one.

## Purpose

To transparently benchmark DrugSim against general-purpose AI on the exact
same molecules and experimental ground truth — not to argue DrugSim is
"smarter," and not to stack the comparison in DrugSim's favour. If a
general-purpose model performs as well or better on a given benchmark, that
result gets published exactly as clearly as the reverse.

## Test set

The evaluation set for a given run is exactly the benchmark's own held-out
scaffold-split test set (e.g. 800 hERG compounds, 459 CYP3A4 compounds — see
`docs/benchmarks/dataset-registry.md`), identified by the same
`benchmark_id` and `dataset_version` already recorded for DrugSim's own
result. Using a different, smaller, or hand-picked subset for the AI
comparison than DrugSim's own reported test set is not permitted under this
protocol — the comparison is only valid on identical inputs.

## Exact molecule input

Each compound is presented as its canonical SMILES string, standardised
through the same pipeline DrugSim itself uses
(`drugsim_chem.process_structure`) before being shown to any system —
identical structure representation across DrugSim, GPT, and Claude. No
compound name, brand name, or other identifying metadata is included in the
prompt (that could leak the answer through the model's training-data
recollection of the named drug, rather than testing structure-based
reasoning).

## Exact prompt (fixed, identical for every model and every molecule)

```
You are evaluating a molecule for a specific pharmacological property.

SMILES: {canonical_smiles}

Question: Does this molecule inhibit the {endpoint_name} at a potency
threshold of IC50 <= 10 uM, based on its chemical structure?

Answer with exactly one word: "Yes" or "No". Do not explain your reasoning.
Do not ask for more information. If you are uncertain, still provide your
best single-word answer.
```

`{endpoint_name}` is substituted with "hERG (KCNH2/Kv11.1) cardiac channel"
or "CYP3A4" as appropriate. The forced single-word answer format is
deliberate: it removes free-text parsing ambiguity from scoring, at the cost
of not capturing a model's expressed uncertainty — a real limitation of this
protocol, disclosed here rather than silently accepted.

## Model name, version, and settings

Recorded exactly, per run, before any results are reported:

- Exact model identifier (e.g. `gpt-4o-2026-05-13`, `claude-sonnet-5-20260315`) — never an unversioned name like "GPT" or "Claude," which refers to a moving target.
- Temperature: 0 (deterministic as far as the API allows), explicitly set, not left at a provider default that could change.
- Max output tokens: capped low (the answer is one word) to prevent an unscored free-text continuation from being silently truncated mid-answer.
- System prompt (if any): none beyond what's shown above — no "you are an expert chemist" framing that could bias the model toward guessing confidently.

## Repeated runs

Each molecule is submitted **3 times independently** (fresh API call, no
conversation history carried over) per model, even at temperature 0, since
provider-side non-determinism is real and undisclosed at the API level for
both GPT and Claude as of this writing. The majority vote across the 3 runs
is the model's answer for that molecule; a 1-1-1 non-majority result (not
possible with 3 runs and 2 options, included here for completeness if a
future version of this protocol allows a third response category such as
"Uncertain") would be recorded as a non-answer, not silently broken to
either side.

## Information provided to the model

Only the fixed prompt above. No dataset context, no few-shot examples, no
description of what "hERG" or "CYP3A4" is beyond the plain-language mention
already in the prompt itself, and no access to DrugSim's own prediction for
that molecule. Symmetric across GPT and Claude — neither receives anything
the other doesn't.

## External web access

**Disabled for both models**, if the provider's API offers a browsing/tool
mode. This is a structure-reasoning benchmark, not a "look up this drug's
Wikipedia page" benchmark — a model that recognises a well-known drug by
name and recalls its known hERG liability from training data or a web
search is not doing the same task DrugSim is doing (working from structure
alone). If a provider's default API mode cannot fully disable retrieval or
tool use, that is recorded as a caveat on the result, not silently ignored.

## Scoring method

Each model's per-molecule "Yes"/"No" answer is mapped to
blocker/non-blocker (or inhibitor/non-inhibitor) and scored against the
same experimental ground-truth label DrugSim's own evaluation used — the
aggregated ChEMBL IC50 <= 10 µM threshold for the primary scaffold-split
benchmark, or the relevant external dataset's own label for an
external-validation comparison (with that dataset's own label-definition
caveat carried over unchanged — see `docs/benchmarks/dataset-registry.md`).
Metrics computed are exactly the classification metrics already reported
for DrugSim on the same benchmark (ROC-AUC is not computable from a binary
Yes/No answer with no probability attached — accuracy, balanced accuracy,
F1, precision, recall, and a confusion matrix are the metrics a forced
binary answer actually supports, and only those are reported for GPT/Claude
even though DrugSim's own richer output supports more).

## Experimental ground truth

Identical to DrugSim's own benchmark: the same dataset, same version, same
label definition, same held-out compounds — see
`docs/benchmarks/dataset-registry.md` for the exact source file per
benchmark. Never a different or looser ground truth for the AI side of the
comparison.

## Date of evaluation

Recorded per run as an ISO date, alongside the exact model identifiers used
that day — both because model behaviour can change between provider updates
and because a "GPT" or "Claude" result without a date and version is not
reproducible or falsifiable.

## Reproducibility record required per run

A completed run must record, at minimum:

- `benchmark_id` and `dataset_version` evaluated against
- Exact model identifiers (GPT and Claude) and their release dates
- Temperature and other sampling settings used
- Number of repeated calls per molecule and the aggregation rule
- Whether external web/tool access was available, and to what extent it could be disabled
- The exact prompt template used (verbatim, not paraphrased)
- Evaluation date
- Full per-molecule results (not just the aggregate metric), so a reviewer can audit individual disagreements

## What this protocol deliberately does not attempt

- It does not ask either model to explain its reasoning, since that
  reopens free-text scoring ambiguity this protocol is designed to avoid.
- It does not attempt a regression-style (numeric IC50) comparison, since
  neither general-purpose model can be expected to output a calibrated
  potency value from structure alone in a way that would be a fair
  comparison to a trained QSAR model's continuous output.
- It does not run once and generalise — a single molecule, or a single
  run per molecule, is not sufficient evidence for a page whose entire
  purpose is not overclaiming from thin evidence.
