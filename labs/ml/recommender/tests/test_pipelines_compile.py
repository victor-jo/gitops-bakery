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
    # Placement is the training run's job, so the catalog run writes no model outputs
    assert set(tasks) == {"collect-justwatch", "collect-coupang", "match-and-build"}
    assert tasks["match-and-build"]["dependentTasks"] == ["collect-coupang"]
    assert spec["root"]["inputDefinitions"]["parameters"]["max_pages"]["defaultValue"] == 0


def test_training_has_the_four_steps(tmp_path):
    spec = _compile(movie_recommender_training, tmp_path / "t.yaml")[0]
    tasks = set(spec["root"]["dag"]["tasks"])
    assert {"prepare-movielens", "train", "evaluate-and-gate", "place-catalog"} <= tasks


def test_monitoring_pipeline_has_one_step_and_the_evidently_url(tmp_path):
    from monitoring_pipeline import movie_recommender_monitoring

    docs = _compile(movie_recommender_monitoring, tmp_path / "m.yaml")
    assert docs[0]["pipelineInfo"]["name"] == "movie-recommender-monitoring"
    assert set(docs[0]["root"]["dag"]["tasks"]) == {"report-monitoring"}
    assert "evidently-service-internal.evidently.svc.cluster.local" in (tmp_path / "m.yaml").read_text()


def test_weekly_cron_is_monday_0700_kst_in_utc():
    from schedule import MONITORING_CRON, weekly_cron_utc

    assert MONITORING_CRON == "0 0 22 * * 0"  # Sunday 22:00 UTC
    assert weekly_cron_utc(weekday=1, hour=3, minute=30) == "0 30 18 * * 0"  # crosses back one day
    assert weekly_cron_utc(weekday=0, hour=2) == "0 0 17 * * 6"  # Sunday 02:00 KST wraps to Saturday


def test_schedule_crons_in_utc():
    from schedule import CATALOG_CRON, TRAINING_CRON, daily_cron_utc

    assert CATALOG_CRON == "0 0 20 * * *"  # 05:00 KST is 20:00 UTC the day before
    assert TRAINING_CRON == "0 0 21 * * *"  # daily 06:00 KST is 21:00 UTC the day before
    assert daily_cron_utc(hour=3, minute=30) == "0 30 18 * * *"


class _FakeClient:
    """Two pages of recurring runs; create_recurring_run adds one or raises."""

    def __init__(self, fail=False):
        from types import SimpleNamespace as NS

        self.NS, self.fail, self.deleted = NS, fail, []
        self.pages = {"": [NS(recurring_run_id="a", display_name="movie-catalog")], "t2": [NS(recurring_run_id="b", display_name="other"), NS(recurring_run_id="c", display_name="movie-catalog")]}

    def list_recurring_runs(self, page_token, page_size):
        return self.NS(recurring_runs=self.pages[page_token], next_page_token="t2" if page_token == "" else "")

    def create_recurring_run(self, **kw):
        if self.fail:
            raise RuntimeError("create failed")
        new = self.NS(recurring_run_id="new", display_name=kw["job_name"])
        self.pages["t2"].append(new)
        return new

    def delete_recurring_run(self, run_id):
        self.deleted.append(run_id)


def test_schedule_recurring_deletes_old_same_name_across_pages_after_create():
    fake = _FakeClient()
    from schedule import schedule_recurring

    assert schedule_recurring(fake, "movie-catalog").recurring_run_id == "new"
    assert fake.deleted == ["a", "c"]  # "c" sits on page two; "b" has another name and "new" is kept


def test_schedule_recurring_keeps_old_runs_when_create_fails():
    import pytest
    from schedule import schedule_recurring

    fake = _FakeClient(fail=True)
    with pytest.raises(RuntimeError):
        schedule_recurring(fake, "movie-catalog")
    assert fake.deleted == []
