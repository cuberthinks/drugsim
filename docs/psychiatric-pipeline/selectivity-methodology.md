# DRD2/HRH1 selectivity methodology

Answers, precisely: *"How much more strongly is the molecule predicted
to interact with the therapeutic target (DRD2) relative to the
off-target (HRH1)?"* — nothing more than that. This document exists
because the original feature brief's own suggested formula (`SI = H1
Affinity / D2 Affinity`) is scientifically wrong as stated — see
`scientific-foundation.md`'s selectivity section for why — and a
correct replacement needs its formula, units, and direction stated
explicitly, not assumed.

## Why the naive ratio is wrong

Binding-affinity measurements come in two families that point in
*opposite* directions:

- **Potency values** (Ki, IC50, in nM or µM): **smaller = stronger**
  binding.
- **Inverted/log values** (pKi, pIC50 = -log10(value in molar)):
  **larger = stronger** binding.

`SI = H1/D2` computed on raw Ki values would mean "larger SI = weaker
D2 binding relative to H1" — the opposite of what "more selective for
the target" should mean. Computed on pKi values, the same-shaped
formula would mean the opposite of *that*. Without stating which
convention is in play, the formula is not just imprecise, it can
silently flip which molecules look "good."

## The actual formula

Both `models/psychiatric/drd2_activity` and `models/psychiatric/
hrh1_activity` predict **pki** on the identical scale:

```
pki = 9 - log10(Ki in nM)   =   -log10(Ki in molar)
```

Higher `pki` always means stronger binding, for both targets, because
both pipelines apply this exact same transform (see each endpoint's
`build_dataset.py`). That shared convention is what makes a direct
subtraction meaningful:

```
selectivity_index_log10 = pki_drd2 - pki_hrh1
```

- **Units**: log10 (dimensionless ratio of molar concentrations).
- **Direction**: positive means the compound is predicted to bind DRD2
  more strongly than HRH1 (more selective for the therapeutic target);
  negative means the reverse.
- **Fold form**, for a more intuitive reading:
  `fold_selectivity_for_drd2 = 10 ** selectivity_index_log10` — e.g. an
  index of `+2.0` means "predicted ~100x stronger binding at DRD2 than
  HRH1."

Implementation: `models/psychiatric/selectivity.py::compute_selectivity`.

## Uncertainty propagation

Each target's model already reports its own split-conformal interval
half-width (in pKi units) from its own `evaluation_report.json`. The
selectivity index's own uncertainty is the **sum** of the two
half-widths, not a variance-reduced combination (e.g. not
`sqrt(a^2 + b^2)`):

```
uncertainty_half_width_log10 = drd2_half_width + hrh1_half_width
```

This is a deliberately conservative choice. A variance-style combination
would require assuming the two models' errors are independent and
approximately Gaussian — an assumption this codebase has not verified
and should not silently make. Summing half-widths gives a valid
worst-case bound without that assumption, at the cost of a wider
(more honest, less flattering) reported interval.

## Handling incompatible measurements

If either target's underlying dataset had needed to mix Ki and IC50
without justification, this formula would not be valid — see
`data-sources.md`: both `drd2_activity` and `hrh1_activity` use **Ki
only**, precisely to avoid that problem. If a future revision ever adds
IC50 data for either target, it must not be pooled into the same `pki`
column without re-deriving whether IC50 and Ki are commensurate for
that assay context (they generally are not, without a competition-
binding correction).

## Applicability domain

If either target's own applicability-domain check reports the compound
as out-of-domain, the selectivity result's `domain_status` is
`"out_of_domain"` and carries an explicit caveat — the selectivity
value is still computed and shown (never hidden), but flagged as an
extrapolation on top of its already-reported uncertainty interval.

## What this does NOT claim

Directly enforcing `scientific-foundation.md`'s corrections:

- **Not a safety or efficacy claim.** A high DRD2-selectivity index does
  not mean a compound is effective or safe; a high HRH1-selectivity
  index does not mean a compound will cause weight gain (see the
  scientific-foundation doc's HRH1/weight-gain section — the
  correlation is real but not suffient on its own, and 5-HT2C is at
  least as strong a correlate).
- **Not a replacement for the individual predictions.** The selectivity
  index is a derived summary; the underlying DRD2 and HRH1 predictions,
  with their own uncertainty and applicability-domain status, remain
  the primary evidence and should always be shown alongside it, not
  replaced by it.

## Worked verification (real, not illustrative)

`models/psychiatric/demo_selectivity.py` runs both real trained models
on two real reference compounds with well-documented, opposite
pharmacology (SMILES verified against live ChEMBL, not typed from
memory):

| Compound | Real-world profile | Predicted DRD2 pKi | Predicted HRH1 pKi | selectivity_index_log10 | Domain |
|---|---|---|---|---|---|
| Haloperidol (CHEMBL54) | Classic, potent D2-antagonist antipsychotic | 8.02 | 6.85 | **+1.18** (≈15x DRD2-selective) | in_domain |
| Diphenhydramine (CHEMBL657) | Classic antihistamine, not an antipsychotic | 6.06 | 6.80 | **-0.73** (≈5.4x HRH1-selective) | out_of_domain |

Both directions match well-established real pharmacology exactly —
this is the correctness check for the formula and its sign convention,
not a claim that either number is precise (the reported uncertainty
half-width, ±2.31 log10 units here, is wide enough that only the broad
direction should be trusted, not the specific fold value).
