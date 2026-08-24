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

**Not evaluated**, for both GPT and Claude, on both benchmarks. DrugSim has
no API access configured for either service. See
`docs/benchmarks/ai-comparison-protocol.md` for the full protocol that would
need to be followed and recorded before any comparison could be shown here —
running an informal, undocumented comparison would be exactly the kind of
fabrication this page exists to avoid, so none was attempted.

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
