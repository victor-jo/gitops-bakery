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
from schedule import CRONS, schedule_recurring  # noqa: E402
from catalog_pipeline import movie_catalog  # noqa: E402
from monitoring_pipeline import movie_recommender_monitoring  # noqa: E402
from training_pipeline import movie_recommender_training  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("pipeline", choices=["catalog", "training", "monitoring"])
parser.add_argument("--max-pages", type=int, default=0, help="catalog: cap new Coupang pages (0 = all)")
parser.add_argument("--epochs", type=int, default=5, help="training: MF epochs")
parser.add_argument("--sample-users", type=int, default=0, help="training: MovieLens users to sample (0 = all)")
parser.add_argument("--model-type", choices=["mf", "hybrid"], default="mf",
                    help="training: plain MF on ids, or hybrid with item features in the item vectors")
parser.add_argument("--schedule", action="store_true", help="create (or replace) the recurring run instead of one run: catalog daily 05:00 KST, training daily 06:00 KST, monitoring Monday 07:00 KST")
parser.add_argument("--no-wait", action="store_true", help="submit and exit without waiting for the run")
args = parser.parse_args()

if args.pipeline == "catalog":
    pipeline, name, arguments = movie_catalog, "movie-catalog", {"max_pages": args.max_pages}
elif args.pipeline == "monitoring":
    pipeline, name, arguments = movie_recommender_monitoring, "movie-recommender-monitoring", {}
else:
    pipeline, name = movie_recommender_training, "movie-recommender-training"
    arguments = {"epochs": args.epochs, "sample_users": args.sample_users, "model_type": args.model_type}

package = Path(__file__).with_name(f"{name.replace('-', '_')}.yaml")
compiler.Compiler().compile(pipeline, str(package))
client = Client(host=os.environ["KFP_URL"])
if args.schedule:
    cron = CRONS[name]
    # catalog: max_concurrency=1 so a slow crawl is never joined by a second run
    job = schedule_recurring(client, name, experiment_id=client.create_experiment(name).experiment_id, pipeline_package_path=str(package),
                             cron_expression=cron, max_concurrency=1, no_catchup=True, enable_caching=False, params=arguments)
    print("recurring run:", job.recurring_run_id, "name:", name, "cron (UTC):", cron)
    sys.exit(0)
run = client.create_run_from_pipeline_package(str(package), arguments=arguments, run_name=name)
print("run id:", run.run_id, "arguments:", arguments)
if not args.no_wait:
    started = time.time()
    state = client.wait_for_run_completion(run.run_id, timeout=6 * 3600).state
    print("state:", state, f"after {time.time() - started:.0f} s")
