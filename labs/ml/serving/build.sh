#!/usr/bin/env bash
# Bakes the current champion into a Bento and a host-arch Docker image: import model -> bentoml build -> containerize
set -euo pipefail
cd "$(dirname "$0")/.."
source ./env.sh
export MLFLOW_TRACKING_URI="$MLFLOW_URL" MLFLOW_DISABLE_AGENT_HINT=1
# The server hands out presigned Garage URLs the Mac cannot resolve, so artifacts come through the server
export MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false
.venv/bin/python - <<'PY'
import pickle

import bentoml
import mlflow
from mlflow import MlflowClient

version = MlflowClient().get_model_version_by_alias("income-classifier-best", "champion")
columns = pickle.load(open(mlflow.artifacts.download_artifacts(f"runs:/{version.run_id}/column_list.pkl"), "rb"))
# The run id lets the service find this model's own training data, whatever is champion later
model = bentoml.mlflow.import_model(
    "income-classifier", "models:/income-classifier-best@champion",
    labels={"alias": "champion", "mlflow_version": version.version},
    metadata={"run_id": version.run_id},
    custom_objects={"column_list": columns},
)
print(f"imported {model.tag} from income-classifier-best v{version.version}")
PY
.venv/bin/bentoml build -f serving/bentofile.yaml . --output tag | tail -1 > serving/.bento-tag
TAG=$(sed 's/^__tag__://' serving/.bento-tag)
.venv/bin/bentoml containerize "$TAG" --platform "linux/$(uname -m | sed 's/x86_64/amd64/')" -t "income-classifier-drift:${TAG#*:}"
echo "image: income-classifier-drift:${TAG#*:}"
