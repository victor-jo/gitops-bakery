# Income drift pipeline: entities -> Feast features -> Evidently drift report against the champion's training features
import sys

from kfp import compiler, dsl, kubernetes

# The first two steps are the inference pipeline's own components, so they run in its image unchanged
sys.path[:0] = ["src", "../../kfp/pipeline/src"]
from components import read_entities, retrieve_features  # noqa: E402
from drift_components import detect_drift  # noqa: E402

GARAGE = "garage.gitlab.svc.cluster.local:3900"
ENV = {
    "S3_ENDPOINT": GARAGE,
    "S3_REGION": "garage",
    "AWS_DEFAULT_REGION": "garage",
    "AWS_ENDPOINT_URL": f"http://{GARAGE}",
    "FEAST_S3_ENDPOINT_URL": f"http://{GARAGE}",
    "MLFLOW_TRACKING_URI": "http://mlflow.mlflow.svc.cluster.local",
}
FEATURES = ",".join([
    "demographic:Sex", "demographic:Race", "demographic:Native_country",
    "relationship:Relationship", "relationship:Marital-Status",
    "occupation:Workclass", "occupation:Education", "occupation:Occupation",
])


def _wire(task):
    # Credentials come from a Kubernetes Secret instead of pipeline parameters, so they never appear in the KFP UI
    kubernetes.use_secret_as_env(task, secret_name="kfp-s3", secret_key_to_env={
        "AWS_ACCESS_KEY_ID": "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY": "AWS_SECRET_ACCESS_KEY"})
    for name, value in ENV.items():
        task.set_env_variable(name, value)
    return task


@dsl.pipeline(name="income-drift-detection", description="Compare today's Feast features with the champion's training features in Evidently")
def income_drift_detection(
    entity_bucket: str = "inference-datasets",
    entity_key: str = "entity_df.parquet",
    feature_config_bucket: str = "feature-registry",
    feature_config_key: str = "feature_store_cluster.yaml",
    feature_list: str = FEATURES,
    model_name: str = "income-classifier-best",
    model_alias: str = "champion",
    reference_context: str = "reference_features",
    evidently_url: str = "http://evidently-service-internal.evidently.svc.cluster.local:8000",
    project_name: str = "income-classifier",
):
    entities = _wire(read_entities(bucket=entity_bucket, key=entity_key))
    features = _wire(retrieve_features(entities=entities.outputs["entities"], config_bucket=feature_config_bucket,
                                       config_key=feature_config_key, feature_list=feature_list))
    _wire(detect_drift(features=features.outputs["features"], model_name=model_name, model_alias=model_alias,
                       reference_context=reference_context, evidently_url=evidently_url, project_name=project_name))


if __name__ == "__main__":
    compiler.Compiler().compile(income_drift_detection, "income_drift_detection.yaml")
    print("compiled income_drift_detection.yaml")
