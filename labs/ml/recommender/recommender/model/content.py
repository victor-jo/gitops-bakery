# Ridge model that places movies lacking MovieLens data into the MF item space
from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import HashingVectorizer, TfidfTransformer
from sklearn.linear_model import Ridge

from recommender.genres import CANONICAL

_GENRE_INDEX = {g: i for i, g in enumerate(CANONICAL)}
_FIRST_DECADE, _LAST_DECADE = 1900, 2020
N_DECADES = (_LAST_DECADE - _FIRST_DECADE) // 10 + 2  # last slot is "unknown"


def genre_decade_features(catalog: pd.DataFrame) -> sp.csr_matrix:
    """Genre multi-hot, then decade one-hot (1900s to 2020s, last column for an unknown year), per row."""
    n = len(catalog)
    genre = np.zeros((n, len(CANONICAL)), dtype=np.float32)
    for r, genres in enumerate(catalog["genres"]):
        for g in genres:
            if g in _GENRE_INDEX:
                genre[r, _GENRE_INDEX[g]] = 1.0
    decade = np.zeros((n, N_DECADES), dtype=np.float32)
    for r, year in enumerate(catalog["release_year"]):
        if pd.isna(year):
            decade[r, -1] = 1.0
        else:
            d = min(max(int(year) // 10 * 10, _FIRST_DECADE), _LAST_DECADE)
            decade[r, (d - _FIRST_DECADE) // 10] = 1.0
    return sp.csr_matrix(np.hstack([genre, decade]))


def _text(value) -> str:
    """A plain string, or '' for None, NaN, pd.NA and any other non-string."""
    return value if isinstance(value, str) else ""


def _texts(catalog: pd.DataFrame) -> list[str]:
    return [
        f"{_text(t)} {_text(d)} {' '.join(a) if isinstance(a, (list, np.ndarray)) else ''}"
        for t, d, a in zip(catalog["title"], catalog["description"], catalog["actors"])
    ]


class ContentModel:
    """Predicts MF vectors and biases from genres, decade and text; keeps MF values for matched rows."""

    def __init__(self, hasher, tfidf, ridge, movielens_to_idx, item_vecs, item_bias):
        self.hasher = hasher
        self.tfidf = tfidf
        self.ridge = ridge
        self.movielens_to_idx = movielens_to_idx
        self.item_vecs = item_vecs
        self.item_bias = item_bias

    def _features(self, catalog: pd.DataFrame) -> sp.csr_matrix:
        text = self.tfidf.transform(self.hasher.transform(_texts(catalog)))
        return sp.hstack([genre_decade_features(catalog), text]).tocsr()

    def place(self, catalog: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
        pred = self.ridge.predict(self._features(catalog))
        vecs = pred[:, :-1].astype(np.float32)
        bias = pred[:, -1].astype(np.float32)
        for r, ml_id in enumerate(catalog["movielens_id"]):
            if pd.isna(ml_id):
                continue
            idx = self.movielens_to_idx.get(int(ml_id))
            if idx is not None:
                vecs[r] = self.item_vecs[idx]
                bias[r] = self.item_bias[idx]
        return vecs, bias


def fit_content_model(
    catalog: pd.DataFrame,
    item_vecs: np.ndarray,
    item_bias: np.ndarray,
    movielens_to_idx: dict[int, int],
) -> ContentModel:
    """Fit a Ridge from content features to the MF item space using movies that have MovieLens data."""
    rows, idxs = [], []
    for r, ml_id in enumerate(catalog["movielens_id"]):
        if not pd.isna(ml_id) and int(ml_id) in movielens_to_idx:
            rows.append(r)
            idxs.append(movielens_to_idx[int(ml_id)])
    if len(rows) < 2:
        raise ValueError(f"need at least 2 catalog movies matched to MovieLens, got {len(rows)}")
    hasher = HashingVectorizer(analyzer="char_wb", ngram_range=(2, 3), n_features=2**16,
                               alternate_sign=False, norm=None)
    tfidf = TfidfTransformer()
    matched = catalog.iloc[rows]
    tfidf.fit(hasher.transform(_texts(matched)))
    model = ContentModel(hasher, tfidf, Ridge(alpha=1.0), movielens_to_idx, item_vecs, item_bias)
    target = np.hstack([item_vecs[idxs], item_bias[idxs][:, None]])
    model.ridge.fit(model._features(matched), target)
    return model
