# Book-style inference pipeline with a drift gate: entities -> Feast features -> drift check -> champion model -> predictions
import sys

from kfp import compiler, dsl

# Same components as the two pipelines it combines: inference steps from labs/ml/kfp, the drift step from here
sys.path[:0] = ["src", "../../kfp/pipeline/src"]
from components import read_entities, retrieve_features, run_inference, write_predictions  # noqa: E402
from drift_components import detect_drift  # noqa: E402
from pipeline import FEATURES, _wire  # noqa: E402


@dsl.pipeline(name="income-batch-inference-with-drift",
              description="Score users with the champion model only when their features have not drifted from the training data")
def income_batch_inference_with_drift(
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
    # Shifts only the copy the drift check sees; inference always scores the real features
    drift_strength: float = 0.0,
    fail_on_drift: bool = True,
    output_bucket: str = "inference-datasets",
    output_key: str = "predictions_with_drift_check.parquet",
):
    entities = _wire(read_entities(bucket=entity_bucket, key=entity_key))
    features = _wire(retrieve_features(entities=entities.outputs["entities"], config_bucket=feature_config_bucket,
                                       config_key=feature_config_key, feature_list=feature_list))
    drift = _wire(detect_drift(features=features.outputs["features"], model_name=model_name, model_alias=model_alias,
                               reference_context=reference_context, evidently_url=evidently_url, project_name=project_name,
                               drift_strength=drift_strength, fail_on_drift=fail_on_drift))
    # .after() only orders the steps; it is the drift step failing on dataset drift that keeps inference from running
    predictions = _wire(run_inference(features=features.outputs["features"], model_name=model_name,
                                      model_alias=model_alias)).after(drift)
    _wire(write_predictions(predictions=predictions.outputs["predictions"], bucket=output_bucket, key=output_key))


if __name__ == "__main__":
    compiler.Compiler().compile(income_batch_inference_with_drift, "income_batch_inference_with_drift.yaml")
    print("compiled income_batch_inference_with_drift.yaml")
