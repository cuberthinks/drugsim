# DrugSim

**DrugSim v1.0** is a computational ADMET research and prioritisation platform. Given a molecular structure, it returns validated machine-learning predictions for a small, growing set of independently evaluated endpoints — each one shown together with its uncertainty, applicability domain, and model provenance, never as a bare number.

This page is the top-level orientation for anyone landing in this repository for the first time. If you only read one document, read [`release/DRUGSIM_V1_README.md`](release/DRUGSIM_V1_README.md) — it assumes no prior context.

## What's actually in v1.0

Two validated endpoints, each independently built, audited, and promoted on its own evidence:

| Endpoint | Category | Status |
|---|---|---|
| hERG (KCNH2/Kv11.1) inhibition | Toxicity | VALIDATED FOR INTERNAL RESEARCH |
| CYP3A4 inhibition | Metabolism | VALIDATED FOR INTERNAL RESEARCH |

Full detail: [`phase10/final-scientific-audit.md`](phase10/final-scientific-audit.md).

## Documentation map

| Directory | What's in it |
|---|---|
| [`release/`](release/) | The v1.0 release notes and a plain-language project README — start here |
| [`scientific/`](scientific/) | Curated scientific status: endpoints, validation, limitations |
| [`methodology/`](methodology/) | How a prediction is actually made, pipeline stage by stage |
| [`api/`](api/) | The prediction API's contract |
| [`deployment/`](deployment/) | How to run and operate a deployment |
| [`privacy/`](privacy/) | What happens to a submitted structure |
| [`terms/`](terms/) | Terms of use |
| `phase1/` – `phase10/` | The full, phase-by-phase engineering and scientific record this product was built from — the authoritative source every summary page above links back to |
| `tds/` | The original Technical Design Specification |
| `adr/` | Architecture decision records |
| `legal/` | Third-party dataset attribution |

## A note on `docs/index.md`

`docs/index.md` (this directory's mkdocs home page) is the **original Phase 1 planning document**. It describes a broader early ambition — bioavailability, half-life, DILI, carcinogenicity endpoints, drug-likeness scoring, target hypotheses — than what was actually built. None of those four endpoints exist in v1.0. It is kept unmodified as the historical record (per this project's own "nothing deleted silently" principle) with a status note added at the top pointing here instead. **This file, not `index.md`, is authoritative for what v1.0 actually is.**
