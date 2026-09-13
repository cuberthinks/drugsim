# Scientific Coverage & Generalisation

Work responding to external reviewer feedback from readers with
biomedical/drug-discovery experience. **No model was trained, retrained,
re-thresholded or promoted in this workstream.**

## Documents

| Document | Contents |
|---|---|
| [`current-state-audit.md`](current-state-audit.md) | Architecture as found, strengths that must not regress, weaknesses W1–W4, affected modules, what must remain unchanged |
| [`compound-identity-coverage.md`](compound-identity-coverage.md) | Measured reference-identity coverage; why the obvious fix isn't the fix |
| [`external-generalisation.md`](external-generalisation.md) | External precision/specificity/PR-AUC by applicability-domain tier; threshold sensitivity; error analysis |
| [`data-gap-analysis.md`](data-gap-analysis.md) | Which data would actually help, which would not, and why |
| [`final-report.md`](final-report.md) | Answers the brief's ten completion questions, including what was **not** done |

## Reproducing the analyses

```bash
.venv-verify/bin/python scripts/scientific_coverage/01_external_generalisation.py
.venv-verify/bin/python scripts/scientific_coverage/02_identity_coverage.py
```

Both are read-only and write JSON beside themselves. `01` caches its compound
pool (`.pool_cache.json`); delete it to force a full rebuild.

## The three findings worth knowing

**1. The external "generalisation failure" is a base-rate effect, not model
degradation.** On 3,956 independent compounds the hERG model scores ROC-AUC
0.865 (*higher* than its 0.784 internal), specificity 0.682 (*nearly double*
its 0.373 internal), and essentially unchanged MCC. Precision falls to 0.218
only because prevalence falls from 61% to 9.4%. Do not "fix" this by
retraining.

**2. The applicability domain works better than previously concluded.** Phase
4.5 called it *"partially supported, not cleanly monotonic"* using ROC-AUC —
prevalence-insensitive, on tiers ranging 44%→1% positive. With PR-AUC the
gradient is perfectly monotonic (0.825 → 0.663 → 0.404 → 0.131) and MCC
collapses to 0.085 out-of-domain. Keep the mechanism; update Phase 4.5's
wording.

**3. Identity coverage is a reference-data problem, not a matching problem.**
~96% of independent public compounds are unnameable because the reference set
is seeded from compounds named in DrugSim's own two assay files. Adding an
InChIKey-skeleton tier gains +0.16–0.32pp. It shipped anyway — bounded,
ambiguity-refusing, and explicitly labelled a different kind of match — but it
is not the fix.

## Two rules this workstream enforces

**Reference data ≠ training data.** Naming more compounds makes DrugSim more
useful to *read*. It does not make any model more accurate. Never let an
identity-coverage improvement be reported as a performance improvement.

**Identity never gates prediction.** `VALID + UNIDENTIFIED + PREDICTABLE` is a
supported, normal state. "Unidentified" is an expected outcome for a novel
molecule, not an error — and is rendered that way.
