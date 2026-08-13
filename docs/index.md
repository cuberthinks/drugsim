# DrugSim Engineering Documentation

> **v1.0 status note (Phase 10):** this page is the original Phase 1 planning
> document and is kept as-is for the historical record (project principle:
> "nothing deleted silently") — it describes the platform's early ambition,
> not what actually shipped. The table below (bioavailability, half-life,
> DILI, carcinogenicity) was a Phase 1 candidate survey; **none of those
> four endpoints were built**. What actually reached v1.0 is exactly two
> independently validated endpoints — hERG inhibition and CYP3A4
> inhibition — with no drug-likeness assessment or target-hypothesis
> capability. For what is actually true of the released system, start at
> [`docs/README.md`](README.md) or
> [`docs/release/DRUGSIM_V1_RELEASE_NOTES.md`](release/DRUGSIM_V1_RELEASE_NOTES.md),
> not this page.

DrugSim is an **AI-assisted preclinical prioritisation platform**. A researcher
uploads a molecular structure and receives predicted ADMET properties, drug-likeness
assessment, target hypotheses and toxicity flags — each with quantified confidence
and an explicit statement of whether the molecule falls inside the model's
applicability domain.

## What DrugSim is not

Phase 1 verified the public training corpus behind the headline endpoints:

| Endpoint | Public training compounds |
|---|---|
| Human oral bioavailability | 640 |
| Human half-life | 667 |
| DILI (hepatotoxicity) | 475 |
| Carcinogenicity | 278 |

Models trained on a few hundred compounds have narrow applicability domains and
degrade sharply outside them — which is exactly where newly designed molecules live.
DrugSim is therefore **not a replacement for laboratory or animal testing**. The
defensible claim is better ordering of an experimental queue, with calibrated
uncertainty.

## Where to start

| You are | Read |
|---|---|
| New to the project | [TDS §1 & §12](tds/01-overview-and-principles.md), then [§2 architecture](tds/02-system-architecture.md), then the [Phase 1 dataset survey](phase1/step1-dataset-survey.md) |
| Implementing a feature | [§4 data contracts](tds/04-data-contracts.md) → [§5 API](tds/05-api-specification.md) → [§8 standards](tds/08-engineering-standards.md) |
| Reviewing a PR | [§8 standards](tds/08-engineering-standards.md) and the P1–P12 principles |
| Working on chemistry | [Phase 1 Step 4](phase1/step4-compound-schema.md) and [Step 8](phase1/step8-data-cleaning-pipeline.md) |

**Do not start with the schema.** It will not make sense without the dataset
survey's findings on licensing and dataset sizes.

## The twelve principles

Reproducibility over speed · every prediction traceable · never overwrite raw data ·
provenance per record · models reproducible · confidence and applicability always ·
scientific validation every release · nothing deleted silently · decisions documented
· boring technology preferred · customer structures are confidential IP · honest
failure over confident error.

See [TDS §12](tds/01-overview-and-principles.md) for the enforcement mechanism behind
each.
