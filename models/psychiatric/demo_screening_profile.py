#!/usr/bin/env python3
"""Run the full multi-objective psychiatric screening profile on real reference compounds.

Extends the same two real, independently-verified reference compounds
`demo_selectivity.py` already validated (opposite, well-documented real
pharmacology), now through the FULL six-signal profile (DRD2, HRH1,
Selectivity, CYP2D6, BBB, hERG) rather than DRD2/HRH1/Selectivity alone.

Usage:
    python models/psychiatric/demo_screening_profile.py
"""

from __future__ import annotations

import dataclasses
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from screening_profile import screen_compound  # noqa: E402

COMPOUNDS = {
    "Haloperidol (CHEMBL54) -- classic potent D2 antagonist antipsychotic": "O=C(CCCN1CCC(O)(c2ccc(Cl)cc2)CC1)c1ccc(F)cc1",
    "Diphenhydramine (CHEMBL657) -- classic potent H1 antagonist, not an antipsychotic": "CN(C)CCOC(c1ccccc1)c1ccccc1",
}


def main() -> int:
    """Screen each reference compound and print the full structured profile."""
    for label, smiles in COMPOUNDS.items():
        profile = screen_compound(smiles)
        print(f"\n{'=' * 70}\n{label}\n{'=' * 70}")
        print(json.dumps(dataclasses.asdict(profile), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
