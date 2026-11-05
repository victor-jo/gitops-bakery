# Turns MovieLens ratings and the couple's feedback into dense-indexed binary training rows
import hashlib

import numpy as np
import pandas as pd
from sklearn.model_selection import train_test_split

from recommender.config import LIKE_RATING

COUPLE_COLUMNS = ["viewer", "movie_key", "movielens_id", "liked"]
# Share of the couple's marks held out for the gate, chosen per mark by a stable hash
COUPLE_HOLDOUT_PERCENT = 20


def load_couple_feedback(events: list[dict], catalog: pd.DataFrame) -> pd.DataFrame:
    """Latest mark per (viewer, movie) mapped to MovieLens ids; unmapped movies are dropped."""
    marks = [e for e in events if e.get("kind") == "mark"]
    if not marks:
        return pd.DataFrame({"viewer": pd.Series(dtype=object),
                             "movie_key": pd.Series(dtype=object),
                             "movielens_id": pd.Series(dtype="Int64"),
                             "liked": pd.Series(dtype=bool)})
    df = pd.DataFrame(marks).sort_values("at", kind="stable")
    df = df.drop_duplicates(["viewer", "movie_key"], keep="last")
    ids = catalog.dropna(subset=["movielens_id"]).drop_duplicates("movie_key")
    ids = ids.set_index("movie_key")["movielens_id"]
    df["movielens_id"] = df["movie_key"].map(ids)
    df = df.dropna(subset=["movielens_id"])
    out = df[COUPLE_COLUMNS].copy()
    out["movielens_id"] = out["movielens_id"].astype("Int64")
    out["liked"] = out["liked"].astype(bool)
    return out.reset_index(drop=True)


def load_movielens(
    ratings: pd.DataFrame, couple: pd.DataFrame
) -> tuple[pd.DataFrame, dict[str, int], dict[int, int]]:
    """Return rows (user_idx, item_idx, label), the me/wife user index and the movieId -> item_idx map."""
    user_codes, users = pd.factorize(ratings["userId"], sort=True)
    item_codes, items = pd.factorize(ratings["movieId"], sort=True)
    item_index = {int(m): i for i, m in enumerate(items)}
    rows = pd.DataFrame({
        "user_idx": user_codes.astype("int32"),
        "item_idx": item_codes.astype("int32"),
        "label": (ratings["rating"].to_numpy() >= LIKE_RATING).astype("float32"),
    })
    n = len(users)
    user_index = {"me": n, "wife": n + 1}

    if len(couple):
        rows = pd.concat([rows, couple_rows(couple, user_index, item_index)], ignore_index=True)
    return rows, user_index, item_index


def couple_rows(couple: pd.DataFrame, user_index: dict[str, int], item_index: dict[int, int]) -> pd.DataFrame:
    """The couple's marks as (user_idx, item_idx, label) rows; movies MovieLens does not know are dropped."""
    known = couple[couple["movielens_id"].astype("Int64").isin(list(item_index))]
    return pd.DataFrame({
        "user_idx": known["viewer"].map(user_index).astype("int32"),
        "item_idx": known["movielens_id"].astype("int64").map(item_index).astype("int32"),
        "label": known["liked"].astype("float32"),
    }).reset_index(drop=True)


def split(df: pd.DataFrame, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """75/15/10 train/val/test split, as in the reference project."""
    train, rest = train_test_split(df, test_size=0.25, random_state=seed)
    val, test = train_test_split(rest, test_size=0.4, random_state=seed)
    return train, val, test


def _held_out(viewer: str, movie_key: str) -> bool:
    digest = hashlib.sha1(f"{viewer}|{movie_key}".encode()).digest()
    return int.from_bytes(digest[:8], "big") % 100 < COUPLE_HOLDOUT_PERCENT


def split_couple(couple: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split the couple's marks into training and holdout by a hash of viewer|movie_key.

    A mark keeps its side across runs as new marks arrive, so a holdout mark never sits in an
    earlier champion's training rows.
    """
    held = np.fromiter((_held_out(v, k) for v, k in zip(couple["viewer"], couple["movie_key"])),
                       dtype=bool, count=len(couple))
    return couple[~held].reset_index(drop=True), couple[held].reset_index(drop=True)


def split_all(
    df: pd.DataFrame, user_index: dict[str, int], seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split MovieLens rows 75/15/10; the couple's rows (already split by split_couple) all join train."""
    is_couple = df["user_idx"].isin(list(user_index.values())).to_numpy()
    train, val, test = split(df[~is_couple], seed)
    return pd.concat([train, df[is_couple]], ignore_index=True), val, test
