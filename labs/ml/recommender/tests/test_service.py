# Tests for the service's catalog reload: which movie frame it serves and which Feast views it materializes
import pandas as pd

from serving import service


class _FakeFeast:
    def __init__(self):
        self.materialized = []

    def materialize_incremental(self, end_date, feature_views):
        self.materialized.append(feature_views)


def _store(monkeypatch, frame, views):
    monkeypatch.setattr(service.movie_features, "load", lambda: (frame, views))
    monkeypatch.setattr(service, "champion_global_bias", lambda: 0.25)
    store = object.__new__(service.LiveStore)  # skip __init__, which reaches Garage and Valkey
    store.feast = _FakeFeast()
    store.reload()
    return store


def test_reload_serves_the_joined_frame_and_materializes_its_three_views(monkeypatch):
    frame = pd.DataFrame({"movie_key": ["a"]})
    store = _store(monkeypatch, frame, ["movie_catalog", "movie_popularity", "movie_embedding"])
    assert store.catalog() is frame and store.global_bias() == 0.25
    assert store.feast.materialized == [["movie_catalog", "movie_popularity", "movie_embedding"]]


def test_reload_from_the_legacy_parquet_starts_without_materializing(monkeypatch):
    legacy = pd.DataFrame({"movie_key": ["old"]})
    store = _store(monkeypatch, legacy, [])
    assert store.catalog() is legacy
    assert store.feast.materialized == []
