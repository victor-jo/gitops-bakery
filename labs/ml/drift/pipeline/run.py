# Submits the compiled income drift pipeline to the lab KFP and waits for it to finish; an optional argument sets drift_strength
import os
import sys

from kfp import Client

# The second argument picks the package: income_drift_detection.yaml (default) or income_batch_inference_with_drift.yaml
package = sys.argv[2] if len(sys.argv) > 2 else "income_drift_detection.yaml"
client = Client(host=os.environ["KFP_URL"])
run = client.create_run_from_pipeline_package(package, arguments={"drift_strength": float(sys.argv[1]) if len(sys.argv) > 1 else 0.0},
                                         run_name=package.removesuffix(".yaml").replace("_", "-"))
print("run id:", run.run_id)
print("state:", client.wait_for_run_completion(run.run_id, timeout=1800).state)
print("reports:", os.environ.get("EVIDENTLY_URL", "$EVIDENTLY_URL"))
