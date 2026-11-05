# Tests for couple ranking, veto, newest-first picks, the popular fallback, paging and reasons
import numpy as np
import pandas as pd

import pytest

from recommender.core.rank import and_particle, recommend
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
    assert [r["movie_key"] for r in out if r["source"] == "pick"] == ["b"]
    assert all(r["source"] == "popular" for r in out if r["movie_key"] == "a")
    out = recommend(_cat([("z", 0.9, 0.1), ("b", 0.8, 0.8)]), 0.0, TASTE, _warm())
    assert [r["movie_key"] for r in out] == ["b"]


def test_rank_by_lower_score():
    out = recommend(_cat([("a", 0.95, 0.5), ("b", 0.8, 0.6)]), 0.0, TASTE, _warm())
    assert [r["movie_key"] for r in out] == ["b", "a"]


def test_popular_fallback_follows_the_picks_by_popularity_and_drops_strong_dislikes():
    rows = [("s1", 0.9, 0.9, 0.1), ("s2", 0.8, 0.8, 0.2), ("s3", 0.7, 0.7, 0.3)]
    rows += [(f"g{i}", 0.9, 0.25 + i * 0.02, 0.4 + i * 0.1) for i in range(4)] + [("x", 0.9, 0.1, 1.0)]
    out = recommend(_cat(rows), 0.0, TASTE, _warm())
    assert [r["source"] for r in out] == ["pick"] * 3 + ["popular"] * 4
    # Picks keep their score order; the fallback goes by Korean popularity, not by score
    assert [r["movie_key"] for r in out] == ["s1", "s2", "s3", "g3", "g2", "g1", "g0"]
    assert "x" not in [r["movie_key"] for r in out]  # 0.1 is below STRONG_DISLIKE_P, even as a popular movie


def test_pages_are_slices_of_one_list_across_the_fallback_boundary():
    rows = [(f"p{i}", 0.9, 0.9) for i in range(5)] + [(f"v{i}", 0.9, 0.3, 0.9 - i * 0.1) for i in range(4)]
    cat, c = _cat(rows), _warm()
    full = [r["movie_key"] for r in recommend(cat, 0.0, TASTE, c)]
    assert len(full) == 9
    pages = [[r["movie_key"] for r in recommend(cat, 0.0, TASTE, c, offset=o, limit=4)] for o in (0, 4, 8, 12)]
    assert pages[0] + pages[1] + pages[2] == full
    assert [len(p) for p in pages] == [4, 4, 1, 0]
    assert [r["source"] for r in recommend(cat, 0.0, TASTE, c, offset=4, limit=2)] == ["pick", "popular"]


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
    assert out[0]["reason"] == "둘 다 좋아한 'Tliked'와(과) 비슷해요"
    c.viewers["wife"].liked = set()
    c.viewers["wife"].genres = ["drama"]
    assert recommend(cat, 0.0, TASTE, c)[0]["reason"] == "내가 좋아한 'Tliked'와(과) 비슷해요"
    c.viewers["me"].liked, c.viewers["wife"].liked = set(), {"liked"}
    cat["title"] = ["후보", "기생충"]
    assert recommend(cat, 0.0, TASTE, c)[0]["reason"] == "아내가 좋아한 '기생충'과 비슷해요"
    assert out[0]["services"] == ["Netflix"]


def test_veto_applies_to_viewer_without_taste():
    # wife has no taste, so p_wife = sigmoid(bias + global): 0.1 < 0.20 is absent even as a gamble.
    cat = _cat([("a", 0.9, 0.9), ("b", 0.9, 0.9)])
    cat["bias"] = [_logit(0.1), _logit(0.5)]
    cat["vector"] = [np.array([_logit(0.9), 0], np.float32)] * 2
    cat["bias"] = [_logit(0.1), 0.0]
    out = recommend(cat, 0.0, {"me": np.array([1.0, 0.0], np.float32), "wife": None}, _warm())
    assert [r["movie_key"] for r in out if r["movie_key"] == "a"] == []


def test_dislike_penalty_vetoes_near_neighbour():
    cat = _cat([("bad", 0.9, 0.9), ("near", 0.9, 0.9), ("far", 0.9, 0.9)])
    cat["vector"] = [
        np.array([0.2, 0.0], np.float32),
        np.array([0.2, 0.001], np.float32),
        np.array([0.0, 3.0], np.float32),
    ]
    taste = {"me": np.array([1.0, 0.0], np.float32), "wife": np.array([1.0, 0.0], np.float32)}
    c = _couple(disliked={"bad"})
    out = recommend(cat, 0.0, taste, c)
    near = [r for r in out if r["movie_key"] == "near"]
    assert near and near[0]["source"] == "popular" and near[0]["p_me"] < 0.35
    assert [r for r in out if r["movie_key"] == "far"][0]["source"] == "pick"


def test_genre_bonus_moves_movie_up():
    cat = _cat([("a", 0.6, 0.6), ("b", 0.6, 0.6)])
    cat["genres"] = [["drama"], ["comedy"]]
    c = _couple(genres=["comedy"])
    c.viewers["wife"].genres = ["comedy"]
    out = recommend(cat, 0.0, TASTE, c)
    assert [r["movie_key"] for r in out] == ["b", "a"]
    assert out[0]["p_me"] > out[1]["p_me"]


def test_mark_without_liked_is_ignored():
    from datetime import datetime, timezone
    from recommender.core.state import Event, replay

    s = replay([Event("mark", "me", "a", None, None, datetime(2026, 1, 1, tzinfo=timezone.utc))])
    assert not s.viewers["me"].liked and not s.viewers["me"].disliked


@pytest.mark.parametrize("title,particle", [
    ("모아나", "와"), ("기생충", "과"), ("Up", "와(과)"), ("2012", "와"), ("1987", "과"), ("", "와(과)"),
])
def test_and_particle(title, particle):
    assert and_particle(title) == particle


def test_reason_falls_back_to_genre_when_the_liked_movie_is_not_similar():
    cat = _cat([("cand", 0.9, 0.9), ("liked", 0.9, 0.9)])
    # Orthogonal vectors: cosine 0 is below the floor, so naming 'liked' would mislead
    cat["vector"] = [np.array([2.0, 0.0], np.float32), np.array([0.0, 2.0], np.float32)]
    c = CoupleState({"me": ViewerState(liked={"liked"}), "wife": ViewerState(liked={"liked"})})
    taste = {"me": np.array([1.0, 1.0], np.float32), "wife": np.array([1.0, 1.0], np.float32)}
    out = recommend(cat, 0.0, taste, c)
    assert out[0]["movie_key"] == "cand"
    assert out[0]["reason"] == "드라마 장르에서 한국 인기작이에요"


def test_recency_bonus_lifts_recent_movies_without_weakening_the_veto():
    cat = _cat([("old", 0.80, 0.80), ("new", 0.72, 0.72), ("bad_new", 0.90, 0.30)])
    cat["release_year"] = pd.array([1995, 2026, 2026], dtype="Int64")
    out = recommend(cat, 0.0, TASTE, _warm(), this_year=2026)
    assert [r["movie_key"] for r in out if r["source"] == "pick"] == ["new", "old"]
    # Recency only orders the picks; a movie one viewer dislikes is still never a pick
    assert all(r["source"] == "popular" for r in out if r["movie_key"] == "bad_new")


def test_recency_fades_over_five_years_and_ignores_missing_years():
    from recommender.core.rank import recency

    years = pd.array([2026, 2025, 2021, 1990, None], dtype="Int64")
    assert recency(years, 2026).tolist() == pytest.approx([1.0, 0.8, 0.0, 0.0, 0.0])


def test_recency_bonus_favours_recent_movies_people_actually_watch():
    # Same year and predicted taste: the popular one gets the full bonus, the obscure one almost none
    cat = _cat([("obscure", 0.70, 0.70, 0.05), ("old", 0.75, 0.75, 0.9), ("hit", 0.70, 0.70, 1.0)])
    cat["release_year"] = pd.array([2026, 2000, 2026], dtype="Int64")
    out = recommend(cat, 0.0, TASTE, _warm(), this_year=2026)
    assert [r["movie_key"] for r in out] == ["hit", "obscure", "old"]


def test_picks_go_newest_year_first_then_by_score_with_unknown_years_last():
    cat = _cat([("y20_lo", 0.6, 0.6), ("none", 0.95, 0.95), ("y24", 0.5, 0.5), ("y20_hi", 0.9, 0.9)])
    cat["release_year"] = pd.array([2020, None, 2024, 2020], dtype="Int64")
    out = recommend(cat, 0.0, TASTE, _warm(), this_year=2026)
    assert [r["movie_key"] for r in out] == ["y24", "y20_hi", "y20_lo", "none"]


def test_korean_bonus_moves_korean_movies_up_without_weakening_the_veto():
    cat = _cat([("foreign", 0.80, 0.80), ("korean", 0.74, 0.74), ("korean_bad", 0.90, 0.30)])
    cat["korean"] = [False, True, True]
    out = recommend(cat, 0.0, TASTE, _warm())
    assert [r["movie_key"] for r in out if r["source"] == "pick"] == ["korean", "foreign"]
    assert all(r["source"] == "popular" for r in out if r["movie_key"] == "korean_bad")


def test_a_like_filter_orders_by_similarity_then_year_and_keeps_the_exclusions():
    rows = [("hi", 0.9, 0.9), ("tie_old", 0.9, 0.9), ("tie_new", 0.9, 0.9), ("low", 0.9, 0.9),
            ("vetoed", 0.9, 0.3), ("watched", 0.9, 0.9)]
    cat = _cat(rows)
    cat["release_year"] = pd.array([2001, 2002, 2020, 2026, 2026, 2026], dtype="Int64")
    sim = np.array([0.9, 0.801, 0.799, 0.29, 0.95, 0.95])
    c = _warm()
    c.watched = {"watched"}
    out = recommend(cat, 0.0, TASTE, c, this_year=2026, similarity=sim)
    # 0.801 and 0.799 are both 80%, so the newer one goes first; 0.29 is below the minimum
    assert [r["movie_key"] for r in out] == ["hi", "tie_new", "tie_old"]
    assert [r["source"] for r in out] == ["similar"] * 3  # no popular fallback, so the vetoed one never shows
    assert out[0]["similarity"] == pytest.approx(0.9)
    page = recommend(cat, 0.0, TASTE, c, this_year=2026, similarity=sim, offset=1, limit=5)
    assert [r["movie_key"] for r in page] == ["tie_new", "tie_old"]


def test_review_rating_reorders_within_a_year_only_and_leaves_unrated_movies_neutral():
    cat = _cat([("plain", 0.80, 0.80), ("loved", 0.78, 0.78), ("unrated", 0.79, 0.79), ("old_loved", 0.9, 0.9),
                ("bad_loved", 0.9, 0.3)])
    cat["release_year"] = pd.array([2026, 2026, 2026, 2010, 2026], dtype="Int64")
    cat["review_rating"] = [0.5, 0.9, None, 1.0, 1.0]
    out = recommend(cat, 0.0, TASTE, _warm(), this_year=2026)
    picks = [r["movie_key"] for r in out if r["source"] == "pick"]
    # loved jumps plain within 2026; unrated keeps its taste place between them; 2010 stays after 2026
    assert picks == ["loved", "unrated", "plain", "old_loved"]
    assert [r["movie_key"] for r in out if r["source"] == "popular"] == ["bad_loved"]  # the veto ignores reviews
