# Tests for MovieLens loading, couple feedback mapping, splitting and the matrix factorization trainer
import numpy as np
import pandas as pd

from recommender.model.data import load_couple_feedback, load_movielens, split, split_all, split_couple
from recommender.model.evaluate import auc
from recommender.model.mf import export, predict, train

COUPLE_COLS = ["viewer", "movielens_id", "liked"]


def _couple(rows):
    return pd.DataFrame(rows, columns=COUPLE_COLS)


def test_load_movielens_labels_and_dense_indices():
    ratings = pd.DataFrame({
        "userId": [500, 500, 900], "movieId": [7, 99, 7], "rating": [4.0, 3.5, 5.0],
        "timestamp": [1, 2, 3]})
    rows, user_index, item_index = load_movielens(ratings, _couple([]))
    assert item_index == {7: 0, 99: 1}
    assert user_index == {"me": 2, "wife": 3}
    by_pair = {(r.user_idx, r.item_idx): r.label for r in rows.itertuples()}
    assert by_pair[(0, 0)] == 1.0  # rating exactly 4.0 is a like
    assert by_pair[(0, 1)] == 0.0  # 3.5 is not
    assert by_pair[(1, 0)] == 1.0


def test_load_movielens_appends_couple_events():
    ratings = pd.DataFrame({
        "userId": [1, 1], "movieId": [10, 20], "rating": [5.0, 1.0], "timestamp": [1, 2]})
    couple = _couple([["me", 10, True], ["wife", 20, False], ["me", 555, True]])
    rows, user_index, item_index = load_movielens(ratings, couple)
    assert user_index == {"me": 1, "wife": 2}
    mine = rows[rows.user_idx == 1]
    assert list(zip(mine.item_idx, mine.label)) == [(item_index[10], 1.0)]  # 555 unknown, dropped
    wife = rows[rows.user_idx == 2]
    assert list(zip(wife.item_idx, wife.label)) == [(item_index[20], 0.0)]
    assert rows.user_idx.max() == user_index["wife"]


def test_load_couple_feedback_latest_mark_wins_and_unmapped_dropped():
    catalog = pd.DataFrame({
        "movie_key": ["a", "b", "c"],
        "movielens_id": pd.array([10, 20, None], dtype="Int64")})
    events = [
        {"kind": "mark", "viewer": "me", "movie_key": "a", "liked": True, "genres": [], "at": "2026-01-01"},
        {"kind": "mark", "viewer": "me", "movie_key": "a", "liked": False, "genres": [], "at": "2026-02-01"},
        {"kind": "mark", "viewer": "wife", "movie_key": "b", "liked": True, "genres": [], "at": "2026-01-01"},
        {"kind": "mark", "viewer": "me", "movie_key": "c", "liked": True, "genres": [], "at": "2026-01-01"},
        {"kind": "watched", "viewer": "me", "movie_key": "b", "liked": None, "genres": [], "at": "2026-03-01"},
    ]
    out = load_couple_feedback(events, catalog)
    assert list(out.columns) == COUPLE_COLS
    got = {(r.viewer, int(r.movielens_id)): bool(r.liked) for r in out.itertuples()}
    assert got == {("me", 10): False, ("wife", 20): True}


def test_load_couple_feedback_empty():
    out = load_couple_feedback([], pd.DataFrame({"movie_key": [], "movielens_id": []}))
    assert out.empty and list(out.columns) == COUPLE_COLS


def test_split_proportions_and_couple_split():
    df = pd.DataFrame({"user_idx": range(1000), "item_idx": 0, "label": 1.0})
    train_df, val, test = split(df)
    assert (len(train_df), len(val), len(test)) == (750, 150, 100)
    assert split(df)[0].equals(train_df)  # deterministic
    couple = pd.DataFrame({"user_idx": [1] * 10, "item_idx": range(10), "label": 1.0})
    ctrain, holdout = split_couple(couple)
    assert (len(ctrain), len(holdout)) == (8, 2)


def test_train_learns_block_structure_and_export_shapes():
    rng = np.random.default_rng(0)
    users, items = np.meshgrid(np.arange(50), np.arange(40), indexing="ij")
    users, items = users.ravel(), items.ravel()
    label = ((users < 25) == (items < 20)).astype(float)
    df = pd.DataFrame({"user_idx": users, "item_idx": items, "label": label})
    df = df.iloc[rng.permutation(len(df))]
    train_df, held = df.iloc[:1500], df.iloc[1500:]

    model = train(train_df, n_users=50, n_items=40, epochs=30)
    exp = export(model)

    scores = predict(model, held.user_idx.to_numpy(), held.item_idx.to_numpy())
    assert auc(held.label.to_numpy(), scores) >= 0.95

    assert exp["item_vecs"].shape == (40, 32) and exp["item_vecs"].dtype == np.float32
    assert exp["user_vecs"].shape == (50, 32)
    assert exp["item_bias"].shape == (40,) and exp["user_bias"].shape == (50,)
    assert isinstance(exp["global_bias"], float)


def test_rows_use_compact_dtypes():
    ratings = pd.DataFrame({"userId": [1, 2], "movieId": [5, 6], "rating": [4.0, 2.0], "timestamp": [1, 2]})
    rows, _, _ = load_movielens(ratings, _couple([["me", 5, True]]))
    assert rows.user_idx.dtype == np.int32 and rows.item_idx.dtype == np.int32
    assert rows.label.dtype == np.float32


def test_split_all_keeps_couple_rows_out_of_val_and_test():
    ml = pd.DataFrame({"user_idx": np.arange(1000, dtype=np.int32) % 50, "item_idx": np.int32(0),
                       "label": np.float32(1)})
    couple = pd.DataFrame({"user_idx": np.int32(50), "item_idx": np.arange(10, dtype=np.int32),
                           "label": np.float32(1)})
    df = pd.concat([ml, couple], ignore_index=True)
    train_df, val, test, holdout = split_all(df, {"me": 50, "wife": 51})
    assert (len(val), len(test), len(holdout)) == (150, 100, 2)
    assert len(train_df) == 750 + 8
    assert not (val.user_idx == 50).any() and not (test.user_idx == 50).any()
    assert (train_df.user_idx == 50).sum() == 8 and train_df.user_idx.dtype == np.int32


def test_predict_batches(monkeypatch):
    import recommender.model.mf as mf
    model = train(pd.DataFrame({"user_idx": np.int32([0, 1]), "item_idx": np.int32([0, 1]),
                                "label": np.float32([1, 0])}), 2, 2, epochs=1)
    u, i = np.int32([0, 1, 0, 1, 1]), np.int32([0, 1, 1, 0, 1])
    full = predict(model, u, i)
    monkeypatch.setattr(mf, "PREDICT_BATCH", 2)
    assert np.allclose(predict(model, u, i), full)
