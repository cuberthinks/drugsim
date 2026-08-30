# Dynamic compound identification

How DrugSim identifies a submitted molecule (name, synonyms, database
identifiers, a verified description) without hardcoding per-compound
answers and without ever sending a user's structure to a third party.

## The problem this replaces

Before this feature, only the four example compounds on `/predict`
(`frontend/src/lib/exampleCompounds.ts`) had any name/description at all
— and that was a static button label, never connected to the prediction
response. A user typing in caffeine's SMILES got a prediction with no
indication of what compound it even was.

## Why this is an offline snapshot, not a live lookup

DrugSim's `/predict` service has an existing, tested, audited guarantee:
**no third-party service ever receives a submitted structure**
(`docs/privacy/confidentiality-audit.md` Sec 8 — proven there by the
deployed service's dependency list not even including an HTTP client). A
live per-request call to PubChem would break that guarantee.

Instead, identity data is fetched **once, offline**, by
`scripts/build_compound_identity_snapshot.py`, for compounds already in
DrugSim's own approved reference data — never for a live user submission.
The live `/predict` path only ever does a local, in-memory dictionary
lookup keyed by InChIKey (`src/drugsim_identity/snapshot.py`). No network
call, no new runtime dependency, in the deployed service.

A compound outside the snapshot resolves as `identity_status:
"unidentified"` — the expected, normal outcome for a genuinely novel
molecule, not an error. Prediction proceeds exactly as if the compound
had been identified.

## Trusted source: PubChem

PubChem is already registered in `datasets/registry.yaml` (`source_id:
pubchem`, `role: identity_spine`) with a resolved licence
(`spdx: US-PD`, `tier: green`, `commercial_ok: true`) — adopted there
specifically as "the chemical identity resolution spine (InChIKey <->
CID)," just never implemented until now. The build script calls
`drugsim_curation.provenance.resolve_license` against this registry entry
before any network call, and fails closed (refuses to run) if it ever
stops resolving.

For each seed compound, the script standardises it via
`drugsim_chem.process_structure` (reused, not reimplemented) to get its
canonical InChIKey, then calls PubChem's public PUG-REST/PUG-View APIs:

1. `/compound/inchikey/{key}/cids/JSON` — resolve to a PubChem CID.
2. `/compound/cid/{cid}/property/Title/JSON` — the preferred display name.
3. `/compound/cid/{cid}/synonyms/JSON` — up to 5 synonyms, excluding the
   preferred name itself.
4. `/pug_view/data/compound/{cid}/JSON?heading=Record+Description` —
   PubChem's own sourced "Record Description" section, when one exists.

**Nothing here is generated or inferred from the SMILES.** Every name,
synonym, and description is PubChem's own real response, captured
verbatim with its own citation where PubChem provides one (e.g.
`"PubChem (National Toxicology Program...)"`).

## Which compounds are in the snapshot

`scripts/build_compound_identity_snapshot.py` enriches:

- `datasets/golden/compounds.csv`'s `category == "drug"` rows (aspirin,
  caffeine, ibuprofen, paracetamol) — excluding `imatinib_like`, whose own
  name says it is a similar-shaped test structure, not literally imatinib.
- The two DrugSim example compounds not already covered by the golden set
  (terfenadine, dofetilide) — listed by SMILES in
  `src/drugsim_identity/data/seed_compounds.yaml`.
- **Every named compound already in DrugSim's own raw ChEMBL training
  data** (`datasets/raw/chembl_{herg,cyp3a4}_ic50_raw.csv`'s
  `molecule_pref_name` column) — ChEMBL only sets this field for
  compounds it considers notable (approved drugs, well-known reference
  compounds), so this is a large, already-ingested, already-licensed
  source, not a new external dependency. As of the last build: 910
  compounds resolved to a real PubChem entry (34 had no PubChem match,
  correctly skipped rather than guessed at — mostly internal
  pharma-company codenames PubChem doesn't carry under that identity).
- **Common, well-known compounds not otherwise covered** — e.g. ethanol
  (`datasets/golden/compounds.csv` tags it `category=simple`, not
  `category=drug`, so the automatic golden-fixture inclusion misses it)
  — added explicitly to `seed_compounds.yaml` when a real user-facing
  gap like this is found.

This is a **scoping list only** — it says which compounds are worth a
lookup, never what the answer is. Extending coverage means adding a
SMILES to the seed list (or another already-approved reference source)
and re-running the build script; it never means hand-writing a name or
description.

## Metadata fields

Returned on every `POST /predict` response as `compound_identity`:

| Field | Populated when |
|---|---|
| `identity_status` | Always — `"identified"` or `"unidentified"` |
| `compound_name` | Identified only |
| `synonyms` | Identified, and PubChem had at least one |
| `identifiers` | Identified — `{"pubchem_cid": "..."}` |
| `description` | Identified — a real PubChem description, or the literal string `"Verified description unavailable."` if PubChem has no Record Description on file (never fabricated) |
| `description_source` | Identified and PubChem cited a source for the description |
| `source` | Identified — `"PubChem"` |
| `retrieved_at` | Identified — when the offline snapshot build resolved this compound |

`molecular_weight` was also added to the existing `molecule` block
(`MoleculeSchema`) — it's a computed chemistry fact (RDKit `Descriptors.
MolWt`, already available internally) like `molecular_formula`, always
present regardless of identification status, not an identity fact.

## How to run the build script

```bash
python scripts/build_compound_identity_snapshot.py
```

Requires `httpx` and `pyyaml` (already project dependencies, already used
by the equivalent ChEMBL-fetching scripts under `models/admet/*`) —
neither is installed in the live predict-api's own dependency set
(`requirements-predict-api.txt`), and this script is never imported by
anything under `src/drugsim_predict`.

Re-running the script only fetches compounds not already in the snapshot
(it's additive) unless the snapshot file is deleted first. A per-compound
PubChem failure (network error, or no CID found) is logged and skipped —
it never aborts the batch or discards already-resolved entries.

## Provenance

Every identified compound's record carries `pubchem_cid`, `retrieved_at`
(when the build script resolved it), and `license_spdx` (`"US-PD"`) —
answering "where did this come from" without a separate lookup. This
mirrors the same provenance discipline `drugsim_curation` already applies
to training data (Phase 11).

## Privacy

No change to DrugSim's existing privacy posture. The structures PubChem
sees are DrugSim's own already-public reference compounds (aspirin,
caffeine, the example compounds, etc.), fetched offline by an operator —
never a structure a user submitted to `/predict`. See
`docs/privacy/index.md` and `docs/privacy/confidentiality-audit.md` for
the full, unchanged accounting of what does and does not leave this
service.

## Known limitations

- **Coverage is limited to the seeded compounds** — a genuinely novel
  molecule (the common case for a research tool like DrugSim) is
  correctly reported as unidentified, not a gap to "fix" by widening the
  seed list arbitrarily.
- **`compound_name` is exactly PubChem's own `Title` property**,
  including occasional technical qualifiers (e.g. ibuprofen resolves to
  `"Ibuprofen, (+-)-"`, PubChem's racemic-mixture-aware title) — not
  smoothed over, since doing so would mean overriding a verified source's
  own answer.
- **Descriptions are PubChem's first available "Record Description"
  entry**, which is sometimes a hazard/safety-committee statement rather
  than a general "what is this compound" summary (e.g. aspirin's current
  entry is about developmental-toxicity classification) — real and
  sourced, just not curated for tone.
- **`frontend/src/lib/export.ts`'s CSV/JSON export does not yet include
  the new identity fields** — out of this feature's scope, not broken by
  it.
