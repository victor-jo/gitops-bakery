# Containerized Python Components for the income batch-inference pipeline, built with `kfp component build`
import os

from kfp import dsl
from kfp.dsl import Dataset, Input, Output

# Pods pull from Harbor by its in-cluster name (set by labs/ml/env.sh); the installer pushes it from the Mac as localhost:30001.
# Inside the running image this module is imported again without the variable, where the name no longer matters.
IMAGE = os.environ.get("KFP_IMAGE", "income-pipeline:0.1.0")
BASE = "python:3.13-slim"
# Same versions that passed the step-by-step run on the Mac; the model was trained with scikit-learn 1.9.1
PACKAGES = [
    "feast[redis,aws]==0.67.0",
    "mlflow==3.16.0",
    "scikit-learn==1.9.1",
    "skops==0.16.0",
    "pandas==2.3.3",
    "numpy==2.5.4",
    "pyarrow==25.0.1",
    "s3fs==2026.9.0",
    "minio==7.2.20",
]


@dsl.component(base_image=BASE, target_image=IMAGE, packages_to_install=PACKAGES)
def read_entities(bucket: str, key: str, entities: Output[Dataset]) -> int:
    from steps import read_entities as run

    return run(bucket, key, entities.path)


@dsl.component(base_image=BASE, target_image=IMAGE, packages_to_install=PACKAGES)
def retrieve_features(entities: Input[Dataset], config_bucket: str, config_key: str, feature_list: str, features: Output[Dataset]) -> int:
    from steps import retrieve_features as run

    return run(entities.path, config_bucket, config_key, feature_list, features.path)


@dsl.component(base_image=BASE, target_image=IMAGE, packages_to_install=PACKAGES)
def run_inference(features: Input[Dataset], model_name: str, model_alias: str, predictions: Output[Dataset]) -> int:
    from steps import run_inference as run

    return run(features.path, model_name, model_alias, predictions.path)


@dsl.component(base_image=BASE, target_image=IMAGE, packages_to_install=PACKAGES)
def write_predictions(predictions: Input[Dataset], bucket: str, key: str) -> int:
    from steps import write_predictions as run

    return run(predictions.path, bucket, key)
