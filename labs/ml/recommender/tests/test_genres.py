# Tests for the shared genre vocabulary and its source mappings
from recommender import genres


def test_justwatch():
    assert genres.from_justwatch(["act", "drm", "trl"]) == ["action", "drama", "thriller"]
    assert genres.from_justwatch(["scf", "rma", "xyz"]) == ["romance", "scifi"]


def test_coupang():
    assert genres.from_coupang(["범죄", "드라마", "스릴러", "실화 바탕"]) == ["crime", "drama", "thriller"]
    assert genres.from_coupang(["무협", "시대극"]) == ["action", "history"]
    assert genres.from_coupang(["키즈", "가족"]) == ["family"]


def test_movielens():
    assert genres.from_movielens("Action|Sci-Fi|IMAX") == ["action", "scifi"]


def test_korean_label_covers_canonical():
    assert set(genres.KOREAN_LABEL) == set(genres.CANONICAL)
    assert len(genres.CANONICAL) == 20
