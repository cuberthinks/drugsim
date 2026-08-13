#!/usr/bin/env bash
# Downloads the trained model artifacts from a GitHub Release into the
# local models/ tree, in exactly the layout drugsim_predict.model_registry
# expects (matching each registry file's own artifact.path /
# inference_support.*_path fields).
#
# Why this exists: models/**/artifact/ is gitignored on purpose (large
# trained-model binaries, not source -- see .gitignore and Dockerfile.
# predict-api's own header comment). This repo does not commit them and
# does not use Git LFS; instead they are attached as assets on a GitHub
# Release, and this script fetches them from there. Used both by
# Dockerfile.predict-api (build-time) and by anyone standing up a fresh
# clone outside Docker.
#
# Fails loudly (set -e, curl -f) on any missing/failed download -- this
# project never silently proceeds with a missing model artifact.
#
# Usage:
#   MODEL_RELEASE_URL_BASE=https://github.com/<owner>/<repo>/releases/download/<tag> \
#     scripts/fetch_model_artifacts.sh

set -euo pipefail

if [[ -z "${MODEL_RELEASE_URL_BASE:-}" ]]; then
    echo "MODEL_RELEASE_URL_BASE is not set -- refusing to proceed without knowing where to fetch model artifacts from." >&2
    echo "Example: MODEL_RELEASE_URL_BASE=https://github.com/YOUR_USER/drugsim/releases/download/models-v1" >&2
    exit 1
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# local path (relative to repo root) | release asset filename.
# Deliberately NOT a bash associative array (`declare -A`, bash 4.0+) --
# macOS ships bash 3.2 as /bin/bash (last GPLv2 release Apple shipped) with
# no associative-array support at all; a script that only works inside the
# eventual Debian-based Docker image but silently breaks for anyone
# testing it locally on a Mac is a real portability bug, not a hypothetical
# one (caught by actually running this against a local test server before
# trusting it in a Dockerfile). Plain newline-delimited pairs work
# identically on bash 3.2 and any later version.
#
# Asset filenames are namespaced by endpoint to keep the Release's asset
# list readable; only the three files each endpoint's registry entry
# actually checksum-verifies are fetched (models/admet/*/artifact/scaler.joblib,
# a dev-time-only intermediate, is deliberately NOT one of them).
FILES="
models/admet/herg_inhibition/artifact/model.joblib|herg_model.joblib
models/admet/herg_inhibition/artifact/inference_support.npz|herg_inference_support.npz
models/admet/herg_inhibition/artifact/descriptor_ad_scaler.joblib|herg_descriptor_ad_scaler.joblib
models/admet/cyp3a4_inhibition/artifact/model.joblib|cyp3a4_model.joblib
models/admet/cyp3a4_inhibition/artifact/inference_support.npz|cyp3a4_inference_support.npz
models/admet/cyp3a4_inhibition/artifact/descriptor_ad_scaler.joblib|cyp3a4_descriptor_ad_scaler.joblib
"

echo "$FILES" | while IFS='|' read -r local_path asset_name; do
    [ -z "$local_path" ] && continue
    dest="$ROOT/$local_path"
    mkdir -p "$(dirname "$dest")"
    echo "Fetching $asset_name -> $local_path"
    curl -fL --retry 3 --retry-delay 2 -o "$dest" "$MODEL_RELEASE_URL_BASE/$asset_name"
done

echo "All model artifacts fetched."
