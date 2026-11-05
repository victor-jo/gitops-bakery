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


def test_couple_rows_map_by_viewer_name():
    new = _arrays([10], [100, 200], [[1.0]] * 3, [[1.0], [-1.0]])
    champion = _arrays([10], [200, 100], [[1.0]] * 3, [[-1.0], [1.0]])
    couple = pd.DataFrame([(1 + k % 2, k % 2, float(k % 2 == 0), "couple") for k in range(12)],
                          columns=["user_idx", "item_idx", "label", "split"])
    holdout = pd.concat([_holdout().query("user_idx == 0"), couple], ignore_index=True)
    new_m, champ_m, couple_size, n_rows = steps.compare_on_same_rows(new, champion, holdout)
    assert n_rows == 16 and couple_size == 12
    assert new_m["couple_auc"] == champ_m["couple_auc"] == 1.0


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
