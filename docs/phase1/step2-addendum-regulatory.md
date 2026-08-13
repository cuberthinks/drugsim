# DrugSim — Step 2 Addendum
## Regulatory-Grade Architecture Deltas

**Trigger:** Decision of 2026-08-05 — *regulatory path intended* (FDA submissions, ICH M7).
**Amends:** `step2-data-architecture.md`, `step2-data-dictionary.md`
**Status:** Draft for approval

---

## 1. Why this addendum exists

Step 2 was written against the assumption that regulatory use was undecided, and Step 1 §7 flagged the question precisely because the answer is expensive to retrofit. The answer is now **yes**, and it changes the architecture in ways that are cheap today and very costly later.

Second decision: **commercial model undecided** → build the strict commercial-safe design. Practically this means the ShareAlike containment in ADR-007 stays fully enforced, and a Green/Amber-only fallback training path is a standing requirement rather than a contingency.

---

## 2. Regulatory requirements now in scope

| Framework | Requirement | Architectural consequence |
|---|---|---|
| **21 CFR Part 11 §11.10(e)** | Secure, computer-generated, time-stamped audit trails; changes must not obscure prior values; retained as long as the record | Append-only `audit_log` capturing old **and** new values. **No hard deletes anywhere** |
| **21 CFR Part 11 §11.10(d)** | System access limited to authorised individuals | `system_user` + role model; every mutation attributed to a user |
| **21 CFR Part 11 §11.50** | Signature manifestations: printed name, date/time, **meaning** of signature | `electronic_signature` with explicit `signature_meaning` |
| **21 CFR Part 11 §11.70** | Signature-to-record linking, non-repudiable | Content hash of the signed record stored with the signature |
| **ICH M7(R2)** | **Two complementary (Q)SAR methodologies — one expert rule-based, one statistical-based**; absence of alerts from both permits a no-concern conclusion; expert review resolves ambiguous/out-of-domain results | Dedicated `ich_m7_assessment` entity enforcing *one of each* methodology, plus a mandatory expert-review path |
| **OECD (Q)SAR validation** | Five principles: defined endpoint · unambiguous algorithm · defined applicability domain · goodness-of-fit/robustness/predictivity · mechanistic interpretation where possible | `model_validation_record` structured on the five principles |
| **QMRF** | Harmonised model reporting template | `model_qmrf` document store linked to each validated model version |

Verified 2026-08-05 against FDA M7(R2) guidance and OECD (Q)SAR Assessment Framework materials.

---

## 3. Architecture deltas

### 3.1 New cross-cutting principle
**P8 — Nothing is ever deleted or silently altered.** Every mutation is attributed, timestamped, reversible in the record (not necessarily in effect), and carries a reason. This supersedes any convenience-driven update-in-place in Steps 2 and 3.

### 3.2 Zone changes
- **Z1 Landing** — retention becomes a *compliance* requirement, not just a scientific one. Object-lock with a defined retention period; deletion requires a signed, recorded decision.
- **Z4 Serving** — gains the governance domain (§4 of Step 3): users, audit log, signatures, validation records.
- **Z5 Inference** — predictions destined for regulatory use require a completed `model_validation_record` and, for mutagenicity, a completed `ich_m7_assessment`. Enforced at constraint level.

### 3.3 New gate: G7 — Regulatory Release
Runs after G6 for any release flagged `regulatory_use`:
- Every model in the release has a current `model_validation_record` covering all five OECD principles
- Every model has a QMRF document
- Audit-trail continuity verified — no gaps, no orphaned mutations
- All required electronic signatures present and hash-valid
- Applicability-domain definition explicit and versioned per model

### 3.4 ICH M7 as a first-class workflow
Mutagenicity is the one endpoint where the regulatory framework prescribes the *method*, not just the evidence quality. DrugSim must therefore run and record **two independent predictions per compound** — one from an expert rule-based system (structural alerts), one from a statistical model — and treat disagreement, out-of-domain, or indeterminate results as triggering mandatory expert review rather than as a number to average.

**This is the clearest instance of a Step 1 theme:** the honest answer is often "the model cannot conclude", and the schema must be able to represent that state as a legitimate, signed outcome.

---

## 4. Data dictionary deltas

New controlled vocabularies:

**`signature_meaning`** — `authorship` · `review` · `approval` · `responsibility` · `verification`

**`audit_operation`** — `insert` · `update` · `soft_delete` · `restore`

**`model_methodology_type`** — `expert_rule_based` · `statistical_based` · `hybrid` · `read_across`
*Required for ICH M7: an assessment must reference one `expert_rule_based` and one `statistical_based` model.*

**`ich_m7_class`** — `class_1` … `class_5`
- `class_1` — known mutagenic carcinogen
- `class_2` — known mutagen, unknown carcinogenic potential
- `class_3` — alerting structure unrelated to the API; no mutagenicity data
- `class_4` — alerting structure shared with API or related tested non-mutagenic compounds
- `class_5` — no structural alert, or alert with sufficient data showing no mutagenicity

**`oecd_principle`** — `defined_endpoint` · `unambiguous_algorithm` · `applicability_domain` · `performance_measures` · `mechanistic_interpretation`

**`expert_review_outcome`** — `confirms_prediction` · `overrides_prediction` · `inconclusive_further_testing_required`

New cross-cutting columns on all governance-relevant tables: `created_by`, `created_at`, `modified_by`, `modified_at`, `is_deleted`, `deleted_reason`, `record_hash`.

---

## 5. Cost of this decision — stated plainly

The regulatory path is the right call if submissions are genuinely intended, but it is not free:

- **Schema size** grows by roughly a third (governance domain + validation domain)
- **Every write path** becomes heavier: audit capture, attribution, no in-place updates
- **Process burden** is ongoing and larger than the engineering burden — validation documentation, signature workflows, change control. Software cannot supply this; people must
- **Model updates become governed events.** A retrained model is a change-controlled artefact requiring re-validation, not a deployment
- **Part 11 compliance is a property of the whole system**, including hosting, access control and SOPs. The schema below is necessary but nowhere near sufficient — do not let a compliant-looking database create false confidence about the organisation's compliance posture

My recommendation stands behind the decision, with one caveat worth stating: build the schema now, but treat formal validation as a Phase 5+ activity. Designing for it early costs little; *executing* it before there are models worth validating would consume the runway.

---

*End addendum. Incorporated into Step 3.*
