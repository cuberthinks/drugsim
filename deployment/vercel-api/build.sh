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
