# Fixed item features the hybrid MF projects into its item space: genres, decade, Korean flag, log rating count
import re

import numpy as np
import pandas as pd

from recommender.genres import from_movielens
from recommender.model.content import genre_decade_features

_TITLE_YEAR = re.compile(r"\((\d{4})\)\s*$")


def movielens_year(title) -> int | None:
    """The release year MovieLens writes at the end of a title, as in "Toy Story (1995)"."""
    found = _TITLE_YEAR.search(title) if isinstance(title, str) else None
    return int(found.group(1)) if found else None


def item_features(item_index: dict[int, int], movies: pd.DataFrame, catalog: pd.DataFrame,
                  train_rows: pd.DataFrame) -> np.ndarray:
    """One float32 row per item index: genre multi-hot, decade one-hot, Korean flag, log rating count.

    Genres and year come from MovieLens, so every item has them. MovieLens has no language, so the
    Korean flag comes from the catalog and only movies in it can carry the flag. The rating count is
    log1p of the item's training rows, standardized over items, so no held-out row is counted.
    """
    ids = np.empty(len(item_index), dtype=np.int64)
    ids[list(item_index.values())] = list(item_index)
    meta = movies.set_index("movieId").reindex(ids)
    frame = pd.DataFrame({
        "genres": [from_movielens(g) if isinstance(g, str) else [] for g in meta["genres"]],
        "release_year": pd.array([movielens_year(t) for t in meta["title"]], dtype="Int64"),
    })
    korean_ids = catalog.loc[catalog["korean"] & catalog["movielens_id"].notna(), "movielens_id"]
    korean = np.isin(ids, korean_ids.astype(np.int64).to_numpy()).astype(np.float32)
    log_count = np.log1p(np.bincount(train_rows["item_idx"].to_numpy(), minlength=len(ids)))
    spread = log_count.std()
    popularity = (log_count - log_count.mean()) / spread if spread > 0 else np.zeros(len(ids))
    return np.hstack([genre_decade_features(frame).toarray(), korean[:, None],
                      popularity[:, None]]).astype(np.float32)
