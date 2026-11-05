# Tests for the Bayesian review rating that combines IMDb, TMDB and Coupang scores
import numpy as np
import pandas as pd
import pytest

from recommender.catalog.rating import review_rating


def _df(**cols):
    return pd.DataFrame(cols)


def test_one_source_is_pulled_toward_the_catalog_mean_by_its_vote_count():
    # Coupang 1..5: medians of the counts is 10, so 10 votes weigh as much as the prior
    df = _df(coupang_rating=[5.0, 5.0, 3.0, 1.0], coupang_count=[1000, 10, 10, 10])
    r = review_rating(df)
    raw = np.array([1.0, 1.0, 0.5, 0.0])
    w = np.array([100.0, 1.0, 1.0, 1.0])
    mean = (w * raw).sum() / w.sum()
    assert r.tolist() == pytest.approx(list((mean + w * raw) / (1 + w)))
    assert r[0] > r[1] > r[2] > r[3]  # the many-vote 5.0 stays near 1, the few-vote one drifts to the mean


def test_sources_with_different_scales_and_counts_combine_into_one_rating():
    df = _df(imdb_score=[10.0, 1.0], imdb_votes=[5000, 5000], tmdb_score=[10.0, 0.0],
             coupang_rating=[None, 5.0], coupang_count=[0, 4])
    r = review_rating(df)
    # imdb weighs 1 each (its median is 5000), tmdb 0.25 on the first only, coupang 1 on the second only
    weighted = np.array([1.0 + 0.25 * 1.0, 0.0 + 1.0 * 1.0])
    weight = np.array([1.25, 2.0])
    mean = weighted.sum() / weight.sum()
    assert r.tolist() == pytest.approx(list((mean + weighted) / (1 + weight)))
    assert 0 < r.min() and r.max() < 1


def test_unrated_movies_stay_unknown():
    df = _df(imdb_score=[7.0, None, None], imdb_votes=[100, None, 50], tmdb_score=[0.0, 0.0, None],
             coupang_rating=[None, 4.0, None], coupang_count=[None, 0, None])
    r = review_rating(df)
    assert np.isfinite(r[0]) and r[1:].isna().all()  # a TMDB 0 is no rating, nor is a Coupang score with 0 votes
    assert review_rating(_df(title=["a"])).isna().all()  # no score columns at all
