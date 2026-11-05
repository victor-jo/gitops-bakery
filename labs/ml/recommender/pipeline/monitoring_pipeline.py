# Monitoring pipeline: the couple's joint thumbs-up rate, genre drift and taste shift sent to Evidently
import sys
from pathlib import Path

from kfp import compiler, dsl

sys.path[:0] = [str(Path(__file__).parent), str(Path(__file__).parent / "src")]
from components import report_monitoring  # noqa: E402
from wiring import wire  # noqa: E402

# The Evidently service inside the cluster; the Mac reaches the same service through its sslip.io host
EVIDENTLY = "http://evidently-service-internal.evidently.svc.cluster.local:8000"


@dsl.pipeline(name="movie-recommender-monitoring", description="Report the joint thumbs-up rate, genre drift and taste shift to Evidently")
def movie_recommender_monitoring():
    wire(report_monitoring(), memory="2Gi").set_env_variable("EVIDENTLY_URL", EVIDENTLY)


if __name__ == "__main__":
    compiler.Compiler().compile(movie_recommender_monitoring, str(Path(__file__).with_name("movie_recommender_monitoring.yaml")))
    print("compiled movie_recommender_monitoring.yaml")
