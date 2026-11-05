# Tests for the weekly monitoring frames: joint thumbs-up flags, genre shares, taste shift, snapshot picking and panels
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from recommender.core.state import Event
from recommender.genres import CANONICAL
from recommender.monitoring import joint_like, pick_history, taste_vectors, weekly_frames

T0 = datetime(2026, 11, 1, 12, tzinfo=timezone.utc)


def _at(h):
    return T0 + timedelta(hours=h)


def _mark(viewer, key, liked, h):
    return Event("mark", viewer, key, liked, None, _at(h))


def _watched(key, h):
    return Event("watched", None, key, None, None, _at(h))


CAT = pd.DataFrame({"genres": [["drama", "comedy"], ["drama"]]})
TASTE = {"me": np.array([1.0, 2.0]), "wife": np.array([3.0, 4.0])}


def _frames(events):
    return weekly_frames(events, CAT, CAT, TASTE, TASTE)


def test_both_liked_is_one_only_when_both_marked_thumbs_up_after_watching():
    events = [_watched("a", 1), _mark("me", "a", True, 2), _mark("wife", "a", True, 3),
              _watched("b", 1), _mark("me", "b", True, 2), _mark("wife", "b", False, 3)]
    w = _frames(events)["watched"]
    assert dict(zip(w["movie_key"], w["both_liked"])) == {"a": 1, "b": 0}
    assert joint_like(w)["joint_like_rate"][0] == 0.5


def test_only_the_latest_mark_after_the_watch_counts():
    events = [_watched("a", 5), _mark("me", "a", False, 1), _mark("me", "a", True, 6),
              _mark("wife", "a", True, 7), _mark("wife", "a", False, 8)]
    assert _frames(events)["watched"]["both_liked"].tolist() == [0]
    events = [_watched("a", 5), _mark("me", "a", False, 1), _mark("wife", "a", True, 7)]
    assert _frames(events)["watched"]["both_liked"].tolist() == [0]  # my only mark predates the watch


def test_week_is_the_iso_week_in_kst():
    # Sunday 2026-11-01 16:00 UTC is Monday 2026-11-02 01:00 KST, which starts week 45
    f = _frames([Event("watched", None, "a", None, None, datetime(2026, 11, 1, 16, tzinfo=timezone.utc))])
    assert f["watched"]["week"].tolist() == ["2026-W45"]


def test_no_watched_events_gives_no_data_not_a_crash():
    f = _frames([])
    assert len(f["watched"]) == 0
    row = joint_like(f["watched"]).iloc[0]
    assert np.isnan(row["joint_like_rate"]) and row["watched_count"] == 0


def test_genre_mix_shares_sum_to_one_over_every_canonical_genre():
    mix = _frames([])["genre_mix_now"]
    assert mix["genre"].tolist() == list(CANONICAL)
    assert abs(mix["share"].sum() - 1.0) < 1e-12
    assert abs(mix.set_index("genre")["share"]["drama"] - 2 / 3) < 1e-12


def test_taste_shift_is_the_cosine_distance_per_viewer():
    before = {"me": np.array([1.0, 0.0]), "wife": np.array([3.0, 4.0])}
    now = {"me": np.array([0.0, 2.0]), "wife": np.array([6.0, 8.0])}
    shift = weekly_frames([], CAT, CAT, now, before)["taste_shift"]
    assert shift.columns.tolist() == ["taste_shift_me", "taste_shift_wife"] and len(shift) == 1
    assert abs(shift["taste_shift_me"][0] - 1.0) < 1e-12  # orthogonal
    assert abs(shift["taste_shift_wife"][0]) < 1e-12  # same direction
    zero = weekly_frames([], CAT, CAT, {"me": np.zeros(2), "wife": np.zeros(2)},
                         {"me": np.zeros(2), "wife": np.zeros(2)})["taste_shift"]
    assert zero.iloc[0].tolist() == [0.0, 0.0]


def test_pick_history_takes_newest_at_least_a_week_old_else_oldest():
    keys = [f"catalog/history/2026-11-0{d}.parquet" for d in (1, 2, 3, 5)]
    assert pick_history(keys, date(2026, 11, 9)).endswith("2026-11-02.parquet")
    assert pick_history(keys, date(2026, 11, 5)).endswith("2026-11-01.parquet")
    assert pick_history([], date(2026, 11, 5)) is None


def test_taste_before_ignores_later_marks():
    feats = pd.DataFrame({"movie_key": ["a", "b"], "vector": [np.array([1.0, 0.0], np.float32), np.array([0.0, 1.0], np.float32)],
                          "bias": [0.0, 0.0], "genres": [["drama"], ["drama"]], "popularity_kr": [1.0, 1.0]})
    events = [_mark("me", "a", True, 1), _mark("me", "b", False, 100)]
    early = taste_vectors(events, feats, 0.0, _at(50))["me"]
    late = taste_vectors(events, feats, 0.0)["me"]
    assert not np.allclose(early, late)
    assert early[0] > 0


def test_snapshot_builds_without_watched_events():
    from recommender.monitoring import build_snapshot

    metrics = build_snapshot(_frames([])).dict()["metrics"]
    names = [m["metric_name"] for m in metrics]
    assert "MeanValue(column=joint_like_rate)" in names
    assert "MeanValue(column=taste_shift_me)" in names and "MeanValue(column=taste_shift_wife)" in names
    assert any(n.startswith("DriftedColumnsCount") for n in names)
    # Only the genre column is drift-tested; taste columns are reported as values instead
    drift = [n for n in names if n.startswith("ValueDrift")]
    assert drift and all("genre" in n for n in drift)


class _Dashboard:
    def __init__(self, ws):
        self.ws = ws

    def add_panel(self, panel):
        self.ws.board.panels.append(panel)
        self.ws.board.tabs[0].panels.append(panel.id)


class _Workspace:
    """In-memory stand-in for the Evidently workspace's project and dashboard calls."""

    def __init__(self, titles):
        from types import SimpleNamespace as NS

        from evidently.sdk.models import DashboardModel, DashboardPanelPlot, DashboardTabModel

        panels = [DashboardPanelPlot(title=t, subtitle=None, size=None, values=[]) for t in titles]
        self.board = DashboardModel(tabs=[DashboardTabModel(title="General", panels=[p.id for p in panels])],
                                    panels=panels)
        self.project = NS(id="p1", dashboard=_Dashboard(self))
        self.saved = 0

    def search_project(self, name):
        return [self.project]

    def get_dashboard(self, project_id):
        return self.board.copy(deep=True)

    def save_dashboard(self, project_id, dashboard):
        self.saved += 1
        self.board = dashboard


def test_ensure_project_replaces_obsolete_panels_once():
    from recommender import monitoring as m

    ws = _Workspace(["Joint thumbs-up rate (last run)", m.WATCHED_PANEL, "Share of drifted columns"])
    m.ensure_project(ws, "movie-recommender")
    titles = [p.title for p in ws.board.panels]
    assert sorted(titles) == sorted([m.WATCHED_PANEL, m.JOINT_PANEL, m.DRIFT_PANEL, m.TASTE_PANEL])
    assert ws.board.tabs[0].panels == [p.id for p in ws.board.panels]
    taste = next(p for p in ws.board.panels if p.title == m.TASTE_PANEL)
    assert [v.metric_labels["column"] for v in taste.values] == ["taste_shift_me", "taste_shift_wife"]
    saved = ws.saved
    m.ensure_project(ws, "movie-recommender")
    assert [p.title for p in ws.board.panels] == titles and ws.saved == saved  # second run changes nothing
