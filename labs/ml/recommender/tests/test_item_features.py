# Tests for the item features the hybrid MF projects into its item space
import numpy as np
import pandas as pd

from recommender.genres import CANONICAL
from recommender.model.content import N_DECADES
from recommender.model.item_features import item_features, movielens_year

N_GENRES = len(CANONICAL)


def _movies():
    return pd.DataFrame({
        "movieId": [10, 20, 30],
        "title": ["Toy Story (1995)", "Oldboy (2003)", "Untitled"],
        "genres": ["Animation|Children|Comedy", "Mystery|Thriller", "(no genres listed)"],
    })


def _catalog():
    # 20 is Korean and in MovieLens; the Korean movie without an id and the non-Korean 10 add nothing
    return pd.DataFrame({
        "movielens_id": pd.array([20, None, 10], dtype="Int64"),
        "korean": [True, True, False],
    })


def _train_rows(counts: dict[int, int]):
    items = [i for i, n in counts.items() for _ in range(n)]
    return pd.DataFrame({"user_idx": 0, "item_idx": np.array(items, dtype=np.int32), "label": np.float32(1)})


def test_movielens_year_reads_the_trailing_parenthesised_year():
    assert movielens_year("Toy Story (1995)") == 1995
    assert movielens_year("Babylon 5: The Gathering (1993) ") == 1993
    assert movielens_year("Untitled") is None
    assert movielens_year(None) is None


def test_rows_follow_the_item_index_and_carry_genres_decade_korean_and_popularity():
    # Item index order differs from the movies table: movie 30 is item 0, 10 is item 1, 20 is item 2
    index = {30: 0, 10: 1, 20: 2}
    feats = item_features(index, _movies(), _catalog(), _train_rows({0: 1, 1: 100, 2: 10}))
    assert feats.shape == (3, N_GENRES + N_DECADES + 2) and feats.dtype == np.float32

    genres = feats[:, :N_GENRES]
    assert {CANONICAL[g] for g in np.flatnonzero(genres[1])} == {"animation", "comedy", "family"}
    assert {CANONICAL[g] for g in np.flatnonzero(genres[2])} == {"mystery", "thriller"}
    assert genres[0].sum() == 0

    decades = feats[:, N_GENRES:N_GENRES + N_DECADES]
    assert decades.sum(axis=1).tolist() == [1, 1, 1]
    assert decades[0, -1] == 1  # no year in the title: the unknown slot
    assert np.argmax(decades[1]) == (1990 - 1900) // 10 and np.argmax(decades[2]) == (2000 - 1900) // 10

    assert feats[:, -2].tolist() == [0.0, 0.0, 1.0]

    pop = feats[:, -1]
    assert np.isclose(pop.mean(), 0, atol=1e-6) and np.isclose(pop.std(), 1, atol=1e-5)
    assert pop[1] > pop[2] > pop[0]  # 100 rows > 10 rows > 1 row


def test_items_missing_from_movies_and_from_training_rows():
    feats = item_features({10: 0, 77: 1}, _movies(), _catalog(), _train_rows({0: 5}))
    assert feats[1, :N_GENRES].sum() == 0 and feats[1, N_GENRES + N_DECADES - 1] == 1
    assert feats[1, -1] < feats[0, -1]  # no training rows ranks below five


def test_equal_popularity_gives_a_zero_column_instead_of_nan():
    feats = item_features({10: 0, 20: 1}, _movies(), _catalog(), _train_rows({0: 3, 1: 3}))
    assert np.all(feats[:, -1] == 0)
