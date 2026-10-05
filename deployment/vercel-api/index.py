"""Vercel entrypoint for the DrugSim prediction API.

Vercel detects a module-level ``app`` (ASGI) in ``index.py``. The real
application lives in ``drugsim_predict.api``; ``build.sh`` copies ``src/`` and
the model artifacts next to this file, so putting ``./src`` on the path is all
that is needed to import it exactly as the Docker image does.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "src"))

from drugsim_predict.api import app  # noqa: E402,F401  (re-exported for Vercel)
