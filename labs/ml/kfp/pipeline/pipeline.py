# Income batch-inference pipeline: entities -> Feast historical features -> MLflow champion model -> predictions in Garage
import sys

from kfp import compiler, dsl, kubernetes

sys.path.insert(0, "src")
from components import read_entities, retrieve_features, run_inference, write_predictions  # noqa: E402

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


@dsl.pipeline(name="income-batch-inference", description="Score users with the champion income model using Feast features")
def income_batch_inference(
    entity_bucket: str = "inference-datasets",
    entity_key: str = "entity_df.parquet",
    feature_config_bucket: str = "feature-registry",
    feature_config_key: str = "feature_store_cluster.yaml",
    feature_list: str = FEATURES,
    model_name: str = "income-classifier-best",
    model_alias: str = "champion",
    output_bucket: str = "inference-datasets",
    output_key: str = "predictions_kfp.parquet",
):
    entities = _wire(read_entities(bucket=entity_bucket, key=entity_key))
    features = _wire(retrieve_features(entities=entities.outputs["entities"], config_bucket=feature_config_bucket,
                                       config_key=feature_config_key, feature_list=feature_list))
    predictions = _wire(run_inference(features=features.outputs["features"], model_name=model_name, model_alias=model_alias))
    _wire(write_predictions(predictions=predictions.outputs["predictions"], bucket=output_bucket, key=output_key))


if __name__ == "__main__":
    compiler.Compiler().compile(income_batch_inference, "income_batch_inference.yaml")
    print("compiled income_batch_inference.yaml")
