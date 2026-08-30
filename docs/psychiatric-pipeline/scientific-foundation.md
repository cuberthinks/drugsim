# Scientific foundation: psychiatric compound screening

Audits the scientific assumptions in the "Unified Psychiatric Compound
Screening Pipeline" brief, per its own §1 requirement to verify claims
**before** writing any code. Every claim below is classified
**SUPPORTED**, **PARTIALLY SUPPORTED**, **SIMPLIFIED**, or **NOT
SUPPORTED**, with the reasoning that led to that classification. Where
the original brief's framing was imprecise or risked an overclaim, the
correction is stated plainly rather than implemented as written.

This document is pharmacology background, not a validated model output
— nothing here has been confirmed against DrugSim's own predictions,
because no DrugSim model for these endpoints exists yet (see
`data-sources.md`).

## DRD2 relevance to antipsychotic pharmacology

**SUPPORTED.** D2 dopamine receptor antagonism (or partial agonism, for
newer agents like aripiprazole) is the central, decades-established
mechanism connecting antipsychotic drugs to their antipsychotic effect
— the "dopamine hypothesis of schizophrenia." Clinical PET
receptor-occupancy studies have repeatedly shown that antipsychotic
efficacy correlates with striatal D2 occupancy in a defined window
(roughly 65–80%), and that occupancy above that window predicts
extrapyramidal side effects. This is one of the best-characterized
target-effect relationships in psychiatric pharmacology, which is why
DRD2 binding affinity is a scientifically reasonable therapeutic-target
endpoint to model.

## HRH1 antagonism and antipsychotic weight gain

**SUPPORTED as a real, replicated correlation; NOT SUPPORTED as a sole
or primary explanation.** Antipsychotics with high H1 affinity (e.g.
olanzapine, clozapine, quetiapine) are consistently associated with
greater weight gain and sedation than low-H1-affinity agents (e.g.
aripiprazole, ziprasidone) — this pattern is well replicated across
receptor-binding-profile studies. However, the literature on
antipsychotic-induced weight gain identifies **5-HT2C receptor
antagonism** as at least as strong a correlate, and metabolic effects
(insulin resistance, leptin dysregulation) involve additional
mechanisms beyond either single receptor. Treating HRH1 affinity as
*the* explanation for weight-gain liability — or treating low HRH1
affinity as evidence a compound won't cause weight gain — would be an
overclaim the data doesn't support. The brief's own instruction ("do
not claim that selectivity automatically prevents weight gain," §6) is
correct and will be enforced in the actual feature, not just this doc.

## Interpretation of DRD2 vs. HRH1 selectivity

**PARTIALLY SUPPORTED, and only with the correction the brief itself
demands.** The naive formula the brief explicitly flags —
`SI = H1 Affinity / D2 Affinity` — is scientifically wrong as stated,
because it never specifies whether "affinity" means a potency value
(where **smaller is stronger**, e.g. Ki/IC50 in nM) or an inverted
value like pKi (where **larger is stronger**). Computing a naive ratio
of raw Ki/IC50 values without first converting to a consistent,
direction-correct scale (e.g. pKi = -log10(Ki in M), where higher
always means stronger binding) produces a number whose direction of
"more selective" flips depending on which convention was assumed. A
scientifically defensible selectivity measure must state, explicitly,
which direction "more selective for the target" points on the chosen
scale — full methodology in `selectivity-methodology.md` once that
phase is reached.

## CYP2D6: inhibition vs. substrate metabolism vs. pharmacogenomic phenotype vs. DDI

**SUPPORTED that these are four distinct concepts, and conflating any
two of them is a real error the brief correctly warns against.**

- **CYP2D6 inhibition**: a compound blocking the enzyme's activity —
  what a Ki/IC50-based computational model can actually predict from
  structure.
- **CYP2D6 substrate metabolism**: whether a compound is *metabolized
  by* CYP2D6 — a related but separate question (a compound can inhibit
  CYP2D6 without being its substrate, and vice versa).
- **CYP2D6 pharmacogenomic phenotype**: a *patient's* genotype-derived
  classification (poor/intermediate/normal/ultrarapid metabolizer,
  CPIC/FDA-recognized) — this describes a person, not a molecule, and
  is categorically outside what any structure-based computational model
  can predict.
- **CYP2D6-mediated drug-drug interaction**: an emergent clinical risk
  arising from combining an inhibitor with a substrate in a specific
  patient — several steps removed from a single compound's predicted
  inhibition value.

A model predicting inhibition only answers the first bullet.
Labeling that result "genetically safe" or "safe for poor
metabolizers" would be **NOT SUPPORTED** — those claims require
genotype data this system never has access to. The brief's own labeling
instruction (§7) is scientifically correct and will be followed
literally.

## BBB permeability and CNS exposure

**SUPPORTED that BBB penetration is generally necessary for direct CNS
target engagement; SIMPLIFIED/PARTIALLY SUPPORTED as a claim of
sufficiency.** A compound that cannot cross the blood-brain barrier
cannot directly engage a CNS target like DRD2 or HRH1 at meaningful
concentrations via passive routes — this part is well established.
However, "BBB-permeable" does not imply "reaches an adequate
therapeutic brain concentration": actual brain exposure also depends on
plasma protein binding, active efflux (P-glycoprotein and other
transporters can pump a BBB-permeable compound back out), dosing, and
metabolic clearance. A BBB+ classification is a necessary-condition
screen, not a exposure guarantee — the brief's own instruction ("do not
claim BBB+ means therapeutic brain exposure," §8) is correct.

## BBB penetration and lipophilicity

**SIMPLIFIED.** Higher lipophilicity (LogP) has a historical, real
correlation with passive membrane permeability generally, including the
BBB, and appears in classic CNS drug-likeness heuristics. But modern
CNS multi-parameter optimization scoring (e.g. Pfizer's CNS MPO) treats
LogP as only one of several comparably-weighted inputs — topological
polar surface area (TPSA) and hydrogen-bond donor count are often
stronger discriminators for CNS penetration than LogP alone, and active
transport (both efflux and influx) can dominate over passive
lipophilicity-driven diffusion for many real drugs. "More lipophilic =
better BBB penetration" as a blanket rule is an oversimplification that
a real BBB model (trained on real permeability labels, not a
LogP-only heuristic) should not need to lean on, and this feature's own
documentation should not repeat it as if it were a reliable rule.

## hERG inhibition and cardiac safety

**SUPPORTED.** hERG (KCNH2/Kv11.1) potassium channel blockade is a
well-established mechanism of drug-induced QT-interval prolongation,
which can precipitate the polymorphic ventricular arrhythmia Torsades
de Pointes. This is the same, already-validated mechanism DrugSim's
existing hERG model screens for (see `docs/tds/06-ml-architecture.md`
and the model's own registry entry) — nothing new is being asserted
here.

## Limitations of hERG as a proxy for clinical arrhythmia risk

**SUPPORTED as a real, already-partially-documented limitation, not a
new finding.** hERG affinity alone does not fully predict clinical
Torsades risk: many hERG-active compounds never cause clinical
arrhythmia in practice, because real risk also depends on effects on
other cardiac ion channels (not just hERG/IKr), active metabolites,
plasma concentration achieved at clinical dose, and patient-specific
risk factors (electrolyte status, congenital long-QT susceptibility,
concomitant drugs). This is consistent with DrugSim's own existing
disclosures — the hERG model's reliability reporting already documents
that calibration degrades under real distribution shift (see
`docs/model-retraining/README.md`'s discussion of the same model) and
that its own applicability-domain checks exist precisely because a
confident-looking prediction is not automatically a trustworthy one.
This screening pipeline inherits that same limitation for its hERG
component and must not claim more certainty than the existing model
itself claims.

## Summary table

| Claim | Classification |
|---|---|
| DRD2 antagonism → antipsychotic efficacy | SUPPORTED |
| HRH1 antagonism → weight gain (as *a* contributor) | SUPPORTED |
| HRH1 antagonism → weight gain (as *the* explanation) | NOT SUPPORTED |
| Naive `SI = H1/D2` without direction correction | NOT SUPPORTED |
| Direction-corrected, log-space selectivity measure | SUPPORTED (methodology TBD) |
| CYP2D6 inhibition ≠ substrate ≠ phenotype ≠ DDI | SUPPORTED (as distinct concepts) |
| Inhibition-only model implies genetic safety | NOT SUPPORTED |
| BBB+ → CNS target engagement is possible | SUPPORTED |
| BBB+ → guaranteed therapeutic brain exposure | NOT SUPPORTED |
| Higher LogP → better BBB penetration (blanket rule) | SIMPLIFIED |
| hERG inhibition → QT-prolongation mechanism | SUPPORTED |
| hERG inhibition → precise clinical arrhythmia risk | PARTIALLY SUPPORTED |

No claim above was implemented as originally phrased where it was found
inaccurate — corrections are carried forward into
`selectivity-methodology.md`, `data-sources.md`, and (in later phases)
every user-facing explanation this feature produces.
