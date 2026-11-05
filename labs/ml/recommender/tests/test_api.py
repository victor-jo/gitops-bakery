# Tests for the recommender HTTP API over an in-memory store, and the service settings
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from recommender.core.state import Event
from recommender.genres import CANONICAL
from serving.api import create_app


def _catalog():
    # (key, vector, genres, popularity): a2 is a near twin of a; b points the other way
    rows = [
        ("a", [2.0, 0.0], ["drama"], 0.9),
        ("a2", [1.8, 0.2], ["drama"], 0.1),
        ("b", [0.0, 2.0], ["drama"], 0.8),
        ("c", [1.0, 1.0], ["drama"], 0.7),
        ("d", [-1.0, 1.0], ["drama"], 0.6),
        ("e", [0.5, 0.5], ["comedy"], 0.95),
        ("f", [0.2, 0.2], ["drama"], 0.5),
    ]
    return pd.DataFrame(
        {
            "movie_key": [r[0] for r in rows],
            "title": [f"T{r[0]}" for r in rows],
            "poster_url": [None if r[0] == "f" else f"http://img/{r[0]}" for r in rows],
            "services": [np.array(["nfx", "cou"], dtype=object)] * len(rows),
            "genres": [np.array(r[2], dtype=object) for r in rows],
            "popularity_kr": [r[3] for r in rows],
            "new_this_week": [False] * len(rows),
            "vector": [np.array(r[1], np.float32) for r in rows],
            "bias": [0.0] * len(rows),
        }
    )


class MemStore:
    def __init__(self, catalog=None, events=None):
        self.cat = _catalog() if catalog is None else catalog
        self.log = list(events or [])
        self.pushed: list[tuple[str, np.ndarray]] = []
        self.online: dict[str, np.ndarray] = {}  # the Feast online store: the last pushed vector per viewer
        self.reads: list[str] = []

    def catalog(self):
        return self.cat

    def global_bias(self):
        return 0.0

    def append(self, event):
        self.log.append(event)

    def events(self):
        return list(self.log)

    def push_taste(self, viewer, vector):
        self.pushed.append((viewer, np.asarray(vector)))
        self.online[viewer] = np.asarray(vector)

    def taste(self, viewer):
        self.reads.append(viewer)
        return self.online.get(viewer)


def _at(minute):
    return datetime(2026, 11, 5, 12, minute, tzinfo=timezone.utc)


def _client(store):
    return TestClient(create_app(store))


def _keys(resp):
    assert resp.status_code == 200, resp.text
    return [r["movie_key"] for r in resp.json()]


def test_genres_lists_every_canonical_genre_with_its_korean_label():
    out = _client(MemStore()).get("/api/genres").json()
    assert [g["id"] for g in out] == list(CANONICAL)
    assert {"id": "thriller", "label": "스릴러"} in out


def test_onboarding_shows_chosen_genres_by_popularity_and_excludes_marked_movies():
    store = MemStore()
    c = _client(store)
    assert c.post("/api/viewer/me/genres", json={"genres": ["drama"]}).json() == {"ok": True}
    assert _keys(c.get("/api/onboarding", params={"viewer": "me"})) == ["a", "b", "c", "d", "f", "a2"]
    assert c.post("/api/mark", json={"viewer": "me", "movie_key": "b", "liked": True,
                                     "source": "onboarding"}).json() == {"ok": True}
    assert _keys(c.get("/api/onboarding", params={"viewer": "me"})) == ["a", "c", "d", "f", "a2"]
    page = c.get("/api/onboarding", params={"viewer": "me", "offset": 1, "limit": 2}).json()
    assert [r["movie_key"] for r in page] == ["c", "d"]
    assert page[0]["services"] == ["Netflix", "Coupang Play"]
    assert c.get("/api/onboarding", params={"viewer": "me", "offset": 50}).json() == []
    # The other viewer's marks do not hide anything from me, and mine do not hide anything from her
    c.post("/api/viewer/wife/genres", json={"genres": ["drama"]})
    assert "b" in _keys(c.get("/api/onboarding", params={"viewer": "wife"}))
    nulls = [r for r in c.get("/api/onboarding", params={"viewer": "me"}).json() if r["movie_key"] == "f"]
    assert nulls[0]["poster_url"] is None


def test_mark_changes_the_next_recommendations():
    store = MemStore()
    c = _client(store)
    for v in ("me", "wife"):
        c.post(f"/api/viewer/{v}/genres", json={"genres": ["drama"]})
    before = _keys(c.get("/api/recommendations"))
    assert "a" in before
    for v in ("me", "wife"):
        c.post("/api/mark", json={"viewer": v, "movie_key": "a", "liked": True, "source": "onboarding"})
    after = _keys(c.get("/api/recommendations"))
    assert "a" not in after
    assert after.index("a2") < before.index("a2")
    rec = c.get("/api/recommendations").json()[0]
    assert set(rec) == {"movie_key", "title", "poster_url", "services", "new_this_week",
                        "p_me", "p_wife", "source", "reason"}


def test_mark_appends_an_event_and_pushes_only_that_viewers_new_taste():
    store = MemStore()
    c = _client(store)
    store.pushed.clear()
    c.post("/api/mark", json={"viewer": "wife", "movie_key": "b", "liked": False, "source": "watched"})
    e = store.log[-1]
    assert (e.kind, e.viewer, e.movie_key, e.liked) == ("mark", "wife", "b", False)
    assert e.at.tzinfo is not None
    assert [v for v, _ in store.pushed] == ["wife"]
    assert store.pushed[0][1].shape == (2,)
    assert store.pushed[0][1] @ np.array([0.0, 1.0]) < 0  # disliking b turns her away from b's direction


def test_watched_is_recorded_and_excluded_from_recommendations():
    store = MemStore()
    c = _client(store)
    assert "e" in _keys(c.get("/api/recommendations"))
    assert c.post("/api/watched", json={"movie_key": "e"}).json() == {"ok": True}
    assert store.log[-1].kind == "watched" and store.log[-1].movie_key == "e"
    assert "e" not in _keys(c.get("/api/recommendations"))


def test_state_is_rebuilt_from_stored_events_at_start():
    events = [
        Event("genres", "me", None, None, ["drama"], _at(0)),
        Event("mark", "me", "a", True, None, _at(1)),
        Event("watched", None, "c", None, None, _at(2)),
    ]
    store = MemStore(events=events)
    c = _client(store)
    assert {v for v, _ in store.pushed} == {"me", "wife"}
    assert "a" not in _keys(c.get("/api/onboarding", params={"viewer": "me"}))
    recs = _keys(c.get("/api/recommendations"))
    assert "a" not in recs and "c" not in recs


def test_a_new_catalog_is_picked_up_and_both_viewers_are_refolded():
    store = MemStore()
    c = _client(store)
    c.post("/api/mark", json={"viewer": "me", "movie_key": "a", "liked": True, "source": "onboarding"})
    store.cat = _catalog().iloc[1:].reset_index(drop=True)  # "a" left the catalog
    store.pushed.clear()
    assert _keys(c.get("/api/recommendations"))
    assert {v for v, _ in store.pushed} == {"me", "wife"}
    assert c.post("/api/watched", json={"movie_key": "a"}).status_code == 404


class FailingPushStore(MemStore):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.fail = True
        self.attempts: list[tuple[str, np.ndarray]] = []

    def push_taste(self, viewer, vector):
        self.attempts.append((viewer, np.asarray(vector)))
        if self.fail:
            raise ConnectionError("valkey down")
        super().push_taste(viewer, vector)


def test_a_failed_taste_push_still_records_the_mark():
    events = [Event("genres", v, None, None, ["drama"], _at(0)) for v in ("me", "wife")]
    store = FailingPushStore(events=events)
    c = _client(store)  # start-up survives the failing pushes too
    before = _keys(c.get("/api/recommendations"))
    n = len(store.log)
    resp = c.post("/api/mark", json={"viewer": "me", "movie_key": "a", "liked": True, "source": "onboarding"})
    assert resp.status_code == 200 and resp.json() == {"ok": True}
    assert len(store.log) == n + 1
    after = _keys(c.get("/api/recommendations"))
    assert after != before and "a" not in after


def test_a_failed_push_during_a_catalog_change_still_refolds_both_viewers():
    store = FailingPushStore()
    c = _client(store)
    c.post("/api/mark", json={"viewer": "me", "movie_key": "b", "liked": True, "source": "onboarding"})
    c.post("/api/mark", json={"viewer": "wife", "movie_key": "d", "liked": True, "source": "onboarding"})
    store.cat = _catalog().assign(vector=[np.array([y, x], np.float32) for x, y in _catalog()["vector"]])
    old = {v: u for v, u in store.attempts}
    store.attempts.clear()
    assert c.get("/api/recommendations").status_code == 200
    new = dict(store.attempts)
    assert sorted(new) == ["me", "wife"]
    # Each refolded taste follows the swapped axes of the new catalog
    for v in ("me", "wife"):
        np.testing.assert_allclose(new[v], old[v][::-1], atol=1e-4)


def _p(c, viewer):
    return {r["movie_key"]: r[f"p_{viewer}"] for r in c.get("/api/recommendations").json()}


def test_recommendations_score_with_the_taste_read_from_the_store():
    store = MemStore()
    c = _client(store)
    store.reads.clear()
    store.online["me"] = np.array([0.0, 5.0], np.float32)  # Feast says "me" loves b's direction
    p = _p(c, "me")
    assert sorted(store.reads) == ["me", "wife"]
    assert p["b"] == pytest.approx(1 / (1 + np.exp(-10.0)))
    assert p["a"] == pytest.approx(0.5)
    assert _p(c, "wife")["b"] == pytest.approx(0.5)  # her stored taste is still the zero prior


def test_a_mark_is_pushed_and_then_read_back_for_the_next_recommendations():
    store = MemStore()
    c = _client(store)
    before = _p(c, "wife")
    c.post("/api/mark", json={"viewer": "wife", "movie_key": "b", "liked": False, "source": "onboarding"})
    pushed = store.pushed[-1]
    assert pushed[0] == "wife"
    np.testing.assert_array_equal(store.online["wife"], pushed[1])
    store.reads.clear()
    after = _p(c, "wife")
    assert "wife" in store.reads
    assert after["d"] < before["d"]  # d leans toward b, which she now dislikes


def test_recommendations_page_through_the_picks_then_the_popular_fallback():
    store = MemStore()
    c = _client(store)
    c.post("/api/viewer/wife/genres", json={"genres": ["drama"]})
    c.post("/api/mark", json={"viewer": "me", "movie_key": "e", "liked": True, "source": "onboarding"})
    c.post("/api/watched", json={"movie_key": "a2"})
    # Feast says "me" leans away from b's direction: b falls below the strong-dislike floor, c and d below the veto
    store.online["me"] = np.array([0.0, -1.0], np.float32)
    pages = [c.get("/api/recommendations", params={"offset": o, "limit": 3}).json() for o in (0, 3, 6)]
    assert [[(r["movie_key"], r["source"]) for r in p] for p in pages] == [
        [("a", "pick"), ("f", "pick"), ("c", "popular")], [("d", "popular")], []]
    # The marked, the watched and the strongly disliked never appear, as picks or as popular movies
    assert {r["movie_key"] for p in pages for r in p}.isdisjoint({"e", "a2", "b"})
    assert c.get("/api/recommendations", params={"limit": 0}).status_code == 422


class BrokenReadStore(MemStore):
    def __init__(self, broken, **kw):
        super().__init__(**kw)
        self.broken = broken

    def taste(self, viewer):
        if self.broken == "raise":
            raise ConnectionError("valkey down")
        if self.broken == "none":
            return None
        return np.zeros(3, np.float32)  # a vector of the wrong shape


@pytest.mark.parametrize("broken,why", [("raise", "valkey down"), ("none", "no vector stored"),
                                        ("shape", "expected (2,)")])
def test_a_failed_or_empty_store_read_falls_back_to_the_folded_taste(broken, why, caplog):
    marks = [Event("mark", "me", "b", True, None, _at(1)), Event("mark", "wife", "d", False, None, _at(2))]
    expected = _p(_client(MemStore(events=marks)), "me")
    c = _client(BrokenReadStore(broken, events=marks))
    with caplog.at_level("WARNING", logger="serving.api"):
        resp = c.get("/api/recommendations")
    assert resp.status_code == 200
    assert {r["movie_key"]: r["p_me"] for r in resp.json()} == pytest.approx(expected)
    lines = [r.getMessage() for r in caplog.records]
    assert len(lines) == 2
    for vid, line in zip(("me", "wife"), lines):
        assert line.startswith(f"taste of {vid} comes from memory") and why in line


def test_a_taste_whose_push_failed_is_not_read_back_stale():
    store = FailingPushStore()
    store.fail = False
    c = _client(store)
    store.fail = True
    c.post("/api/mark", json={"viewer": "me", "movie_key": "b", "liked": True, "source": "onboarding"})
    store.reads.clear()
    p = _p(c, "me")
    assert store.reads == ["wife"]  # the store still holds her current taste but not his
    assert p["c"] > 0.5  # his folded taste, liking b, is used rather than the stale zero vector
    store.fail = False
    c.get("/api/recommendations")  # the queued push lands on the next request
    assert store.attempts[-1][0] == "me"
    np.testing.assert_array_equal(store.online["me"], store.attempts[-1][1])


@pytest.mark.parametrize(
    "method,path,body",
    [
        ("post", "/api/viewer/kid/genres", {"genres": ["drama"]}),
        ("get", "/api/onboarding?viewer=kid", None),
        ("post", "/api/mark", {"viewer": "kid", "movie_key": "a", "liked": True, "source": "onboarding"}),
        ("post", "/api/mark", {"viewer": "me", "movie_key": "zzz", "liked": True, "source": "onboarding"}),
        ("post", "/api/watched", {"movie_key": "zzz"}),
    ],
)
def test_unknown_viewer_or_movie_is_404(method, path, body):
    store = MemStore()
    c = _client(store)
    n = len(store.log)
    resp = c.post(path, json=body) if method == "post" else c.get(path)
    assert resp.status_code == 404
    assert "detail" in resp.json()
    assert len(store.log) == n


def test_invalid_bodies_are_422():
    c = _client(MemStore())
    assert c.post("/api/viewer/me/genres", json={"genres": ["noir"]}).status_code == 422
    assert c.post("/api/mark", json={"viewer": "me", "movie_key": "a", "liked": True,
                                     "source": "elsewhere"}).status_code == 422
    assert c.post("/api/mark", json={"viewer": "me", "movie_key": "a"}).status_code == 422


def test_static_ui_is_served_at_root():
    c = _client(MemStore())
    resp = c.get("/")
    assert resp.status_code == 200 and "app.js" in resp.text
    assert c.get("/app.js").status_code == 200


ENV = {
    "MLFLOW_TRACKING_URI": "http://mlflow.example:5000",
    "EVIDENTLY_URL": "http://evidently.example:8000",
    "S3_ENDPOINT": "garage.example:3900",
    "VALKEY_ADDRESS": "valkey.example:16379",
}


def test_settings_come_from_env(monkeypatch):
    from serving.service import Settings

    for k, v in ENV.items():
        monkeypatch.setenv(k, v)
    s = Settings.from_env()
    assert (s.mlflow_tracking_uri, s.evidently_url, s.s3_endpoint, s.valkey_address) == tuple(ENV.values())
    monkeypatch.delenv("MLFLOW_TRACKING_URI")
    with pytest.raises(RuntimeError, match="MLFLOW_TRACKING_URI"):
        Settings.from_env()


def test_event_keys_sort_by_time_under_the_feedback_prefix():
    from serving.service import event_key

    k1 = event_key(Event("mark", "me", "a", True, None, _at(1)))
    k2 = event_key(Event("mark", "me", "a", True, None, _at(2)))
    assert k1.startswith("feedback/events/2026-11-05T12") and k1.endswith(".json")
    assert k1 < k2 and k1 != event_key(Event("mark", "me", "a", True, None, _at(1)))


def test_onboarding_puts_the_newest_movies_first():
    cat = _catalog()
    cat["release_year"] = pd.array([2001, 2026, 2010, 2026, 2024, 2020, None], dtype="Int64")
    c = _client(MemStore(catalog=cat))
    c.post("/api/viewer/me/genres", json={"genres": ["drama"]})
    # Newest year first; within a year the more popular one first; a missing year goes last
    assert _keys(c.get("/api/onboarding", params={"viewer": "me"})) == ["c", "a2", "d", "b", "a", "f"]


def test_onboarding_puts_korean_movies_first_within_a_year():
    cat = _catalog()
    cat["release_year"] = pd.array([2026] * 7, dtype="Int64")
    cat["korean"] = [False, True, False, False, True, False, False]
    c = _client(MemStore(catalog=cat))
    c.post("/api/viewer/me/genres", json={"genres": ["drama"]})
    assert _keys(c.get("/api/onboarding", params={"viewer": "me"})) == ["d", "a2", "a", "b", "c", "f"]
