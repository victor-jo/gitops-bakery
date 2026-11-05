# Compiles and submits the movie catalog or training pipeline to the lab KFP; --no-wait returns right after submitting
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
from catalog_pipeline import movie_catalog  # noqa: E402
from training_pipeline import movie_recommender_training  # noqa: E402

parser = argparse.ArgumentParser()
parser.add_argument("pipeline", choices=["catalog", "training"])
parser.add_argument("--max-pages", type=int, default=0, help="catalog: cap new Coupang pages (0 = all)")
parser.add_argument("--epochs", type=int, default=5, help="training: MF epochs")
parser.add_argument("--sample-users", type=int, default=0, help="training: MovieLens users to sample (0 = all)")
parser.add_argument("--no-wait", action="store_true", help="submit and exit without waiting for the run")
args = parser.parse_args()

if args.pipeline == "catalog":
    pipeline, name, arguments = movie_catalog, "movie-catalog", {"max_pages": args.max_pages}
else:
    pipeline, name = movie_recommender_training, "movie-recommender-training"
    arguments = {"epochs": args.epochs, "sample_users": args.sample_users}

package = Path(__file__).with_name(f"{name.replace('-', '_')}.yaml")
compiler.Compiler().compile(pipeline, str(package))
client = Client(host=os.environ["KFP_URL"])
run = client.create_run_from_pipeline_package(str(package), arguments=arguments, run_name=name)
print("run id:", run.run_id, "arguments:", arguments)
if not args.no_wait:
    started = time.time()
    state = client.wait_for_run_completion(run.run_id, timeout=6 * 3600).state
    print("state:", state, f"after {time.time() - started:.0f} s")
