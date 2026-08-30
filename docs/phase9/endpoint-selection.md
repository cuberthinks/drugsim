# Phase 9 — Endpoint Selection

## Selected endpoint: CYP3A4 inhibition (ChEMBL target CHEMBL340)

## Method

Candidates were drawn from the two sources this project's own registry
(`datasets/registry.yaml`) already documents as suitable for ADMET
training — ChEMBL (`role: anchor_bioactivity`) and Therapeutics Data
Commons (`role: admet_training`) — plus the specific alternative targets
Phase 3's own `fetch_chembl_data.py` docstring names as having been
considered and passed over in favour of hERG. Record counts below for
ChEMBL targets were verified live against the ChEMBL REST API on
2026-08-09 (the same API and query pattern Phase 3 used for hERG); TDC
dataset sizes are cited from `datasets/registry.yaml`'s own recorded scale
data (compiled 2026-08-05) and from TDC's public ADME/Tox benchmark pages,
not independently re-downloaded for every candidate — full download was
only performed for the selected endpoint (see
`docs/phase9/phase9-admet-expansion-report.md`).

## Candidates considered

| Candidate | Category | Source | N (verified) | Format | Units issue? | Notes |
|---|---|---|---|---|---|---|
| **CYP3A4 inhibition** | Metabolism | ChEMBL CHEMBL340 | **13,887 IC50 records** (live-verified 2026-08-09; 6,755 after `confidence_score>=8` + `standard_relation='='`) | IC50, nM | No — ChEMBL's `standard_units` field is explicit and consistent, same as hERG | Named in Phase 3's own hERG docstring as the largest passed-over alternative. CYP3A4 metabolises an estimated ~50% of marketed small-molecule drugs; inhibition is a primary mechanism of clinically significant drug-drug interactions. |
| AMES mutagenicity | Toxicity | TDC (Xu et al. curation) | ~7,278 compounds (registry-cited) | Binary label | No (classification) | Large, clean, binary, well-established. Rejected for Phase 9 specifically because it is a Toxicity-category endpoint like the existing hERG model — CYP3A4 gives the platform genuine category breadth (Metabolism) that a second Toxicity endpoint would not. Strong candidate for Phase 10. |
| Blood-brain-barrier penetration (BBB) | Distribution | TDC (Martins et al.) | ~2,030 compounds | Binary label | No (classification) | Smaller than CYP3A4; deferred, not rejected — good Phase 10 candidate for Distribution-category breadth. |
| P-glycoprotein (Pgp/ABCB1) inhibition | Absorption/Distribution | ChEMBL CHEMBL4302 | 2,654 IC50 records (live-verified 2026-08-09; matches Phase 3's own docstring citation exactly) | IC50, nM | No | Real and usable, but 5x smaller than CYP3A4; deferred. |
| CYP2D6 inhibition | Metabolism | ChEMBL CHEMBL2035 | 1,394 IC50 records (live-verified) | IC50, nM | No | Clinically important (genetic polymorphism), but the smallest of the CYP isoforms checked — rejected for this phase on sample size. |
| CYP2C9 inhibition | Metabolism | ChEMBL CHEMBL3227 | 2,609 IC50 records (live-verified) | IC50, nM | No | Same reasoning as CYP2D6 — usable but smaller than CYP3A4; deferred. |
| Drug-induced liver injury (DILI) | Toxicity | TDC | 475 compounds (registry-cited) | Binary label | No (classification) | Too small on its own for a robust scaffold-split train/calibration/test protocol matching hERG's methodology (hERG's *training-split alone* was 6,792). Rejected for this phase; flagged as a candidate only if later combined with independent literature curation. |
| Human bioavailability | Absorption | TDC (Ma et al.) | 640 compounds | Regression, % | **Yes** — `datasets/registry.yaml` explicitly flags TDC units as undocumented/provisional for this endpoint | Rejected: fails both the sample-size and unit-consistency ranking criteria simultaneously — the registry's own units caveat singles this class of endpoint out as high-risk. |
| Aqueous solubility / Caco-2 permeability / VDss / half-life / clearance | Absorption/Distribution | TDC | Various (475–~5,000) | Regression | **Yes** — same registry caveat: "CRITICAL: TDC does not document units... for Caco-2, Lipophilicity, Solubility, VDss, Half Life, Clearance" | Rejected as a class for Phase 9: the project's own data registry already flags these as needing units to be "confirmed empirically at gate G4 before model training," which is exactly the kind of unresolved measurement-definition risk Sec 2 of this phase says must stop work if it cannot be defended. A future phase could resolve this with dedicated unit-verification work; not attempted here to keep this phase to one endpoint, properly validated. |

## Ranking against the nine stated criteria

1. **Dataset quality** — ChEMBL's `confidence_score`/`standard_relation`/`standard_units` fields give CYP3A4 the same structured quality filtering hERG used. TDC's regression endpoints fail this criterion outright per the registry's own documented units caveat.
2. **Endpoint clarity** — "IC50 against human CYP3A4" is exactly as unambiguous as "IC50 against human hERG/KCNH2" — same measurement type, same target-based definition.
3. **Sample size** — CYP3A4 (13,887 / 6,755 filtered) is the largest of every non-hERG candidate checked, by a wide margin over the next-largest ChEMBL alternative (Pgp, 2,654).
4. **Unit consistency** — No issue: ChEMBL potency data carries explicit, machine-readable units, unlike several TDC regression endpoints.
5. **Biological relevance** — CYP3A4-mediated drug-drug interaction is one of the most clinically consequential ADMET liabilities in drug development, comparable in real-world importance to hERG-mediated cardiotoxicity.
6. **Availability of independent validation data** — assessed in `docs/phase9/phase9-admet-expansion-report.md` Sec "External validation"; a candidate disjoint literature/TDC source was sought specifically for CYP3A4 before committing.
7. **Applicability-domain feasibility** — identical featurisation (Morgan fingerprint + physicochemical descriptors) to hERG, so the existing, already-validated AD methodology (Tanimoto + k-NN descriptor distance + scaffold-seen) applies without modification.
8. **Licensing suitability** — ChEMBL, CC BY-SA 3.0 (red tier per the registry) — the exact same licence terms already accepted and in production for the hERG model. No new licensing review is introduced.
9. **Expected scientific value to DrugSim** — Metabolism is one of the four ADMET categories the product's own UI mockup (Phase 9 Sec 17) names, and DrugSim currently covers none of it. CYP3A4 is the highest-value single addition toward genuine multi-category breadth, not just a second Toxicity model.

## Selected endpoint

**CYP3A4 inhibition, target CHEMBL340, IC50-based, binary classification**
(inhibitor / non-inhibitor), following the same aggregation, standardisation,
splitting, feature, model, applicability-domain, and uncertainty
methodology already validated for hERG. Full definition in
`docs/phase9/phase9-admet-expansion-report.md` Sec "Endpoint."

## Rejected / deferred endpoints

- **Rejected this phase, strong future candidates**: AMES mutagenicity,
  BBB penetration, Pgp inhibition, CYP2D6/CYP2C9 inhibition — all have
  real, usable data; none was chosen for Phase 9 specifically because
  CYP3A4 is larger (the ChEMBL targets) or because a second Toxicity
  endpoint adds less platform breadth than a first Metabolism endpoint
  (AMES).
- **Rejected as a class, pending unit verification**: every TDC continuous
  (regression) ADME endpoint (solubility, Caco-2, lipophilicity, VDss,
  half-life, clearance, bioavailability, LD50) — this project's own data
  registry already documents that TDC does not state units for these, and
  Sec 2 of this phase's own brief requires stopping if an endpoint
  definition cannot be defended. Units must be empirically confirmed
  (per the registry's own "gate G4" note) before any of these becomes a
  viable Phase 10+ candidate.
- **Rejected outright, this phase**: DILI (475 compounds — too small to
  reproduce hERG's train/calibration/test scaffold-split protocol
  credibly) and human bioavailability (small *and* units-ambiguous).

## Erratum (found 2026-08-30, during the psychiatric-pipeline audit)

The **CYP2D6 row above cites the wrong ChEMBL target**. `CHEMBL2035` is
not CYP2D6 — it is the **muscarinic acetylcholine receptor M5 (CHRM5)**,
confirmed live via `target_search`. The real CYP2D6 target is
**`CHEMBL289`** ("Cytochrome P450 2D6," SINGLE PROTEIN, Homo sapiens,
UniProt P10635), which carries **8,684 raw IC50 records, 3,349 after
`standard_units='nM'` + `pchembl_value` present** (live-verified
2026-08-30) — not 1,394. This means CYP2D6 was never actually the
smallest CYP isoform checked; the number rejected in this table belongs
to an unrelated GPCR, not to any CYP. The rejection verdict in the table
above is therefore **wrong as stated** and should not be relied on —
see `docs/psychiatric-pipeline/data-sources.md`'s CYP2D6 section for the
corrected assessment. The original table row is left unedited above
(rather than silently rewritten) so this document still accurately
records what Phase 9 actually did and believed at the time; treat the
CYP2D6 line in that table as superseded by this note.

## What was explicitly NOT done

No endpoint was selected before checking real data availability. No
candidate's dataset size was estimated or assumed — every ChEMBL count in
the table above was queried live against the ChEMBL REST API on
2026-08-09, the same day this document was written. Only one endpoint was
selected for development; none of the deferred/rejected candidates were
started in parallel.
