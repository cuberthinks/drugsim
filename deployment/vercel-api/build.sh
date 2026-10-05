#!/usr/bin/env bash
# Assemble a self-contained bundle for the Vercel function: application source,
# the two registry files + inference manifests, and the model artifacts
# (fetched from the same GitHub Release the Docker image uses). Mirrors
# deployment/docker/Dockerfile.predict-api so both hosts serve identical models.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT="$(cd "$HERE/../.." && pwd)"
export MODEL_RELEASE_URL_BASE="${MODEL_RELEASE_URL_BASE:-https://github.com/cuberthinks/drugsim/releases/download/models-v1}"

rm -rf "$HERE/src" "$HERE/models" "$HERE/scripts"
mkdir -p "$HERE/models/registry" "$HERE/scripts"

cp -R "$ROOT/src" "$HERE/src"
find "$HERE/src" -name '__pycache__' -type d -prune -exec rm -rf {} +
cp "$ROOT/scripts/verify_model_integrity.py" "$HERE/scripts/"

# Downloads into $ROOT/models/**/artifact (gitignored) -- fails loudly on any
# missing or failed download, never proceeds with a partial model set.
bash "$ROOT/scripts/fetch_model_artifacts.sh"

for endpoint in herg_inhibition cyp3a4_inhibition; do
  cp "$ROOT/models/registry/${endpoint}_v1.json" "$HERE/models/registry/"
  mkdir -p "$HERE/models/admet/${endpoint}"
  cp "$ROOT/models/admet/${endpoint}/inference_support_manifest.json" "$HERE/models/admet/${endpoint}/"
  cp -R "$ROOT/models/admet/${endpoint}/artifact" "$HERE/models/admet/${endpoint}/artifact"
done

echo "bundle assembled: $(du -sm "$HERE/src" "$HERE/models" | awk '{s+=$1} END {print s}') MB of source+models"

# ---------------------------------------------------------------------------
# Fit the function under Vercel's 500 MB bundle limit. Measured on the first
# real build: 505 MB, i.e. over by 5 MB. About 98 MB of the installed packages
# is test suites and bytecode caches that are never imported at runtime.
# Vercel installs dependencies into this venv BEFORE running this script, and
# bundles the venv afterwards, so pruning here is what reaches the bundle.
# ---------------------------------------------------------------------------
VENV="$HERE/.vercel/python/.venv"
if [ -d "$VENV" ]; then
  SP="$(echo "$VENV"/lib/python3.*/site-packages)"
  BEFORE="$(du -sm "$SP" | cut -f1)"
  find "$SP" -type d \( -name tests -o -name test -o -name __pycache__ \) -prune -exec rm -rf {} +
  AFTER="$(du -sm "$SP" | cut -f1)"
  echo "site-packages: ${BEFORE} MB -> ${AFTER} MB after pruning test dirs and bytecode caches"

  # Safety net: prove the pruned environment still works by running a REAL
  # prediction (exercises numpy, scipy, scikit-learn unpickling and RDKit).
  # A bad prune fails the build here instead of shipping a broken function.
  (cd "$HERE" && DRUGSIM_ENVIRONMENT=local "$VENV/bin/python" -c "
import index
from drugsim_predict.pipeline import run_inference
r = run_inference('CCO')
print('post-prune check ok:', r.model_id, r.predicted_label)
")
else
  echo "note: no venv at $VENV -- skipping prune (the bundle may exceed Vercel's size limit)" >&2
fi
