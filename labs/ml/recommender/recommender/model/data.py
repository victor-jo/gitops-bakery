# Turns MovieLens ratings and the couple's feedback into dense-indexed binary training rows
import pandas as pd
from sklearn.model_selection import train_test_split

from recommender.config import LIKE_RATING

COUPLE_COLUMNS = ["viewer", "movielens_id", "liked"]


def load_couple_feedback(events: list[dict], catalog: pd.DataFrame) -> pd.DataFrame:
    """Latest mark per (viewer, movie) mapped to MovieLens ids; unmapped movies are dropped."""
    marks = [e for e in events if e.get("kind") == "mark"]
    if not marks:
        return pd.DataFrame({"viewer": pd.Series(dtype=object),
                             "movielens_id": pd.Series(dtype="Int64"),
                             "liked": pd.Series(dtype=bool)})
    df = pd.DataFrame(marks).sort_values("at", kind="stable")
    df = df.drop_duplicates(["viewer", "movie_key"], keep="last")
    ids = catalog.dropna(subset=["movielens_id"]).drop_duplicates("movie_key")
    ids = ids.set_index("movie_key")["movielens_id"]
    df["movielens_id"] = df["movie_key"].map(ids)
    df = df.dropna(subset=["movielens_id"])
    out = df[["viewer", "movielens_id", "liked"]].copy()
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
        known = couple[couple["movielens_id"].astype("Int64").isin(list(item_index))]
        extra = pd.DataFrame({
            "user_idx": known["viewer"].map(user_index).astype("int32"),
            "item_idx": known["movielens_id"].astype("int64").map(item_index).astype("int32"),
            "label": known["liked"].astype("float32"),
        })
        rows = pd.concat([rows, extra], ignore_index=True)
    return rows, user_index, item_index


def split(df: pd.DataFrame, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """75/15/10 train/val/test split, as in the reference project."""
    train, rest = train_test_split(df, test_size=0.25, random_state=seed)
    val, test = train_test_split(rest, test_size=0.4, random_state=seed)
    return train, val, test


def split_couple(rows: pd.DataFrame, seed: int = 42) -> tuple[pd.DataFrame, pd.DataFrame]:
    """80/20 split of the couple's own rows into training rows and a holdout kept for evaluation."""
    return train_test_split(rows, test_size=0.2, random_state=seed)


def split_all(
    df: pd.DataFrame, user_index: dict[str, int], seed: int = 42
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split MovieLens rows 75/15/10 and the couple's rows 80/20; the couple's train part joins train."""
    is_couple = df["user_idx"].isin(list(user_index.values())).to_numpy()
    train, val, test = split(df[~is_couple], seed)
    couple = df[is_couple]
    # train_test_split cannot split fewer than two rows; before any feedback there is no holdout
    if len(couple) < 2:
        return pd.concat([train, couple], ignore_index=True), val, test, couple.iloc[:0]
    couple_train, couple_holdout = split_couple(couple, seed)
    return pd.concat([train, couple_train], ignore_index=True), val, test, couple_holdout
