# Submits the compiled income batch-inference pipeline to the lab KFP and waits for it to finish
import os

from kfp import Client

client = Client(host=os.environ["KFP_URL"])
run = client.create_run_from_pipeline_package("income_batch_inference.yaml", arguments={}, run_name="income-batch-inference")
print("run id:", run.run_id)
print("state:", client.wait_for_run_completion(run.run_id, timeout=1800).state)
