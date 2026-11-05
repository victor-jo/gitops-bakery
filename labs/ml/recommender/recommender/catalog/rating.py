# Combines the IMDb, TMDB and Coupang review scores of each movie into one Bayesian-averaged rating in 0..1
from __future__ import annotations

import numpy as np
import pandas as pd

# column with the score, column with its vote count (None: the source gives none), lowest and highest score
SOURCES = {
    "imdb": ("imdb_score", "imdb_votes", 1.0, 10.0),
    "tmdb": ("tmdb_score", None, 0.0, 10.0),
    "coupang": ("coupang_rating", "coupang_count", 1.0, 5.0),
}
# Votes count in units of that source's median vote count among rated movies, so IMDb's thousands and
# Coupang's handfuls weigh alike. TMDB gives no count, so its score counts as a quarter of a typical source.
TMDB_WEIGHT = 0.25
# The catalog mean counts as this many typical sources, pulling thinly rated movies toward it
PRIOR_WEIGHT = 1.0


def review_rating(df: pd.DataFrame) -> pd.Series:
    """Each movie's rating in 0..1, or NaN when no source rates it."""
    n = len(df)
    weighted, weight = np.zeros(n), np.zeros(n)
    for score_col, votes_col, lo, hi in SOURCES.values():
        if score_col not in df:
            continue
        score = pd.to_numeric(df[score_col], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
        rated = np.isfinite(score) & (score > lo if lo == 0.0 else score >= lo)  # TMDB uses 0 for "no votes"
        if votes_col is None:
            w = np.where(rated, TMDB_WEIGHT, 0.0)
        else:
            votes = (pd.to_numeric(df[votes_col], errors="coerce").to_numpy(dtype=float, na_value=np.nan)
                     if votes_col in df else np.full(n, np.nan))
            rated &= np.isfinite(votes) & (votes > 0)
            if not rated.any():
                continue
            w = np.where(rated, np.nan_to_num(votes) / np.median(votes[rated]), 0.0)
        r = np.clip((np.nan_to_num(score) - lo) / (hi - lo), 0.0, 1.0)
        weighted += w * r
        weight += w
    known = weight > 0
    out = np.full(n, np.nan)
    if known.any():
        mean = weighted[known].sum() / weight[known].sum()
        out[known] = (PRIOR_WEIGHT * mean + weighted[known]) / (PRIOR_WEIGHT + weight[known])
    return pd.Series(out, index=df.index, name="review_rating")
