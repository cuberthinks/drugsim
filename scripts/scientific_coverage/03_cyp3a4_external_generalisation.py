"""Scientific Coverage 3: CYP3A4 external generalisation + AD stratification.

Closes the endpoint gap left by `01_external_generalisation.py`, which covered
hERG only. Same question, same metric family, same discipline: report the
precision/specificity/PR-AUC/MCC set per applicability-domain tier on genuinely
external compounds, which the existing CYP3A4 external-validation report does
not break down by tier.

Reuses the label rule, standardisation and overlap exclusion of
`models/admet/cyp3a4_inhibition/external_validation.py` verbatim in method, so
the aggregate numbers here are comparable to that report rather than a
parallel calculation.

Endpoint-specific caveat carried forward from that script, not glossed: TDC's
`CYP3A4_Veith` label is a single-concentration qHTS activity call, whereas this
model's training label is an aggregated dose-response IC50 threshold. The two
label definitions are related but not identical, so external numbers here are
"consistent-with" evidence, not a like-for-like reproduction of internal test
performance.

Read-only. No model trained, retrained or modified.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from drugsim_chem import compute_descriptors, compute_morgan_fingerprint, process_structure  # noqa: E402
from drugsim_chem.parsing import parse_molecule  # noqa: E402
from drugsim_core.errors import StructureError  # noqa: E402

# Reuse the exact metric implementation from the hERG analysis so the two
# reports cannot silently diverge in how a metric is defined.
import importlib.util  # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_sc01", Path(__file__).resolve().parent / "01_external_generalisation.py"
)
_sc01 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_sc01)
_classification_metrics = _sc01._classification_metrics
_max_tanimoto = _sc01._max_tanimoto
TIERS = _sc01.TIERS
SWEEP = _sc01.SWEEP
DEFAULT_THRESHOLD = _sc01.DEFAULT_THRESHOLD

MODEL_PATH = ROOT / "models" / "admet" / "cyp3a4_inhibition" / "artifact" / "model.joblib"
FEATURES_NPZ = ROOT / "datasets" / "processed" / "cyp3a4_inhibition_features.npz"
EXTERNAL_TSV = ROOT / "datasets" / "raw" / "tdc_cyp3a4_veith_raw.tsv"
OUT_DIR = Path(__file__).resolve().parent
OUTPUT_JSON = OUT_DIR / "03_cyp3a4_external_generalisation_report.json"
POOL_CACHE = OUT_DIR / ".cyp3a4_pool_cache.json"

TEST_GROUP = 9
TRAIN_GROUPS = list(range(7))
DESCRIPTOR_FIELDS = [
    "mw_g_mol", "exact_mass_g_mol", "logp_crippen", "molar_refractivity", "tpsa_a2",
    "rotatable_bonds", "aromatic_rings", "ring_count", "heavy_atom_count", "formal_charge",
    "hbd_lipinski", "hba_lipinski", "hbd_strict", "hba_strict", "heteroatom_count",
    "fraction_csp3", "num_stereocentres", "largest_ring_size",
]


def _build_pool() -> list[dict]:
    model = joblib.load(MODEL_PATH)
    data = np.load(FEATURES_NPZ, allow_pickle=True)
    train_mask = np.isin(data["split_groups"], TRAIN_GROUPS)
    train_fps = data["fingerprints"][train_mask]
    train_inchikeys = set(data["inchikey_full"][train_mask].tolist())

    pool: list[dict] = []

    mask = data["split_groups"] == TEST_GROUP
    x = np.concatenate([data["descriptors"][mask], data["fingerprints"][mask]], axis=1)
    y = data["labels"][mask]
    prob = model.predict_proba(x)[:, 1]
    tan = _max_tanimoto(data["fingerprints"][mask], train_fps)
    for i in range(int(mask.sum())):
        pool.append({
            "source": "internal_test",
            "label": int(y[i]),
            "prob": float(prob[i]),
            "max_tanimoto": float(tan[i]),
        })

    external_df = pd.read_csv(EXTERNAL_TSV, sep="\t")
    seen: set[str] = set()
    for i, row in enumerate(external_df.itertuples()):
        try:
            processed = process_structure(row.Drug)
        except StructureError:
            continue
        if processed.is_mixture:
            continue
        ik = processed.identity.inchikey_full
        if ik in seen or ik in train_inchikeys:
            continue  # de-duplicated, and exact training overlap excluded
        seen.add(ik)
        mol = parse_molecule(processed.standardized_smiles)
        d = compute_descriptors(mol)
        descriptors = [getattr(d, f) or 0.0 for f in DESCRIPTOR_FIELDS]
        fp = compute_morgan_fingerprint(mol)
        xq = np.concatenate([descriptors, fp]).reshape(1, -1)
        pool.append({
            "source": "external_tdc",
            "inchikey": ik,
            "label": int(row.Y),
            "prob": float(model.predict_proba(xq)[0, 1]),
            "max_tanimoto": float(_max_tanimoto(fp.reshape(1, -1), train_fps)[0]),
        })
        if (i + 1) % 2000 == 0:
            print(f"  external processed {i + 1}/{len(external_df)}", file=sys.stderr)
    return pool


def main() -> int:
    if POOL_CACHE.exists():
        print("Using cached pool.", file=sys.stderr)
        pool = json.loads(POOL_CACHE.read_text())
    else:
        pool = _build_pool()
        POOL_CACHE.write_text(json.dumps(pool))

    ext = [p for p in pool if p["source"] == "external_tdc"]
    internal = [p for p in pool if p["source"] == "internal_test"]

    def arrs(rows):
        return (
            np.array([r["label"] for r in rows]),
            np.array([r["prob"] for r in rows]),
            np.array([r["max_tanimoto"] for r in rows]),
        )

    ext_y, ext_p, ext_t = arrs(ext)
    int_y, int_p, _ = arrs(internal)

    by_tier = {}
    for name, lo, hi in TIERS:
        sel = (ext_t >= lo) & (ext_t < hi)
        if sel.sum() == 0:
            by_tier[name] = {"n": 0}
            continue
        m = _classification_metrics(ext_y[sel], ext_p[sel], DEFAULT_THRESHOLD)
        m["tanimoto_range"] = [lo, hi]
        m["mean_tanimoto"] = round(float(ext_t[sel].mean()), 4)
        by_tier[name] = m

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "endpoint": "cyp3a4_inhibition",
        "scope": "Read-only. No model trained, retrained or modified.",
        "method_provenance": {
            "model_artifact": str(MODEL_PATH.relative_to(ROOT)),
            "external_source": "TDC CYP3A4_Veith (PubChem AID 1851 qHTS)",
            "external_file": str(EXTERNAL_TSV.relative_to(ROOT)),
            "exact_training_overlap": "excluded by full InChIKey",
            "tier_boundaries": "identical to the hERG analysis and Phase 4.5",
            "decision_threshold": DEFAULT_THRESHOLD,
            "label_definition_caveat": (
                "TDC's Y is a single-concentration qHTS activity call; this model's "
                "training label is an aggregated dose-response IC50 threshold. Related "
                "but not identical definitions -- consistency evidence, not a "
                "like-for-like reproduction."
            ),
        },
        "pool_composition": {"internal_test": len(internal), "external_tdc": len(ext)},
        "reference_internal_test": _classification_metrics(int_y, int_p, DEFAULT_THRESHOLD),
        "external_overall": _classification_metrics(ext_y, ext_p, DEFAULT_THRESHOLD),
        "external_by_applicability_domain_tier": by_tier,
        "threshold_sensitivity_external": {
            f"{t:.2f}": _classification_metrics(ext_y, ext_p, t) for t in SWEEP
        },
    }

    OUTPUT_JSON.write_text(json.dumps(report, indent=2))
    print(f"Wrote {OUTPUT_JSON.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
