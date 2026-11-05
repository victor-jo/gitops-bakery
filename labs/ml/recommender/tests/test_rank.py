# Tests for couple ranking, veto, gamble refill and reasons
import numpy as np
import pandas as pd

from recommender.core.rank import recommend
from recommender.core.state import CoupleState, ViewerState


def _logit(p):
    return float(np.log(p / (1 - p)))


def _cat(rows):
    """rows: (key, p_me, p_wife); vectors are [1,0], taste picks p via bias trick."""
    return pd.DataFrame(
        {
            "movie_key": [r[0] for r in rows],
            "title": [f"T{r[0]}" for r in rows],
            "poster_url": ["u"] * len(rows),
            "services": [["nfx"]] * len(rows),
            "genres": [["drama"]] * len(rows),
            "popularity_kr": [r[3] if len(r) > 3 else 0.5 for r in rows],
            "new_this_week": [False] * len(rows),
            "vector": [np.array([_logit(r[1]), _logit(r[2])], np.float32) for r in rows],
            "bias": [0.0] * len(rows),
        }
    )


TASTE = {"me": np.array([1.0, 0.0], np.float32), "wife": np.array([0.0, 1.0], np.float32)}


def _couple(**kw):
    c = CoupleState({"me": ViewerState(), "wife": ViewerState()})
    for k, v in kw.items():
        setattr(c.viewers["me"], k, v) if k != "watched" else setattr(c, k, v)
    return c


def _warm():
    return _couple(genres=["drama"])


def test_veto_drops_movie_one_dislikes():
    out = recommend(_cat([("a", 0.9, 0.3), ("b", 0.8, 0.8)]), 0.0, TASTE, _warm())
    assert [r["movie_key"] for r in out if not r["gamble"]] == ["b"]
    assert "a" not in [r["movie_key"] for r in out if not r["gamble"]]


def test_rank_by_lower_score():
    out = recommend(_cat([("a", 0.95, 0.5), ("b", 0.8, 0.6)]), 0.0, TASTE, _warm())
    assert [r["movie_key"] for r in out] == ["b", "a"]


def test_gamble_refill_to_five():
    rows = [("s1", 0.9, 0.9), ("s2", 0.8, 0.8), ("s3", 0.7, 0.7)]
    rows += [(f"g{i}", 0.9, 0.25 + i * 0.02) for i in range(4)] + [("x", 0.9, 0.1)]
    out = recommend(_cat(rows), 0.0, TASTE, _warm())
    assert len(out) == 5
    assert [r["gamble"] for r in out] == [False] * 3 + [True] * 2
    assert "x" not in [r["movie_key"] for r in out]
    assert [r["movie_key"] for r in out[3:]] == ["g3", "g2"]


def test_never_more_than_ten():
    out = recommend(_cat([(f"m{i}", 0.9, 0.9) for i in range(30)]), 0.0, TASTE, _warm())
    assert len(out) == 10


def test_excludes_marked_and_watched():
    cat = _cat([(k, 0.9, 0.9) for k in "abcd"])
    c = _couple(liked={"a"}, disliked={"b"}, watched={"c"})
    c.viewers["me"].genres = ["drama"]
    assert [r["movie_key"] for r in recommend(cat, 0.0, TASTE, c)] == ["d"]


def test_rank_with_empty_viewer_uses_popularity():
    cat = _cat([("a", 0.9, 0.9, 0.2), ("b", 0.5, 0.5, 0.9), ("c", 0.7, 0.7, 0.5)])
    out = recommend(cat, 0.0, {"me": None, "wife": None}, _couple())
    assert [r["movie_key"] for r in out] == ["b", "c", "a"]
    assert out[0]["reason"] == "드라마 장르에서 한국 인기작이에요"
    assert 0 < out[0]["p_me"] < 1


def test_reason_prefers_shared_like():
    cat = _cat([("cand", 0.9, 0.9), ("liked", 0.9, 0.9)])
    c = CoupleState({"me": ViewerState(liked={"liked"}), "wife": ViewerState(liked={"liked"})})
    out = recommend(cat, 0.0, TASTE, c)
    assert out[0]["reason"] == "둘 다 좋아한 'Tliked'과 비슷해요"
    c.viewers["wife"].liked = set()
    c.viewers["wife"].genres = ["drama"]
    assert recommend(cat, 0.0, TASTE, c)[0]["reason"] == "나이(가) 좋아한 'Tliked'과 비슷해요"
    assert out[0]["services"] == ["Netflix"]
