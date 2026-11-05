# Containerized Python Components of the movie catalog and training pipelines; bodies live in steps.py
import os

from kfp import dsl
from kfp.dsl import Dataset, Input, Output

# Pods pull from Harbor by its in-cluster name (set by labs/ml/env.sh); inside the image the name no longer matters
IMAGE = os.environ.get("REC_IMAGE", "recommender-pipeline:0.1.0")
BASE = "python:3.13-slim"


@dsl.component(base_image=BASE, target_image=IMAGE)
def collect_justwatch() -> int:
    from steps import collect_justwatch as run

    return run()


@dsl.component(base_image=BASE, target_image=IMAGE)
def collect_coupang(max_pages: int, pause: float) -> int:
    from steps import collect_coupang as run

    return run(max_pages, pause)


@dsl.component(base_image=BASE, target_image=IMAGE)
def match_and_build() -> int:
    from steps import match_and_build as run

    return run()


@dsl.component(base_image=BASE, target_image=IMAGE)
def prepare_movielens():
    from steps import ensure_movielens as run

    run()


@dsl.component(base_image=BASE, target_image=IMAGE)
def train(epochs: int, sample_users: int, dim: int, model_type: str, holdout: Output[Dataset]) -> str:
    from steps import train as run

    return run(epochs, sample_users, dim, holdout.path, model_type)


@dsl.component(base_image=BASE, target_image=IMAGE)
def evaluate_and_gate(run_id: str, holdout: Input[Dataset]) -> str:
    from steps import evaluate_and_gate as run

    return run(run_id, holdout.path)


@dsl.component(base_image=BASE, target_image=IMAGE)
def place_catalog() -> int:
    from steps import place_catalog as run

    return run()


@dsl.component(base_image=BASE, target_image=IMAGE)
def report_monitoring():
    from steps import report_monitoring as run

    run()
