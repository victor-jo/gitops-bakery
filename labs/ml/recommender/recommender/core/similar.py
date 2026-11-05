# Content similarity between catalog movies: genres plus character n-grams of title, description and actors
from __future__ import annotations

import numpy as np
import pandas as pd
import scipy.sparse as sp
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.preprocessing import normalize

from recommender.genres import CANONICAL

_GENRE_INDEX = {g: i for i, g in enumerate(CANONICAL)}


def _text(value) -> str:
    return value if isinstance(value, str) else ""


def _texts(df: pd.DataFrame) -> list[str]:
    n = len(df)
    titles = df["title"] if "title" in df else [""] * n
    descriptions = df["description"] if "description" in df else [""] * n
    actors = df["actors"] if "actors" in df else [None] * n
    return [f"{_text(t)} {_text(d)} {' '.join(a) if isinstance(a, (list, np.ndarray)) else ''}"
            for t, d, a in zip(titles, descriptions, actors)]


def content_matrix(df: pd.DataFrame) -> sp.csr_matrix:
    """One unit row per movie: its genres and its text weigh the same, so a dot product is their cosine.

    The taste vectors cannot serve here: nearly all their variance lies on one axis, so by their cosine
    thousands of unrelated movies look identical.
    """
    n = len(df)
    genre = sp.lil_matrix((n, len(CANONICAL)), dtype=np.float64)
    for r, genres in enumerate(df["genres"]):
        for g in genres:
            if g in _GENRE_INDEX:
                genre[r, _GENRE_INDEX[g]] = 1.0
    text = TfidfVectorizer(analyzer="char_wb", ngram_range=(2, 3), sublinear_tf=True).fit_transform(_texts(df))
    # A character n-gram seen in only one movie links it to nothing, so it is left out when any are shared
    shared = np.asarray((text > 0).sum(axis=0)).ravel() >= 2
    if shared.any():
        text = normalize(text[:, shared])
    return normalize(sp.hstack([normalize(genre.tocsr()), text]).tocsr())


def similarity_to(content: sp.csr_matrix, row: int) -> np.ndarray:
    """Cosine of every movie to the movie at `row`."""
    return np.asarray((content @ content[row].T).todense(), dtype=np.float64).ravel()
