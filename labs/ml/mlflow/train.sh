#!/usr/bin/env bash
# Runs the training notebook headless inside the Jupyter pod, the same run a browser session would do, and leaves the executed copy next to it
set -euo pipefail
source "$(dirname "$0")/../env.sh"
kubectl --context "$BAKERY_CONTEXT" -n mlflow exec deploy/jupyter -c jupyter -- \
  jupyter nbconvert --to notebook --execute work/mlflow/data_exploration_and_model_training.ipynb \
  --output executed.ipynb --ExecutePreprocessor.timeout=1800
echo "runs and the registered model are at $MLFLOW_URL"
