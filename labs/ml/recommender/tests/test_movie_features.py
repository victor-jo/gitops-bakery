# Tests for the movie feature parquets: what each run writes, how readers join them, and the legacy fallback
import numpy as np
import pandas as pd
import pytest

from recommender import movie_features as mf

AT = pd.Timestamp("2026-11-05T05:00:00Z")


def _catalog(keys=("a", "b", "c")):
    n = len(keys)
    return pd.DataFrame({
        "movie_key": list(keys), "tmdb_id": ["1"] * n, "title": [f"t{k}" for k in keys],
        "services": [["nfx"]] * n, "genres": [["drama"]] * n,
        "release_year": pd.array([2024] + [None] * (n - 1), dtype="Int64"),
        "korean": [True] + [False] * (n - 1), "new_this_week": [False] * n,
        "poster_url": [None] * n, "popularity_kr": np.linspace(1.0, 0.5, n), "description": ["x"] * n,
        "actors": [["y"]] * n,
    })


def test_catalog_run_writes_only_the_catalog_and_popularity_parquets():
    frames = mf.catalog_frames(_catalog(), AT)
    assert set(frames) == {"features/movie_catalog.parquet", "features/movie_popularity.parquet"}
    cat, pop = frames["features/movie_catalog.parquet"], frames["features/movie_popularity.parquet"]
    assert list(cat.columns) == ["movie_key", "title", "services", "genres", "release_year", "korean",
                                 "new_this_week", "poster_url", "description", "actors", "event_timestamp"]
    assert list(pop.columns) == ["movie_key", "popularity_kr", "event_timestamp"]
    assert (cat["event_timestamp"] == AT).all() and (pop["event_timestamp"] == AT).all()


def test_embedding_frame_carries_the_champion_version():
    vecs = np.arange(6, dtype=np.float32).reshape(3, 2)
    out = mf.embedding_frame(_catalog(), vecs, np.array([0.1, 0.2, 0.3], np.float32), "7", AT)
    assert list(out.columns) == ["movie_key", "vector", "bias", "model_version", "event_timestamp"]
    assert list(out["model_version"]) == ["7"] * 3
    assert out["bias"].dtype == np.float64
    assert list(out["vector"].iloc[1]) == [2.0, 3.0]


def test_written_parquets_keep_the_nullable_year_and_korean_flag(tmp_path):
    for key, frame in mf.catalog_frames(_catalog(), AT).items():
        frame.to_parquet(tmp_path / "f.parquet", index=False)
        back = pd.read_parquet(tmp_path / "f.parquet")
        if key == mf.key(mf.CATALOG):
            assert back["release_year"].iloc[0] == 2024 and pd.isna(back["release_year"].iloc[1])
            assert back["korean"].tolist() == [True, False, False]
        assert str(back["event_timestamp"].dt.tz) == "UTC"


def _frames(catalog_keys=("a", "b", "c"), placed=("c", "a", "gone")):
    cat = mf.catalog_frames(_catalog(catalog_keys), AT)
    vecs = np.ones((len(placed), 2), np.float32)
    emb = mf.embedding_frame(pd.DataFrame({"movie_key": list(placed)}), vecs, np.zeros(len(placed)), "3", AT)
    return cat[mf.key(mf.CATALOG)], cat[mf.key(mf.POPULARITY)], emb


def test_join_keeps_catalog_order_and_only_placed_movies():
    out = mf.join(*_frames())
    # b has no vector yet and "gone" left the catalog, so both drop out
    assert list(out["movie_key"]) == ["a", "c"]
    expected = {"movie_key", *mf.COLUMNS[mf.CATALOG], *mf.COLUMNS[mf.POPULARITY], *mf.COLUMNS[mf.EMBEDDING]}
    assert set(out.columns) == expected
    assert out["popularity_kr"].tolist() == [1.0, 0.5]


def test_join_gives_a_movie_without_popularity_zero():
    cat, pop, emb = _frames(placed=("a", "b", "c"))
    out = mf.join(cat, pop[pop["movie_key"] != "b"], emb)
    assert out.set_index("movie_key")["popularity_kr"].to_dict() == {"a": 1.0, "b": 0.0, "c": 0.5}


def _bucket(monkeypatch, objects: dict[str, pd.DataFrame]):
    monkeypatch.setattr(mf.s3, "list_keys", lambda prefix: [k for k in objects if k.startswith(prefix)])
    monkeypatch.setattr(mf.s3, "read_parquet", lambda key: objects[key])


def test_load_joins_the_three_parquets_and_names_their_views(monkeypatch):
    cat, pop, emb = _frames()
    _bucket(monkeypatch, {mf.LEGACY: pd.DataFrame({"movie_key": ["old"]}),
                          mf.key(mf.CATALOG): cat, mf.key(mf.POPULARITY): pop, mf.key(mf.EMBEDDING): emb})
    frame, views = mf.load()
    assert views == ["movie_catalog", "movie_popularity", "movie_embedding"]
    assert list(frame["movie_key"]) == ["a", "c"]


@pytest.mark.parametrize("missing", ["movie_catalog", "movie_popularity", "movie_embedding"])
def test_load_falls_back_to_the_legacy_parquet_until_every_new_one_exists(monkeypatch, missing):
    cat, pop, emb = _frames()
    legacy = pd.DataFrame({"movie_key": ["old"], "vector": [[1.0, 0.0]], "bias": [0.0]})
    objects = {mf.LEGACY: legacy, mf.key(mf.CATALOG): cat, mf.key(mf.POPULARITY): pop, mf.key(mf.EMBEDDING): emb}
    del objects[mf.key(missing)]
    _bucket(monkeypatch, objects)
    frame, views = mf.load()
    assert views == [] and frame is legacy
