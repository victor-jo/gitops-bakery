#!/usr/bin/env bash
# Runs the drift check on the Mac: Feast features from the inference runner's steps 1-2, then the drift step against Evidently
set -euo pipefail
cd "$(dirname "$0")"
source ../env.sh
key() { kubectl --context "$BAKERY_CONTEXT" -n kubeflow get secret kfp-s3 -o jsonpath="{.data.$1}" | base64 -d; }
# Steps 1-2 of the inference runner write ../kfp/out/2_features.parquet; it needs the Garage tunnel from feast/pf.sh
[ -f ../kfp/out/2_features.parquet ] || { ../kfp/run_local.sh 1; ../kfp/run_local.sh 2; }
export AWS_ACCESS_KEY_ID=$(key AWS_ACCESS_KEY_ID) AWS_SECRET_ACCESS_KEY=$(key AWS_SECRET_ACCESS_KEY)
export S3_ENDPOINT=localhost:3900 S3_REGION=garage MLFLOW_TRACKING_URI="$MLFLOW_URL" MLFLOW_DISABLE_AGENT_HINT=1
# EVIDENTLY_URL may point at a port-forward instead (pf.sh), as in the book
../.venv/bin/python -c '
import os, sys
sys.path.insert(0, "pipeline/src")
from drift_steps import detect_drift
detect_drift("../kfp/out/2_features.parquet", os.environ.get("MODEL_NAME", "income-classifier-best"),
             os.environ.get("MODEL_ALIAS", "champion"), "reference_features", os.environ["EVIDENTLY_URL"], "income-classifier")
'
echo "reports: $EVIDENTLY_URL"
