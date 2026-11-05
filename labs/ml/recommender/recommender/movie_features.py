# Object keys, columns, writers and the joined reader of the three movie feature parquets Feast serves
"""The catalog run writes the catalog and popularity parquets; the training run writes the embedding one.

Each parquet backs one Feast feature view of the same name in feature_repo/features.py. Readers join the three
back into one frame per movie. Until both runs have written their parquets once, readers fall back to the
single features/movies.parquet that earlier versions wrote.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from recommender import s3

PREFIX = "features/"
CATALOG = "movie_catalog"
POPULARITY = "movie_popularity"
EMBEDDING = "movie_embedding"
COLUMNS = {
    # description and actors feed the content similarity behind the liked-movie tabs
    CATALOG: ["title", "services", "genres", "release_year", "korean", "new_this_week", "poster_url", "description",
              "actors", "review_rating"],
    POPULARITY: ["popularity_kr"],
    EMBEDDING: ["vector", "bias", "model_version"],
}
LEGACY = f"{PREFIX}movies.parquet"

log = logging.getLogger(__name__)


def key(view: str) -> str:
    """Object key in the recommender bucket of the parquet behind a movie feature view."""
    return f"{PREFIX}{view}.parquet"


def _frame(df: pd.DataFrame, view: str, at: pd.Timestamp) -> pd.DataFrame:
    # Feast's file source needs a timestamp column; every row of one write shares it
    return df[["movie_key", *COLUMNS[view]]].assign(event_timestamp=at).reset_index(drop=True)


def catalog_frames(catalog: pd.DataFrame, at: pd.Timestamp) -> dict[str, pd.DataFrame]:
    """The parquets the catalog run owns, keyed by object key, from today's built catalog."""
    return {key(view): _frame(catalog, view, at) for view in (CATALOG, POPULARITY)}


def embedding_frame(catalog: pd.DataFrame, vecs: np.ndarray, bias: np.ndarray, model_version: str,
                    at: pd.Timestamp) -> pd.DataFrame:
    """The parquet the training run owns: each catalog movie placed by one champion version."""
    placed = pd.DataFrame({"movie_key": catalog["movie_key"].to_numpy(), "vector": list(vecs),
                           "bias": np.asarray(bias, dtype=float), "model_version": str(model_version)})
    return _frame(placed, EMBEDDING, at)


def join(catalog: pd.DataFrame, popularity: pd.DataFrame, embedding: pd.DataFrame) -> pd.DataFrame:
    """One row per catalog movie the champion has placed, in catalog order.

    Movies without a vector cannot be scored, so they wait for the next training run; departed movies whose
    vector is still in the embedding parquet drop out with the catalog.
    """
    cols = {view: ["movie_key", *COLUMNS[view]] for view in COLUMNS}
    out = (catalog[cols[CATALOG]]
           .merge(popularity[cols[POPULARITY]], on="movie_key", how="left")
           .merge(embedding[cols[EMBEDDING]], on="movie_key", how="inner"))
    # A crash between the two catalog-run writes can leave a movie without its popularity
    out["popularity_kr"] = out["popularity_kr"].fillna(0.0)
    unplaced = len(catalog) - len(out)
    if unplaced:
        log.info("%d catalog movies have no vector yet and wait for the next training run", unplaced)
    return out


def load() -> tuple[pd.DataFrame, list[str]]:
    """The movie frame readers score with, and the feature views it came from.

    Returns the legacy features/movies.parquet and no views while any of the three parquets is missing.
    """
    keys = set(s3.list_keys(PREFIX))
    missing = [key(view) for view in COLUMNS if key(view) not in keys]
    if not missing:
        frames = [s3.read_parquet(key(view)) for view in (CATALOG, POPULARITY, EMBEDDING)]
        return join(*frames), list(COLUMNS)
    log.warning("missing %s; reading the legacy %s until the catalog and training runs write them",
                ", ".join(missing), LEGACY)
    return s3.read_parquet(LEGACY), []
