# Collects Netflix and Disney+ Korea movie catalogs and daily additions from the unofficial JustWatch GraphQL API
import json
import re
import time
import unicodedata
import urllib.request
from collections.abc import Callable
from datetime import date

import pandas as pd

from recommender.genres import from_justwatch

URL = "https://apis.justwatch.com/graphql"
COUNTRY = "KR"
PAGE_SIZE = 100
# The unfiltered popularity ranking stops paging near this many results.
RANKED_LIMIT = 1900

Post = Callable[[str, dict], dict]

_CONTENT = """content(country: $country, language: "ko") {
  title originalTitle originalReleaseYear runtime shortDescription posterUrl
  genres { shortName } externalIds { imdbId tmdbId } scoring { tmdbScore } }"""

_POPULAR = """query($country: Country!, $first: Int!, $after: String, $pkg: [String!]%s) {
  popularTitles(country: $country, first: $first, after: $after,
    filter: {objectTypes: [MOVIE], packages: $pkg%s}) {
    totalCount pageInfo { hasNextPage endCursor }
    edges { node { objectId %s } } } }""" % (
    ", $min: Int!, $max: Int!", ", releaseYear: {min: $min, max: $max}", _CONTENT)
_POPULAR_ALL = _POPULAR.replace(", $min: Int!, $max: Int!", "").replace(", releaseYear: {min: $min, max: $max}", "")

_NEW = """query($country: Country!, $first: Int!, $after: String, $date: Date!, $packages: [String!]) {
  newTitles(country: $country, date: $date, first: $first, after: $after, pageType: NEW,
    filter: {objectTypes: [MOVIE], packages: $packages}) {
    pageInfo { hasNextPage endCursor }
    edges { node { ... on Movie { objectId content(country: $country, language: "ko") {
      externalIds { tmdbId } } } } } } }"""

_SEARCH = """query($country: Country!, $first: Int!, $q: String!) {
  popularTitles(country: $country, first: $first, filter: {searchQuery: $q, objectTypes: [MOVIE]}) {
    edges { node { ... on Movie { content(country: $country, language: "ko") {
      title originalReleaseYear externalIds { tmdbId } } } } } } }"""


def http_post(query: str, variables: dict) -> dict:
    """POST one GraphQL request and return the parsed JSON; raise on GraphQL errors."""
    body = json.dumps({"query": query, "variables": variables}).encode()
    req = urllib.request.Request(URL, body, {"content-type": "application/json"})
    data = json.loads(urllib.request.urlopen(req, timeout=30).read())
    if data.get("errors"):
        raise RuntimeError(json.dumps(data["errors"])[:800])
    return data


def default_years() -> list[tuple[int, int]]:
    return [(1900, 1979), (1980, 1989), (1990, 1999)] + [
        (y, y) for y in range(2000, date.today().year + 2)]


def _paced(post: Post, pause: float) -> Post:
    """Wrap post so every request except the first waits `pause` seconds after the previous one."""
    first = True

    def paced(query: str, variables: dict) -> dict:
        nonlocal first
        if not first:
            time.sleep(pause)
        first = False
        return post(query, variables)

    return paced


def _pages(field: str, query: str, variables: dict, post: Post):
    after = None
    while True:
        conn = post(query, {**variables, "first": PAGE_SIZE, "after": after})["data"][field]
        yield from (e["node"] for e in conn["edges"])
        if not conn["pageInfo"]["hasNextPage"]:
            return
        after = conn["pageInfo"]["endCursor"]


def _poster(path: str | None) -> str | None:
    if not path:
        return None
    return "https://images.justwatch.com" + path.replace("{profile}", "s332").replace("{format}", "webp")


def _row(node: dict, package: str) -> dict:
    c = node["content"]
    ids = c["externalIds"] or {}
    return {
        "justwatch_id": node["objectId"], "tmdb_id": ids.get("tmdbId"), "imdb_id": ids.get("imdbId"),
        "title": c["title"], "original_title": c["originalTitle"],
        "release_year": c["originalReleaseYear"], "runtime_min": c["runtime"],
        "genres": from_justwatch([g["shortName"] for g in c["genres"]]),
        "description": c["shortDescription"] or "", "poster_url": _poster(c.get("posterUrl")),
        "service": package,
        "_tmdb_score": (c["scoring"] or {}).get("tmdbScore") or 0.0,
    }


def fetch_service(package: str, post: Post, years: list[tuple[int, int]] | None = None,
                  pause: float = 0.3) -> pd.DataFrame:
    """Return every movie on one service in Korea with a popularity rank.

    Titles are collected in release-year slices because paging stops near 1,900 results.
    Slice order says nothing about popularity, so the rank comes from one unfiltered
    popularTitles pass (JustWatch order, capped near 1,900); titles it never reaches are
    appended after it by tmdb score descending.
    """
    post = _paced(post, pause)
    rows: dict[str, dict] = {}
    for lo, hi in years or default_years():
        for node in _pages("popularTitles", _POPULAR,
                           {"country": COUNTRY, "pkg": [package], "min": lo, "max": hi}, post):
            rows.setdefault(node["objectId"], _row(node, package))
    ranked: list[str] = []
    for node in _pages("popularTitles", _POPULAR_ALL, {"country": COUNTRY, "pkg": [package]}, post):
        oid = node["objectId"]
        rows.setdefault(oid, _row(node, package))
        if oid not in ranked:
            ranked.append(oid)
    in_ranked = set(ranked)
    rest = sorted((r for k, r in rows.items() if k not in in_ranked), key=lambda r: -r["_tmdb_score"])
    ordered = [rows[k] for k in ranked] + rest
    df = pd.DataFrame(ordered).drop(columns="_tmdb_score")
    df["popularity_rank"] = range(1, len(df) + 1)
    return df


def new_titles(day: date, packages: list[str], post: Post, pause: float = 0.3) -> pd.DataFrame:
    """Return movies that JustWatch lists as newly added on the given day, one query per package."""
    post = _paced(post, pause)
    rows = [
        {"justwatch_id": n["objectId"], "tmdb_id": (n["content"]["externalIds"] or {}).get("tmdbId"),
         "service": pkg, "added_on": day}
        for pkg in packages
        for n in _pages("newTitles", _NEW,
                        {"country": COUNTRY, "date": day.isoformat(), "packages": [pkg]}, post)
        if n.get("content")
    ]
    return pd.DataFrame(rows, columns=["justwatch_id", "tmdb_id", "service", "added_on"])


def _norm(title: str) -> str:
    t = unicodedata.normalize("NFKC", title).lower()
    t = re.sub(r"\s*\((\d{4}|자막)\)\s*$", "", t)
    return re.sub(r"[\W_]+", "", t)


def search_tmdb_id(title: str, year: int | None, post: Post) -> str | None:
    """Look a title up by name and return its tmdb id only on an exact normalized match within one year."""
    conn = post(_SEARCH, {"country": COUNTRY, "first": 10, "q": title})["data"]["popularTitles"]
    want = _norm(title)
    for e in conn["edges"]:
        c = (e["node"] or {}).get("content")
        if not c or _norm(c["title"]) != want:
            continue
        y = c["originalReleaseYear"]
        if year is not None and (y is None or abs(y - year) > 1):
            continue
        tmdb = (c["externalIds"] or {}).get("tmdbId")
        if tmdb:
            return tmdb
    return None
