# Tests for the pipeline step helpers: like-for-like champion scoring, catalog sanity checks and user sampling
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline" / "src"))
import steps  # noqa: E402


def _arrays(user_ids, item_ids, user_vecs, item_vecs, names=("me", "wife")):
    n = len(user_ids)
    return {
        "user_vecs": np.asarray(user_vecs, dtype=np.float32), "item_vecs": np.asarray(item_vecs, dtype=np.float32),
        "user_bias": np.zeros(len(user_vecs), np.float32), "item_bias": np.zeros(len(item_vecs), np.float32),
        "global_bias": np.array(0.0), "user_ids": np.asarray(user_ids),
        "user_index": np.array(json.dumps({name: n + k for k, name in enumerate(names)})),
        "item_index": np.array(json.dumps({str(m): i for i, m in enumerate(item_ids)})),
    }


def _holdout():
    # New model space: users 0,1,2 = MovieLens 10,20,30; items 0,1 = movies 100,200
    rows = []
    for split in ("val", "test"):
        for u in (0, 1, 2):
            rows += [(u, 0, 1.0, split), (u, 1, 0.0, split)]
    return pd.DataFrame(rows, columns=["user_idx", "item_idx", "label", "split"])


def test_champion_is_scored_on_the_same_rows_through_its_own_index_maps():
    # The new model ranks movie 100 above 200 for every user, so it is perfect
    new = _arrays([10, 20, 30], [100, 200], [[1.0]] * 5, [[1.0], [-1.0]])
    # The champion knows users 20 and 10 (in that order) and movies 200, 100 (reversed),
    # and it is perfect as well once its indices are mapped correctly
    champion = _arrays([20, 10], [200, 100], [[1.0]] * 4, [[-1.0], [1.0]])
    new_m, champ_m, couple_size, n_rows = steps.compare_on_same_rows(new, champion, _holdout())
    # User 30 is unknown to the champion, so its 4 rows are dropped for both models
    assert n_rows == 8
    assert new_m["val_auc"] == champ_m["val_auc"] == 1.0
    assert couple_size == 0


def test_comparison_drops_rows_for_items_the_champion_never_saw():
    new = _arrays([10, 20, 30], [100, 200], [[1.0]] * 5, [[1.0], [-1.0]])
    champion = _arrays([10, 20, 30], [100], [[1.0]] * 5, [[1.0]])
    _, _, _, n_rows = steps.compare_on_same_rows(new, champion, _holdout())
    assert n_rows == 6


def _couple_holdout():
    # Users 1 and 2 are me and wife: both like movie 100 (item 0) and dislike movie 200 (item 1)
    held = [(1 + k % 2, k // 2 % 2, float(k // 2 % 2 == 0), "couple") for k in range(12)]
    folded = [(u, i, float(i == 0), "couple_train") for u in (1, 2) for i in (0, 1, 0, 1)]
    return pd.DataFrame(held + folded, columns=["user_idx", "item_idx", "label", "split"])


def test_couple_rows_map_by_viewer_name():
    new = _arrays([10], [100, 200], [[1.0]] * 3, [[1.0], [-1.0]])
    champion = _arrays([10], [200, 100], [[1.0]] * 3, [[-1.0], [1.0]])
    holdout = pd.concat([_holdout().query("user_idx == 0"), _couple_holdout()], ignore_index=True)
    new_m, champ_m, couple_size, n_rows = steps.compare_on_same_rows(new, champion, holdout)
    # The 8 couple_train rows only feed the fold-in, so they are neither scored nor counted
    assert n_rows == 16 and couple_size == 12
    assert new_m["couple_auc"] == champ_m["couple_auc"] == 1.0


def test_couple_auc_folds_each_viewer_in_instead_of_using_trained_user_vectors():
    # The trained me/wife vectors point the wrong way; the item vectors are informative
    arrays = _arrays([10], [100, 200], [[1.0], [-5.0], [-5.0]], [[1.0], [-1.0]])
    metrics, couple_size = steps._metrics(arrays, pd.concat([_holdout().query("user_idx == 0"),
                                                             _couple_holdout()], ignore_index=True))
    assert couple_size == 12 and metrics["couple_auc"] == 1.0


def test_couple_auc_without_couple_train_rows_scores_with_the_zero_prior():
    arrays = _arrays([10], [100, 200], [[1.0], [-5.0], [-5.0]], [[1.0], [-1.0]])
    arrays["item_bias"] = np.array([1.0, -1.0], np.float32)
    rows = _couple_holdout().query("split == 'couple'")
    metrics, _ = steps._metrics(arrays, pd.concat([_holdout().query("user_idx == 0"), rows], ignore_index=True))
    # With no marks to fold in, the taste is the zero prior and the item bias alone ranks
    assert metrics["couple_auc"] == 1.0


def _catalog(counts):
    rows = [{"movie_key": f"{s}{i}", "services": [s]} for s, n in counts.items() for i in range(n)]
    return pd.DataFrame(rows)


def test_service_check_passes_and_fails():
    steps.check_services(_catalog({"nfx": 10, "dnp": 10, "cou": 10}), None)
    steps.check_services(_catalog({"nfx": 10, "dnp": 5, "cou": 10}),
                         _catalog({"nfx": 10, "dnp": 10, "cou": 3}))
    with pytest.raises(RuntimeError, match="cou"):
        steps.check_services(_catalog({"nfx": 10, "dnp": 10}), None)
    with pytest.raises(RuntimeError, match="dnp"):
        steps.check_services(_catalog({"nfx": 10, "dnp": 4, "cou": 10}),
                             _catalog({"nfx": 10, "dnp": 10, "cou": 10}))


def test_sample_users_is_clamped_to_the_users_there_are():
    ratings = pd.DataFrame({"userId": [1, 1, 2, 3], "movieId": [5, 6, 5, 5], "rating": [4.0] * 4})
    assert len(steps._sample(ratings, 10)) == 4
    assert steps._sample(ratings, 2)["userId"].nunique() == 2


def test_comparison_without_shared_rows_raises():
    new = _arrays([10, 20, 30], [100, 200], [[1.0]] * 5, [[1.0], [-1.0]])
    champion = _arrays([99], [100, 200], [[1.0]] * 3, [[1.0], [-1.0]])
    with pytest.raises(RuntimeError, match="no holdout rows"):
        steps.compare_on_same_rows(new, champion, _holdout())


class _FakeContent:
    def place(self, catalog):
        return np.ones((len(catalog), 4), np.float32), np.zeros(len(catalog), np.float32)


def _placing(tmp_path, monkeypatch) -> tuple[dict, list]:
    """Fake a champion v7 whose content model places every movie; returns the writes and download URIs."""
    import pickle
    import types

    (tmp_path / "artifacts").mkdir()
    with open(tmp_path / "artifacts" / "content.pkl", "wb") as f:
        pickle.dump(_FakeContent(), f)
    uris = []

    def download(uri, **_):
        uris.append(uri)
        return str(tmp_path)

    monkeypatch.setitem(sys.modules, "mlflow", types.SimpleNamespace(
        artifacts=types.SimpleNamespace(download_artifacts=download)))
    monkeypatch.setattr(steps, "_champion_version", lambda: "7")
    written = {}
    catalog = pd.DataFrame({"movie_key": ["a", "b"], "title": ["A", "B"], "popularity_kr": [0.5, 0.1]})
    monkeypatch.setattr(steps.s3, "read_parquet", lambda key: catalog)
    monkeypatch.setattr(steps.s3, "write_parquet", lambda df, key: written.update({key: df}))
    return written, uris


def test_place_catalog_stamps_every_row_with_a_utc_event_time(tmp_path, monkeypatch):
    written, _ = _placing(tmp_path, monkeypatch)

    before = pd.Timestamp.now(tz="UTC")
    steps.place_catalog()
    after = pd.Timestamp.now(tz="UTC")

    stamp = written["features/movie_embedding.parquet"]["event_timestamp"]
    assert str(stamp.dt.tz) == "UTC"
    assert stamp.nunique() == 1 and before <= stamp.iloc[0] <= after


def test_place_catalog_writes_only_the_embedding_parquet_of_the_champion_version(tmp_path, monkeypatch):
    written, uris = _placing(tmp_path, monkeypatch)
    assert steps.place_catalog() == 2
    assert list(written) == ["features/movie_embedding.parquet"]
    out = written["features/movie_embedding.parquet"]
    assert list(out.columns) == ["movie_key", "vector", "bias", "model_version", "event_timestamp"]
    assert list(out["model_version"]) == ["7", "7"]
    # Pinned to the version, so a promotion between the lookup and the download cannot mislabel the vectors
    assert uris == ["models:/movie-recommender/7"]


def test_place_catalog_skips_without_a_champion(monkeypatch, capsys):
    monkeypatch.setattr(steps, "_champion_version", lambda: None)
    monkeypatch.setattr(steps.s3, "write_parquet", lambda df, key: pytest.fail("must not write features"))
    assert steps.place_catalog() == 0
    assert "skipping placement" in capsys.readouterr().out


def test_match_and_build_writes_the_catalog_and_its_two_feature_parquets(monkeypatch):
    from recommender.catalog import build, coupang

    catalog = pd.DataFrame({
        "movie_key": ["a"], "title": ["A"], "services": [["nfx", "dnp", "cou"]], "genres": [["drama"]],
        "release_year": pd.array([2025], dtype="Int64"), "korean": [True], "new_this_week": [True],
        "poster_url": [None], "popularity_kr": [0.9], "movielens_id": pd.array([None], dtype="Int64"),
        "description": ["d"], "actors": [["a"]]})
    monkeypatch.setattr(steps, "ensure_movielens", lambda: None)
    monkeypatch.setattr(steps, "_exists", lambda key: False)
    monkeypatch.setattr(coupang, "current_movies", lambda pages, sitemap: pages)
    monkeypatch.setattr(build, "match_coupang", lambda movies, search, known: movies.assign(tmdb_id=None))
    monkeypatch.setattr(build, "build_catalog", lambda *a: catalog)
    monkeypatch.setattr(steps.s3, "read_parquet", lambda key: pd.DataFrame({"url": [], "status": []}))
    monkeypatch.setattr(steps.s3, "put_json", lambda obj, key: None)
    written = {}
    monkeypatch.setattr(steps.s3, "write_parquet", lambda df, key: written.update({key: df}))

    steps.match_and_build()

    feature_keys = sorted(k for k in written if k.startswith("features/"))
    assert feature_keys == ["features/movie_catalog.parquet", "features/movie_popularity.parquet"]
    assert written["features/movie_catalog.parquet"]["korean"].tolist() == [True]
    assert written["features/movie_popularity.parquet"]["popularity_kr"].tolist() == [0.9]
