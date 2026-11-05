# Compiles and submits the catalog, training or monitoring pipeline to the lab KFP; --no-wait returns right after submitting
import argparse
import os
import sys
import time
from pathlib import Path

from kfp import Client, compiler

# Component images are fixed at import time, so the in-cluster image name must be set first
if "REC_IMAGE" not in os.environ:
    sys.exit("REC_IMAGE is not set; run: source labs/ml/env.sh")
sys.path.insert(0, str(Path(__file__).parent))
from schedule import WEEKLY_CRON  # noqa: E402
from catalog_pipeline import movie_catalog  # noqa: E402
from monitoring_pipeline import movie_recommender_monitoring  # noqa: E402
from training_pipeline import movie_recommender_training  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("pipeline", choices=["catalog", "training", "monitoring"])
parser.add_argument("--max-pages", type=int, default=0, help="catalog: cap new Coupang pages (0 = all)")
parser.add_argument("--epochs", type=int, default=5, help="training: MF epochs")
parser.add_argument("--sample-users", type=int, default=0, help="training: MovieLens users to sample (0 = all)")
parser.add_argument("--weekly", action="store_true", help="monitoring: create a recurring run (Monday 07:00 KST) instead of one run")
parser.add_argument("--no-wait", action="store_true", help="submit and exit without waiting for the run")
args = parser.parse_args()

if args.pipeline == "catalog":
    pipeline, name, arguments = movie_catalog, "movie-catalog", {"max_pages": args.max_pages}
elif args.pipeline == "monitoring":
    pipeline, name, arguments = movie_recommender_monitoring, "movie-recommender-monitoring", {}
else:
    pipeline, name = movie_recommender_training, "movie-recommender-training"
    arguments = {"epochs": args.epochs, "sample_users": args.sample_users}

package = Path(__file__).with_name(f"{name.replace('-', '_')}.yaml")
compiler.Compiler().compile(pipeline, str(package))
client = Client(host=os.environ["KFP_URL"])
if args.weekly:
    if args.pipeline != "monitoring":
        sys.exit("--weekly only applies to the monitoring pipeline")
    job = client.create_recurring_run(experiment_id=client.create_experiment(name).experiment_id, job_name=f"{name}-weekly",
                                      pipeline_package_path=str(package), cron_expression=WEEKLY_CRON, no_catchup=True, enable_caching=False)
    print("recurring run:", job.recurring_run_id, "cron (UTC):", WEEKLY_CRON)
    sys.exit(0)
run = client.create_run_from_pipeline_package(str(package), arguments=arguments, run_name=name)
print("run id:", run.run_id, "arguments:", arguments)
if not args.no_wait:
    started = time.time()
    state = client.wait_for_run_completion(run.run_id, timeout=6 * 3600).state
    print("state:", state, f"after {time.time() - started:.0f} s")
