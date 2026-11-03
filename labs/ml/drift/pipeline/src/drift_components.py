# Containerized Python Component that runs the drift check inside the drift-pipeline image
import os

from kfp import dsl
from kfp.dsl import Dataset, Input

# Pods pull from Harbor by its in-cluster name (set by labs/ml/env.sh); the installer pushes it from the Mac as localhost:30001
IMAGE = os.environ.get("DRIFT_IMAGE", "drift-pipeline:0.1.0")
BASE = "python:3.13-slim"
PACKAGES = ["evidently==0.7.23", "mlflow==3.16.0", "minio==7.2.20", "pandas==2.3.3", "numpy==2.5.4", "pyarrow==25.0.1"]


@dsl.component(base_image=BASE, target_image=IMAGE, packages_to_install=PACKAGES)
def detect_drift(features: Input[Dataset], model_name: str, model_alias: str, reference_context: str,
                 evidently_url: str, project_name: str, drift_strength: float) -> float:
    from drift_steps import detect_drift as run

    return run(features.path, model_name, model_alias, reference_context, evidently_url, project_name, drift_strength)
