# Matches Coupang titles to TMDB ids and merges the three services into one movie catalog
from collections.abc import Callable
from datetime import date, timedelta

import pandas as pd


def _tmdb(value) -> str | None:
    """Normalize a tmdb id (str, int or float, possibly NaN) to a plain string without '.0'."""
    if value is None or pd.isna(value):
        return None
    text = str(value).strip()
    if text.endswith(".0"):
        text = text[:-2]
    return text or None


def _year(value) -> int | None:
    return None if value is None or pd.isna(value) else int(value)


def match_coupang(coupang: pd.DataFrame, search: Callable[[str, int | None], str | None],
                  known: dict[str, str | None]) -> pd.DataFrame:
    """Add tmdb_id to Coupang rows; `known` caches every searched coupang_id, misses as None."""
    for cid, title, hint in zip(coupang.coupang_id, coupang.title, coupang.year_hint):
        if cid not in known:
            known[cid] = _tmdb(search(title, _year(hint)))
    out = coupang.copy()
    out["tmdb_id"] = [known[c] for c in out.coupang_id]
    return out


def _pct_by_rank(rank: pd.Series) -> pd.Series:
    return 1 - (rank - 1) / len(rank)


def _pct_by_count(count: pd.Series) -> pd.Series:
    count = pd.to_numeric(count, errors="coerce").fillna(0)
    pct = count.rank(method="max", pct=True)
    return pct.where(count > 0, 0.0)


def build_catalog(justwatch: pd.DataFrame, coupang: pd.DataFrame, new: pd.DataFrame,
                  links: pd.DataFrame, today: date) -> pd.DataFrame:
    """Return one row per movie across Netflix, Disney+ and Coupang Play.

    Rows are keyed by tmdb id; a JustWatch title without one is keyed `jw:<id>`
    and an unmatched Coupang title `cp:<coupang_id>`.
    """
    jw = justwatch.copy()
    jw["tmdb_id"] = jw.tmdb_id.map(_tmdb)
    jw["key"] = [f"tmdb:{t}" if t else f"jw:{j}" for t, j in zip(jw.tmdb_id, jw.justwatch_id)]
    jw["pop"] = jw.groupby("service").popularity_rank.transform(_pct_by_rank)

    cp = coupang[coupang.status == "movie"].copy() if "status" in coupang else coupang.copy()
    if "tmdb_id" not in cp:
        cp["tmdb_id"] = None
    cp["tmdb_id"] = cp.tmdb_id.map(_tmdb)
    cp["key"] = [f"tmdb:{t}" if t else f"cp:{c}" for t, c in zip(cp.tmdb_id, cp.coupang_id)]
    cp["pop"] = _pct_by_count(cp.rating_count) if len(cp) else []

    jw_key = dict(zip(jw.justwatch_id, jw.key))
    added: dict[str, date] = {}

    def note(key: str | None, day) -> None:
        if key and day is not None and not pd.isna(day):
            added[key] = max(added.get(key, day), day)

    for jid, tmdb, day in zip(new.justwatch_id, new.tmdb_id, new.added_on):
        t = _tmdb(tmdb)
        note(f"tmdb:{t}" if t else jw_key.get(jid), day)
    if "added_on" in cp:
        for key, day in zip(cp.key, cp.added_on):
            note(key, day)

    ml = {_tmdb(t): int(m) for m, t in zip(links.movieId, links.tmdbId) if _tmdb(t)}
    week_ago = today - timedelta(days=7)

    rows = []
    for key in dict.fromkeys([*jw.key, *cp.key]):
        j = jw[jw.key == key]
        c = cp[cp.key == key]
        first = j.iloc[0] if len(j) else c.iloc[0]
        poster = next((p for p in [*j.poster_url, *c.poster_url] if isinstance(p, str) and p), None)
        year = _year(first.release_year) if len(j) else _year(first.year_hint)
        day = added.get(key)
        tmdb = first.tmdb_id
        rows.append({
            "movie_key": key, "tmdb_id": tmdb, "movielens_id": ml.get(tmdb),
            "title": first.title, "release_year": year,
            "genres": list(first.genres), "description": first.description or "",
            "actors": list(c.iloc[0].actors) if len(c) else [], "poster_url": poster,
            "services": sorted({*j.service, *(["cou"] if len(c) else [])}),
            "popularity_kr": float(max([*j["pop"], *c["pop"]])),
            "added_on": day, "new_this_week": day is not None and day >= week_ago,
        })
    out = pd.DataFrame(rows)
    # Keep None (not NaN) for missing ids and dates.
    for col in ("tmdb_id", "movielens_id", "release_year", "added_on"):
        out[col] = out[col].astype(object).where(out[col].notna(), None)
    return out
