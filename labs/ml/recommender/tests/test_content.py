# Tests for placing movies that lack MovieLens data from genres, decade and text
import pickle

import numpy as np
import pandas as pd
import pytest

from recommender.model.content import fit_content_model


def _row(key, ml_id, genres, year, desc="", actors=None):
    return {"movie_key": key, "tmdb_id": 0, "movielens_id": ml_id, "title": key,
            "release_year": year, "genres": genres, "description": desc,
            "actors": actors or []}


def _frame(rows):
    df = pd.DataFrame(rows)
    df["movielens_id"] = df["movielens_id"].astype("Int64")
    df["release_year"] = df["release_year"].astype("Int64")
    return df


def _fixture():
    rows, vecs, bias = [], [], []
    idx = {}
    for i in range(10):
        horror = i % 2 == 0
        rows.append(_row(f"m{i}", 100 + i, ["horror"] if horror else ["romance"],
                         1990 + i, "scary night" if horror else "love story"))
        vecs.append([1.0 if horror else -1.0, 0.0])
        bias.append(0.5 if horror else -0.5)
        idx[100 + i] = i
    rows.append(_row("new_h", None, ["horror"], 2024, "scary night"))
    rows.append(_row("unmapped", 999, ["romance"], None, "love story"))
    return (_frame(rows), np.array(vecs, dtype=np.float32),
            np.array(bias, dtype=np.float32), idx)


def test_unmatched_horror_is_placed_positive_and_matched_unchanged():
    catalog, vecs, bias, idx = _fixture()
    model = fit_content_model(catalog, vecs, bias, idx)
    out_v, out_b = model.place(catalog)
    assert out_v.shape == (12, 2) and out_b.shape == (12,)
    np.testing.assert_array_equal(out_v[:10], vecs)
    np.testing.assert_array_equal(out_b[:10], bias)
    assert out_v[10, 0] > 0 and out_b[10] > 0
    assert out_v[11, 0] < 0  # id missing from the map counts as unmatched


def test_model_is_picklable():
    catalog, vecs, bias, idx = _fixture()
    model = fit_content_model(catalog, vecs, bias, idx)
    again = pickle.loads(pickle.dumps(model))
    np.testing.assert_allclose(again.place(catalog)[0], model.place(catalog)[0])


def test_too_few_matched_rows_raises():
    catalog, vecs, bias, idx = _fixture()
    with pytest.raises(ValueError, match="at least 2"):
        fit_content_model(catalog, vecs, bias, {100: 0})
