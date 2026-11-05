# Compiles the catalog and training KFP pipelines and checks their names and inputs
import re
import sys
from pathlib import Path

import pytest
import yaml
from kfp import compiler

PIPELINE_DIR = Path(__file__).resolve().parents[1] / "pipeline"
sys.path[:0] = [str(PIPELINE_DIR), str(PIPELINE_DIR / "src")]

from catalog_pipeline import movie_catalog  # noqa: E402
from training_pipeline import movie_recommender_training  # noqa: E402

FORBIDDEN = re.compile(r"secret|password|key", re.I)


def _compile(pipeline, path: Path) -> list[dict]:
    compiler.Compiler().compile(pipeline, str(path))
    return list(yaml.safe_load_all(path.read_text()))


def _input_names(spec: dict) -> list[str]:
    names = list(spec["root"].get("inputDefinitions", {}).get("parameters", {}))
    for comp in spec["components"].values():
        defs = comp.get("inputDefinitions", {})
        names += list(defs.get("parameters", {})) + list(defs.get("artifacts", {}))
    return names


@pytest.mark.parametrize("pipeline,name", [
    (movie_catalog, "movie-catalog"),
    (movie_recommender_training, "movie-recommender-training"),
])
def test_pipeline_compiles_without_credential_inputs(tmp_path, pipeline, name):
    spec = _compile(pipeline, tmp_path / "p.yaml")[0]
    assert spec["pipelineInfo"]["name"] == name
    bad = [n for n in _input_names(spec) if FORBIDDEN.search(n)]
    assert bad == []


def test_training_yaml_names_the_model(tmp_path):
    _compile(movie_recommender_training, tmp_path / "t.yaml")
    assert "movie-recommender" in (tmp_path / "t.yaml").read_text()


def test_catalog_has_the_three_steps_and_a_page_cap(tmp_path):
    spec = _compile(movie_catalog, tmp_path / "c.yaml")[0]
    tasks = spec["root"]["dag"]["tasks"]
    assert {"collect-justwatch", "collect-coupang", "match-and-build"} <= set(tasks)
    assert spec["root"]["inputDefinitions"]["parameters"]["max_pages"]["defaultValue"] == 0


def test_training_has_the_four_steps(tmp_path):
    spec = _compile(movie_recommender_training, tmp_path / "t.yaml")[0]
    tasks = set(spec["root"]["dag"]["tasks"])
    assert {"prepare-movielens", "train", "evaluate-and-gate", "place-catalog"} <= tasks
