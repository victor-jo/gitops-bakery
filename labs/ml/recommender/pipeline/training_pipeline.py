# Training pipeline: MovieLens 25M plus the couple's marks -> MF and content model -> gate -> champion features
import sys
from pathlib import Path

from kfp import compiler, dsl

sys.path[:0] = [str(Path(__file__).parent), str(Path(__file__).parent / "src")]
from components import evaluate_and_gate, place_catalog, prepare_movielens, train  # noqa: E402
from wiring import wire  # noqa: E402


@dsl.pipeline(name="movie-recommender-training", description="Train the movie-recommender MF, gate it against the champion and place the catalog")
def movie_recommender_training(
    epochs: int = 5,
    # 0 trains on every MovieLens user; a positive value samples that many users for a quick run
    sample_users: int = 0,
    dim: int = 32,
):
    ml = wire(prepare_movielens(), memory="6Gi")
    trained = wire(train(epochs=epochs, sample_users=sample_users, dim=dim), cpu="4", memory="8Gi").after(ml)
    gated = wire(evaluate_and_gate(run_id=trained.outputs["Output"], holdout=trained.outputs["holdout"]),
                 cpu="2", memory="6Gi")
    wire(place_catalog(), memory="2Gi").after(gated)


if __name__ == "__main__":
    compiler.Compiler().compile(movie_recommender_training, str(Path(__file__).with_name("movie_recommender_training.yaml")))
    print("compiled movie_recommender_training.yaml")
