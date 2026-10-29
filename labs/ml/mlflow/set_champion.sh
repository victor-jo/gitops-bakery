#!/usr/bin/env bash
# Points the "champion" alias at a version of income-classifier-best (newest by default); the KFP pipeline scores with that alias
set -euo pipefail
source "$(dirname "$0")/../env.sh"
MODEL=income-classifier-best
VERSION="${1:-$(curl -fsS "$MLFLOW_URL/api/2.0/mlflow/registered-models/get?name=$MODEL" |
  python3 -c 'import json,sys; print(max(int(v["version"]) for v in json.load(sys.stdin)["registered_model"]["latest_versions"]))')}"
curl -fsS -X POST "$MLFLOW_URL/api/2.0/mlflow/registered-models/alias" -H 'Content-Type: application/json' \
  -d "{\"name\": \"$MODEL\", \"alias\": \"champion\", \"version\": \"$VERSION\"}" >/dev/null
echo "$MODEL@champion -> v$VERSION"
