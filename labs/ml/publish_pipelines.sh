#!/usr/bin/env bash
# Compiles the lab's three pipelines and registers them in KFP, adding a new version when a pipeline is already there
set -euo pipefail
cd "$(dirname "$0")"
source ./env.sh
PY="$PWD/.venv-kfp/bin/python"
(cd kfp/pipeline && "$PY" pipeline.py)
(cd drift/pipeline && "$PY" pipeline.py && "$PY" inference_with_drift.py)
"$PY" - <<'PYEOF'
import os
from datetime import datetime, timezone

from kfp import Client

PIPELINES = [
    ("income-batch-inference", "kfp/pipeline/income_batch_inference.yaml",
     "Chapter 5: entities -> Feast features -> MLflow champion -> predictions in Garage"),
    ("income-drift-detection", "drift/pipeline/income_drift_detection.yaml",
     "Chapter 6: Feast features vs the champion's training features in Evidently; fails on dataset drift"),
    ("income-batch-inference-with-drift", "drift/pipeline/income_batch_inference_with_drift.yaml",
     "Chapter 6, book layout: the drift check sits before inference and stops it on dataset drift"),
]
client = Client(host=os.environ["KFP_URL"])
version = datetime.now(timezone.utc).strftime("v%Y%m%d-%H%M%S")
for name, package, description in PIPELINES:
    pipeline_id = client.get_pipeline_id(name)
    if pipeline_id is None:
        p = client.upload_pipeline(package, pipeline_name=name, description=description)
        print(f"registered {name}: {p.pipeline_id}")
    else:
        v = client.upload_pipeline_version(package, pipeline_version_name=version, pipeline_id=pipeline_id)
        print(f"new version of {name}: {v.display_name}")
print(f"pipelines: {os.environ['KFP_URL']}/#/pipelines")
PYEOF
