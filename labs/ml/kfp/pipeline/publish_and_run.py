# Mirrors the KFP UI flow of the textbook: upload the pipeline, create an experiment, start a run with runtime parameters
import os

from kfp import Client

HOST = os.environ["KFP_URL"]
client = Client(host=HOST)

# 1) Upload pipeline (UI: Pipelines > Upload pipeline)
existing = client.list_pipelines(filter='{"predicates":[{"key":"display_name","operation":"EQUALS","stringValue":"income-classifier-pipeline"}]}').pipelines
if existing:
    pipeline = existing[0]
    print("pipeline already uploaded:", pipeline.pipeline_id)
else:
    pipeline = client.upload_pipeline("income_batch_inference.yaml", pipeline_name="income-classifier-pipeline",
                                      description="Batch income inference: entities -> Feast features -> MLflow champion -> Garage")
    print("uploaded pipeline:", pipeline.pipeline_id)
version = client.list_pipeline_versions(pipeline.pipeline_id).pipeline_versions[0]
print("pipeline version:", version.pipeline_version_id, version.display_name)

# 2) Create experiment (UI: Experiments > Create experiment)
experiment = client.create_experiment("income-classifier", description="Runs of the income classifier batch inference")
print("experiment:", experiment.experiment_id)

# 3) Create run with runtime parameters (UI: Create run > Run parameters > Start)
run = client.run_pipeline(experiment_id=experiment.experiment_id, job_name="income-classifier-run-1",
                          pipeline_id=pipeline.pipeline_id, version_id=version.pipeline_version_id,
                          params={"output_key": "income_classifier_predictions.parquet"})
print("run:", run.run_id)
print(f"run page: {HOST}/#/runs/details/{run.run_id}")
print("state:", client.wait_for_run_completion(run.run_id, timeout=1800).state)
