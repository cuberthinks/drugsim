"""Pins that the full chemistry pipeline is silent on repeated, per-call use.

Two real console-noise sources were found and fixed while writing Sprint 2.5:

1. RDKit's rdMolStandardize (Cleanup/Uncharger/CanonicalTautomer) prints
   "Initializing X / Running X" progress chatter that bypasses the rdApp.info
   category-based suppression — fixed with rdBase.BlockLogs() scoped around
   standardize()'s implementation.
2. npscorer.readNPModel() prints "reading NP model ... / model in" via a
   raw file-descriptor write that bypasses contextlib.redirect_stdout
   entirely — a ONE-TIME, import-time cost, left as a documented, low-priority
   cosmetic limitation rather than chasing OS-level fd redirection for it.

This test asserts (1) is fixed on REPEATED calls (the case that actually
matters for a production service processing many molecules) and does not
assert anything about the one-time import-time message from (2), which this
test file's own collection will have already triggered before the first test
runs.
"""

from __future__ import annotations

import contextlib
import io

import pytest

from drugsim_chem.pipeline import process_structure

pytestmark = pytest.mark.unit

# Trigger the one-time npscorer import-time print here, at module load, so it
# cannot appear inside any test's captured output below.
process_structure("CCO")


class TestNoRepeatedConsoleNoise:
    """The noise that matters: does it recur on every call, or was it truly
    one-time? standardize()'s rdMolStandardize chatter recurred on EVERY
    call before the BlockLogs fix — this is what must never regress."""

    @pytest.mark.parametrize(
        "smiles",
        [
            "CC(=O)Oc1ccccc1C(=O)O",  # plain molecule
            "CCN(CC)CC.Cl",  # salt-stripping path
            "CCO.CCN",  # mixture path
            "[Na+].[Cl-]",  # whole-salt-retained path
            "CC(=O)[O-]",  # charge neutralisation path
        ],
    )
    def test_processing_is_silent(self, smiles: str) -> None:
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            process_structure(smiles)
        assert buffer.getvalue() == ""

    def test_repeated_calls_stay_silent(self) -> None:
        """The specific regression this suite exists to catch: noise that
        only appears once (e.g. lazy-loaded resource) vs noise that recurs on
        every call (the actual production problem)."""
        buffer = io.StringIO()
        with contextlib.redirect_stdout(buffer), contextlib.redirect_stderr(buffer):
            for _ in range(5):
                process_structure("CC(=O)Oc1ccccc1C(=O)O")
        assert buffer.getvalue() == ""
