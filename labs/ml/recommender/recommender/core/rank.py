# Couple-level ranking: per-viewer like probability, veto, gamble refill and reasons
from __future__ import annotations

import numpy as np
import pandas as pd

from datetime import datetime, timedelta, timezone

from recommender.config import (MAX_RESULTS, MIN_RESULTS, RECENCY_BONUS, RECENCY_YEARS, SERVICES,
                                STRONG_DISLIKE_P, VETO_P, VIEWERS)
from recommender.core.state import CoupleState
from recommender.genres import KOREAN_LABEL

_COS_FLOOR = 0.7
# A liked movie less similar than this is not named as the reason; the genre copy is used instead
_REASON_MIN_COS = 0.3
_SUBJECT = {"me": "내가", "wife": "아내가"}
# Digits whose Korean reading ends in a final consonant: 영 일 삼 육 칠 팔
_DIGITS_WITH_FINAL = set("013678")


def and_particle(title: str) -> str:
    """과 or 와 for the title, chosen by whether its last sound ends in a consonant; 와(과) when unknown."""
    c = title[-1:]
    if "가" <= c <= "힣":
        return "과" if (ord(c) - 0xAC00) % 28 else "와"
    if c.isdigit():
        return "과" if c in _DIGITS_WITH_FINAL else "와"
    return "와(과)"


def this_year_kst() -> int:
    return datetime.now(timezone(timedelta(hours=9))).year


def recency(release_year, this_year: int) -> np.ndarray:
    """1.0 for this year's movies, fading linearly to 0 at RECENCY_YEARS old; 0 when the year is unknown."""
    years = pd.array(release_year, dtype="Int64")
    age = (this_year - years).to_numpy(dtype="float64", na_value=np.inf)
    return np.clip(1.0 - age / RECENCY_YEARS, 0.0, 1.0)


def _unit(m: np.ndarray) -> np.ndarray:
    n = np.linalg.norm(m, axis=-1, keepdims=True)
    return m / np.maximum(n, 1e-9)


def _sigmoid(x: np.ndarray) -> np.ndarray:
    # Stable form: exp is only ever taken of non-positive values.
    e = np.exp(-np.abs(x))
    return np.where(x >= 0, 1.0 / (1.0 + e), e / (1.0 + e))


def recommend(
    catalog: pd.DataFrame, global_bias: float, taste: dict[str, np.ndarray | None], couple: CoupleState,
    this_year: int | None = None,
) -> list[dict]:
    n = len(catalog)
    if n == 0:
        return []
    keys = catalog["movie_key"].to_numpy()
    vecs = np.stack(catalog["vector"].to_numpy()).astype(np.float32)
    unit = _unit(vecs)
    base = catalog["bias"].to_numpy(dtype=np.float32) + np.float32(global_bias)
    genres = catalog["genres"].tolist()
    key_row = {k: i for i, k in enumerate(keys)}

    exclude = set(couple.watched)
    for vs in couple.viewers.values():
        exclude |= vs.liked | vs.disliked
    eligible = ~np.isin(keys, list(exclude)) if exclude else np.ones(n, dtype=bool)

    probs: dict[str, np.ndarray] = {}
    has_taste: dict[str, bool] = {}
    for vid in VIEWERS:
        vs = couple.viewers[vid]
        u = taste.get(vid)
        has_taste[vid] = u is not None
        logit = base.copy()
        if u is not None:
            logit += vecs @ np.asarray(u, dtype=np.float32)
        if vs.genres:
            chosen = set(vs.genres)
            logit += 0.3 * np.fromiter((not chosen.isdisjoint(g) for g in genres), dtype=np.float32, count=n)
        dis = [key_row[k] for k in vs.disliked if k in key_row]
        if dis:
            cos = (unit @ unit[dis].T).max(axis=1)
            logit -= np.maximum(0.0, cos - _COS_FLOOR) / (1.0 - _COS_FLOOR)
        probs[vid] = _sigmoid(logit.astype(np.float64))

    low = np.minimum(probs["me"], probs["wife"])
    cold = not any(vs.liked or vs.disliked or vs.genres for vs in couple.viewers.values())
    score = catalog["popularity_kr"].to_numpy(dtype=np.float64) if cold else low
    if "release_year" in catalog:
        # Recent releases move up the list, weighted by how much they are watched in Korea so that a
        # recent hit outranks an obscure new title; the veto below still uses the raw probabilities
        popularity = catalog["popularity_kr"].to_numpy(dtype=np.float64)
        score = score + RECENCY_BONUS * recency(catalog["release_year"], this_year or this_year_kst()) * popularity

    # Once anyone has given feedback the veto binds both viewers; in cold mode only known tastes veto.
    veto = np.zeros(n, dtype=bool)
    for vid in VIEWERS:
        if has_taste[vid] or not cold:
            veto |= probs[vid] < VETO_P
    survivors = np.flatnonzero(eligible & ~veto)
    survivors = survivors[np.argsort(-score[survivors], kind="stable")][:MAX_RESULTS]
    picked = [(int(i), False) for i in survivors]

    if len(picked) < MIN_RESULTS:
        floor = np.ones(n, dtype=bool)
        for vid in VIEWERS:
            if has_taste[vid] or not cold:
                floor &= probs[vid] >= STRONG_DISLIKE_P
        gamble_mask = eligible & veto & floor
        pool = np.flatnonzero(gamble_mask)
        pool = pool[np.argsort(-score[pool], kind="stable")][: MIN_RESULTS - len(picked)]
        picked += [(int(i), True) for i in pool]

    return [
        _entry(catalog, i, g, probs, unit, key_row, couple, genres[i]) for i, g in picked
    ]


def _nearest(unit: np.ndarray, row: int, liked_keys, key_row: dict) -> int | None:
    """The most similar liked movie, or None when none is at least _REASON_MIN_COS similar."""
    rows = [key_row[k] for k in liked_keys if k in key_row]
    if not rows:
        return None
    cos = unit[rows] @ unit[row]
    best = int(np.argmax(cos))
    return rows[best] if cos[best] >= _REASON_MIN_COS else None


def _entry(catalog, i, gamble, probs, unit, key_row, couple, cand_genres) -> dict:
    row = catalog.iloc[i]
    p_me, p_wife = float(probs["me"][i]), float(probs["wife"][i])
    pv = {"me": p_me, "wife": p_wife}
    reason = None
    both = couple.viewers["me"].liked & couple.viewers["wife"].liked
    near = _nearest(unit, i, both, key_row)
    if near is not None:
        title = catalog.iloc[near]["title"]
        reason = f"둘 다 좋아한 '{title}'{and_particle(title)} 비슷해요"
    else:
        for vid in sorted(VIEWERS, key=lambda v: -pv[v]):
            near = _nearest(unit, i, couple.viewers[vid].liked, key_row)
            if near is not None:
                title = catalog.iloc[near]["title"]
                reason = f"{_SUBJECT[vid]} 좋아한 '{title}'{and_particle(title)} 비슷해요"
                break
    if reason is None:
        chosen = set(couple.viewers["me"].genres) | set(couple.viewers["wife"].genres)
        gid = next((g for g in cand_genres if g in chosen), cand_genres[0] if len(cand_genres) else None)
        label = KOREAN_LABEL.get(gid, gid) if gid else "인기"
        reason = f"{label} 장르에서 한국 인기작이에요"
    return {
        "movie_key": row["movie_key"],
        "title": row["title"],
        "poster_url": row["poster_url"],
        "services": [SERVICES.get(c, c) for c in row["services"]],
        "new_this_week": bool(row["new_this_week"]),
        "p_me": p_me,
        "p_wife": p_wife,
        "gamble": gamble,
        "reason": reason,
    }
