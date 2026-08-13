# What is DrugSim?

DrugSim is a piece of software that looks at the chemical structure of a molecule and predicts a couple of specific things about how it might behave in the body — before anyone has to synthesise it and test it in a lab. This document explains what it does, how it works, and what it doesn't do, assuming you've never seen this project before.

## What it actually predicts

As of this release (v1.0), DrugSim predicts exactly two things:

1. **Does this molecule block the hERG cardiac channel?** This matters because blocking that channel can cause dangerous heart-rhythm problems, so it's one of the very first things drug researchers screen for.
2. **Does this molecule inhibit the CYP3A4 liver enzyme?** This matters because that enzyme breaks down roughly half of all prescription drugs — if a new molecule blocks it, it can cause dangerous drug interactions with anything else a patient is taking.

That's it. Two predictions. DrugSim does **not** predict whether a molecule will work as a medicine, whether it's toxic in some other way, how the body absorbs or eliminates it, or anything about its effect on a human being as a whole. If you've heard the term "ADMET" (Absorption, Distribution, Metabolism, Excretion, Toxicity) — DrugSim currently covers one small piece of Toxicity (hERG) and one small piece of Metabolism (CYP3A4), not the full picture.

## How it works, in plain terms

1. You type in a molecule's structure using a text format called SMILES (a standard way chemists write structures as text — e.g. `CCO` is ethanol).
2. DrugSim cleans up and standardises that structure so the same molecule always gets treated the same way, no matter how it was typed.
3. It computes a set of numerical features that describe the molecule's shape and chemistry.
4. It runs those features through a machine-learning model — one model per endpoint (hERG, CYP3A4) — that was trained on thousands of real, publicly available lab measurements.
5. Alongside the prediction, it tells you two more things that most tools like this skip:
   - **How confident is this?** (uncertainty) — not just "yes" or "no," but a calibrated statement of how sure the model actually is.
   - **Has this model actually seen chemistry like this before?** (applicability domain) — a model is only as good as the data it learned from; DrugSim tells you honestly when you've asked it about something quite different from anything in its training data.
6. You get all of that back together, along with exactly which model version produced it, so the result can always be traced back to its source.

## Why this matters (and why "uncertainty" isn't a hedge)

A lot of tools like this will just spit out "safe" or "unsafe." DrugSim deliberately never does that, for a simple reason: a machine-learning model trained on a few thousand compounds cannot honestly claim certainty about a molecule that looks nothing like anything it was trained on. Reporting a confident-sounding number anyway isn't more useful — it's just less honest. So every DrugSim prediction comes with its uncertainty and applicability-domain assessment attached, always, by construction — the software will not let you see a prediction without them.

## What DrugSim is not

- It is **not a replacement for laboratory testing**. Every prediction is a computational estimate based on historical data, not a real measurement of the actual molecule you typed in.
- It is **not a clinical or diagnostic tool**. Nothing it produces is medical advice or a clinical finding.
- It is **not a whole-body simulation**. It does not know what a drug will actually do inside a human being — it makes two narrow, specific, independently-validated predictions and nothing more.
- It has **not been approved by any regulator** for any purpose.

## Who validated it, and how

Every prediction comes from a model that went through the same process before it was allowed to run: real public data was gathered and cleaned, the model was trained and tested on data it had never seen during training, its performance was measured with standard statistics, its "did it actually learn anything real" behaviour was checked by scrambling the labels and confirming the model got much worse (a real, deliberate sanity check), and — for CYP3A4 — its predictions were checked one more time against a completely separate, independent dataset it had never touched before. Only after all of that does a model get marked "VALIDATED FOR INTERNAL RESEARCH" and become available through the app. If you want the full, detailed scientific writeup, it's in [`../scientific/index.md`](../scientific/index.md) and the full phase-by-phase record in the rest of this `docs/` folder.

## Trying it

Enter a molecule as a SMILES string, click Validate to see the structure DrugSim understood, then click Predict to run either endpoint (or view the full "Compound Profile" to see both at once). Every result page shows the prediction, its uncertainty, its applicability domain, which exact model version produced it, and a link to the full list of limitations.

## Where to go next

- Full release notes: [`DRUGSIM_V1_RELEASE_NOTES.md`](DRUGSIM_V1_RELEASE_NOTES.md)
- Full scientific status: [`../scientific/index.md`](../scientific/index.md)
- The API, if you want to call DrugSim programmatically: [`../api/index.md`](../api/index.md)
- Running your own deployment: [`../deployment/index.md`](../deployment/index.md)
