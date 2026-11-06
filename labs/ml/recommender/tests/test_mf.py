# Tests for MovieLens loading, couple feedback mapping, splitting and the matrix factorization trainer
import numpy as np
import pandas as pd

from recommender.model.data import (
    COUPLE_COLUMNS, couple_rows, load_couple_feedback, load_movielens, split, split_all, split_couple,
)
from recommender.model.evaluate import auc
from recommender.model.mf import export, predict, train

COUPLE_COLS = ["viewer", "movie_key", "movielens_id", "liked"]


def _couple(rows):
    """rows: (viewer, movielens_id, liked); the movie key is derived from the id."""
    return pd.DataFrame([(v, f"m{m}", m, liked) for v, m, liked in rows], columns=COUPLE_COLS)


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
    assert COUPLE_COLUMNS == COUPLE_COLS
    got = {(r.viewer, int(r.movielens_id)): bool(r.liked) for r in out.itertuples()}
    assert got == {("me", 10): False, ("wife", 20): True}


def test_load_couple_feedback_empty():
    out = load_couple_feedback([], pd.DataFrame({"movie_key": [], "movielens_id": []}))
    assert out.empty and list(out.columns) == COUPLE_COLS


def test_split_proportions():
    df = pd.DataFrame({"user_idx": range(1000), "item_idx": 0, "label": 1.0})
    train_df, val, test = split(df)
    assert (len(train_df), len(val), len(test)) == (750, 150, 100)
    assert split(df)[0].equals(train_df)  # deterministic


def _marks(n, viewers=("me", "wife")):
    return pd.DataFrame([(viewers[k % 2], f"key{k}", k, k % 3 == 0) for k in range(n)], columns=COUPLE_COLS)


def test_couple_split_is_a_stable_hash_of_viewer_and_movie():
    ctrain, holdout = split_couple(_marks(1000))
    assert 150 <= len(holdout) <= 250 and len(ctrain) + len(holdout) == 1000
    again_train, again_holdout = split_couple(_marks(1000))
    assert again_holdout.equals(holdout) and again_train.equals(ctrain)
    # The side depends on the mark, not on its position or on the other marks
    shuffled = _marks(1000).sample(frac=1, random_state=1)
    assert set(split_couple(shuffled)[1]["movie_key"]) == set(holdout["movie_key"])


def test_old_couple_marks_never_change_side_as_marks_are_added():
    old_train, old_holdout = split_couple(_marks(300))
    new_train, new_holdout = split_couple(_marks(1000))
    old_keys = set(_marks(300)["movie_key"])
    assert set(new_holdout["movie_key"]) & old_keys == set(old_holdout["movie_key"])
    assert set(new_train["movie_key"]) & old_keys == set(old_train["movie_key"])


def test_couple_split_of_no_marks_is_empty():
    ctrain, holdout = split_couple(_marks(0))
    assert ctrain.empty and holdout.empty


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
    train_df, val, test = split_all(df, {"me": 50, "wife": 51})
    assert (len(val), len(test)) == (150, 100)
    assert len(train_df) == 750 + 10
    assert not (val.user_idx == 50).any() and not (test.user_idx == 50).any()
    assert (train_df.user_idx == 50).sum() == 10 and train_df.user_idx.dtype == np.int32


def test_couple_rows_map_viewers_and_drop_unknown_movies():
    out = couple_rows(_couple([["me", 10, True], ["wife", 20, False], ["me", 555, True]]),
                      {"me": 7, "wife": 8}, {10: 0, 20: 1})
    assert list(zip(out.user_idx, out.item_idx, out.label)) == [(7, 0, 1.0), (8, 1, 0.0)]


def test_predict_batches(monkeypatch):
    import recommender.model.mf as mf
    model = train(pd.DataFrame({"user_idx": np.int32([0, 1]), "item_idx": np.int32([0, 1]),
                                "label": np.float32([1, 0])}), 2, 2, epochs=1)
    u, i = np.int32([0, 1, 0, 1, 1]), np.int32([0, 1, 1, 0, 1])
    full = predict(model, u, i)
    monkeypatch.setattr(mf, "PREDICT_BATCH", 2)
    assert np.allclose(predict(model, u, i), full)


def test_split_all_without_couple_rows():
    ml = pd.DataFrame({"user_idx": np.arange(100, dtype=np.int32) % 10, "item_idx": np.int32(0),
                       "label": np.float32(1)})
    train_df, val, test = split_all(ml, {"me": 10, "wife": 11})
    assert (len(train_df), len(val), len(test)) == (75, 15, 10)


def _genre_world(n_users=60, n_items=60, unseen=10, seed=0):
    """Half the users like genre A, half genre B; the last `unseen` items have no training rows.

    Returns (train rows, item features with a one-hot genre column pair, user group, item genre).
    """
    rng = np.random.default_rng(seed)
    user_group = np.arange(n_users) % 2
    item_genre = np.arange(n_items) % 2
    users, items = np.meshgrid(np.arange(n_users), np.arange(n_items - unseen), indexing="ij")
    users, items = users.ravel(), items.ravel()
    keep = rng.random(len(users)) < 0.5
    users, items = users[keep], items[keep]
    df = pd.DataFrame({"user_idx": users.astype(np.int32), "item_idx": items.astype(np.int32),
                       "label": (user_group[users] == item_genre[items]).astype(np.float32)})
    features = np.eye(2, dtype=np.float32)[item_genre]
    return df, features, user_group, item_genre


def test_default_train_is_the_plain_mf():
    from recommender.model.mf import MF

    df, _, _, _ = _genre_world()
    model = train(df, 60, 60, epochs=1)
    assert type(model) is MF
    np.testing.assert_array_equal(export(model)["item_vecs"], model.item_emb.weight.detach().numpy())


def test_hybrid_export_scores_like_predict_so_fold_in_sees_the_same_model():
    from recommender.model.mf import HybridMF

    df, features, _, _ = _genre_world()
    model = train(df, 60, 60, epochs=3, item_features=features)
    assert isinstance(model, HybridMF)
    exp = export(model)
    assert exp["item_vecs"].shape == (60, 32) and exp["item_bias"].shape == (60,)
    u, i = np.repeat(np.arange(60), 60), np.tile(np.arange(60), 60)
    logit = ((exp["user_vecs"][u] * exp["item_vecs"][i]).sum(1) + exp["user_bias"][u]
             + exp["item_bias"][i] + exp["global_bias"])
    np.testing.assert_allclose(1 / (1 + np.exp(-logit)), predict(model, u, i), atol=1e-5)


def test_hybrid_scores_items_without_training_rows_from_their_features():
    df, features, user_group, item_genre = _genre_world()
    unseen = np.arange(50, 60)
    u, i = np.repeat(np.arange(60), len(unseen)), np.tile(unseen, 60)
    truth = (user_group[u] == item_genre[i]).astype(float)

    hybrid = train(df, 60, 60, epochs=40, item_features=features)
    plain = train(df, 60, 60, epochs=40)
    # The plain MF never saw these items, so their vectors are still the random start
    assert auc(truth, predict(hybrid, u, i)) >= 0.95
    assert auc(truth, predict(plain, u, i)) < 0.8
