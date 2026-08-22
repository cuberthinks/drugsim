"""Confidentiality audit (2026-08-22), item 2: production prediction data
must never silently enter model training.

The 2026-08-22 audit found no code path anywhere in this repository that
reads ``var/predictions.sqlite3`` / :class:`~drugsim_predict.store.PredictionStore`
for any purpose other than serving it back through the API itself, backing
it up, or restoring it -- there is no training pipeline coupled to it at
all. That absence is exactly the kind of fact a manual audit can confirm
today and quietly stop being true tomorrow, when nobody re-runs the audit.
This test makes it a standing, automated guarantee: it scans every
Python source file in the repository for a reference to the prediction
store, and fails if one appears anywhere outside an explicit allowlist.
Extending model training to ever use submitted structures is a real,
legitimate thing DrugSim could someday choose to do -- but per the
project's own privacy commitments (see docs/privacy/), that requires an
explicit, separately documented consent mechanism, not a script that
happens to notice the file is there. Adding a new entry to the allowlist
below should never be the easy fix for a failing run of this test.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = [pytest.mark.unit, pytest.mark.security]

#: References to the live prediction store outside these paths mean
#: something new -- a training script, a notebook, an ETL job -- has
#: started reading production prediction data. That is the one change
#: this test exists to catch; it is not a bureaucratic hoop.
_ALLOWED_REFERENCES = frozenset(
    {
        "src/drugsim_predict/api.py",
        "src/drugsim_predict/store.py",
        "src/drugsim_predict/settings.py",
        "scripts/backup_predictions_db.py",
        "scripts/restore_predictions_db.py",
    }
)

#: Anything matching these substrings identifies a reference to the
#: production prediction store or its backing file. Deliberately broad
#: (matches the class name, the settings field, and the literal filename)
#: so a reference via any of the ways Python code could plausibly reach it
#: is caught, not just one specific import spelling.
_MARKERS = ("PredictionStore", "prediction_db_path", "predictions.sqlite3")

#: Directories never worth walking: environments, build output, and the
#: test suite itself. Excluding `tests/` is deliberate, not a loophole --
#: this rule is about production/ETL/training code coupling to the live
#: store, not about the tests that legitimately exercise store.py directly
#: (test_predict_store.py, test_backup_restore.py, this file's own
#: sibling test_prediction_ownership.py, etc).
_EXCLUDED_DIR_NAMES = frozenset(
    {".git", ".venv", "venv", "node_modules", ".tools", "__pycache__", ".pytest_cache", "dist", "build", "var", "tests"}
)


def _iter_repo_python_files(root: Path):
    for path in root.rglob("*.py"):
        if any(part in _EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        yield path


def test_only_the_allowlisted_files_reference_the_prediction_store(project_root: Path) -> None:
    self_path = Path(__file__).resolve()
    offenders: dict[str, list[str]] = {}

    for path in _iter_repo_python_files(project_root):
        if path.resolve() == self_path:
            continue  # this file's own docstring/allowlist necessarily names the markers.
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        hits = [marker for marker in _MARKERS if marker in text]
        if not hits:
            continue
        rel = path.relative_to(project_root).as_posix()
        if rel in _ALLOWED_REFERENCES:
            continue
        offenders[rel] = hits

    assert not offenders, (
        "A file outside the training-isolation allowlist references the production "
        "prediction store: " + repr(offenders) + ". If this is a legitimate new use, it "
        "must NOT be a training/retraining pipeline reading submitted structures without "
        "explicit, separately documented consent (see docs/privacy/). If it genuinely is "
        "not that, add it to _ALLOWED_REFERENCES in this file with a comment explaining why."
    )


def test_allowlisted_files_still_exist(project_root: Path) -> None:
    """Catches the inverse drift: an allowlist entry for a file that was
    renamed or deleted silently stops meaning anything."""
    missing = [rel for rel in _ALLOWED_REFERENCES if not (project_root / rel).exists()]
    assert not missing, f"Allowlisted paths no longer exist, update _ALLOWED_REFERENCES: {missing}"
