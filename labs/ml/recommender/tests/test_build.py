# Tests for coupang-to-tmdb matching, the merged movie catalog and the S3 helpers
import io
import json
from datetime import date

import pandas as pd
import pytest

from recommender import s3
from recommender.catalog.build import build_catalog, match_coupang

TODAY = date(2026, 11, 5)
LINKS = pd.DataFrame({"movieId": [10, 20], "imdbId": [1, 2], "tmdbId": [100.0, None]})


def _jw(rows):
    cols = ["justwatch_id", "tmdb_id", "title", "release_year", "genres", "description",
            "poster_url", "service", "popularity_rank"]
    return pd.DataFrame(rows, columns=cols)


def _cp(rows):
    cols = ["coupang_id", "status", "title", "year_hint", "genres", "description", "actors",
            "poster_url", "rating_count", "added_on", "tmdb_id"]
    return pd.DataFrame(rows, columns=cols)


NEW = pd.DataFrame(columns=["justwatch_id", "tmdb_id", "service", "added_on"])


def test_build_catalog_merges_services_by_tmdb_id():
    jw = _jw([
        ["j1", "100", "Alpha", 2020, ["drama"], "jw", "http://jw/1", "nfx", 1],
        ["j2", "200", "Beta", 2021, ["comedy"], "jw", None, "nfx", 2],
        ["j3", "300", "Gamma", 2019, ["drama"], "jw", "http://jw/3", "dnp", 1],
    ])
    cp = _cp([
        ["c1", "movie", "알파", 2020.0, ["drama"], "cp", ["A"], "http://cp/1", 50, None, "100"],
        ["c2", "movie", "베타", float("nan"), ["comedy"], "cp", ["B"], "http://cp/2", 10, None, "200"],
        ["c3", "movie", "오직쿠팡", float("nan"), ["horror"], "cp", ["C"], "http://cp/3", None, None, None],
    ])
    out = build_catalog(jw, cp, NEW, LINKS, TODAY).set_index("movie_key")
    assert set(out.index) == {"tmdb:100", "tmdb:200", "tmdb:300", "cp:c3"}
    assert out.loc["tmdb:100", "services"] == ["cou", "nfx"]
    assert out.loc["tmdb:100", "poster_url"] == "http://jw/1"
    assert out.loc["tmdb:200", "poster_url"] == "http://cp/2"
    assert out.loc["tmdb:100", "actors"] == ["A"]
    assert out.loc["tmdb:300", "actors"] == []
    assert out.loc["tmdb:100", "title"] == "Alpha"
    assert out.loc["cp:c3", "title"] == "오직쿠팡"
    assert out.loc["cp:c3", "services"] == ["cou"]
    assert out.loc["cp:c3", "tmdb_id"] is None
    assert out.loc["tmdb:100", "movielens_id"] == 10
    assert out.loc["tmdb:200", "movielens_id"] is pd.NA
    assert out.movielens_id.dtype == "Int64" and out.release_year.dtype == "Int64"
    assert int(out.loc["tmdb:100", "movielens_id"]) == out.loc["tmdb:100", "movielens_id"] == 10
    assert out.loc["cp:c3", "release_year"] is pd.NA
    assert out.loc["tmdb:100", "release_year"] == 2020
    assert out.loc["tmdb:100", "popularity_kr"] == 1.0
    assert out.loc["tmdb:200", "popularity_kr"] == pytest.approx(2 / 3)
    assert out.loc["cp:c3", "popularity_kr"] == 0.0
    assert out.popularity_kr.between(0, 1).all()


def test_build_catalog_new_this_week_window():
    jw = _jw([["j1", "1", "A", 2020, [], "", None, "nfx", 1], ["j2", "2", "B", 2020, [], "", None, "nfx", 2],
              ["j3", "3", "C", 2020, [], "", None, "dnp", 1]])
    new = pd.DataFrame({
        "justwatch_id": ["j1", "j2"], "tmdb_id": ["1", "2"], "service": ["nfx", "nfx"],
        "added_on": [date(2026, 10, 29), date(2026, 10, 28)]})
    out = build_catalog(jw, _cp([]), new, LINKS, TODAY).set_index("movie_key")
    assert out.loc["tmdb:1", "new_this_week"] and out.loc["tmdb:1", "added_on"] == date(2026, 10, 29)
    assert not out.loc["tmdb:2", "new_this_week"]
    assert out.loc["tmdb:3", "added_on"] is None and not out.loc["tmdb:3", "new_this_week"]


def test_new_title_without_tmdb_id_keeps_added_on():
    jw = _jw([["j1", None, "A", 2020, [], "", None, "nfx", 1]])
    new = pd.DataFrame({"justwatch_id": ["j1"], "tmdb_id": ["5"], "service": ["nfx"],
                        "added_on": [date(2026, 11, 1)]})
    out = build_catalog(jw, _cp([]), new, LINKS, TODAY)
    assert list(out.movie_key) == ["jw:j1"]
    assert out.added_on.iloc[0] == date(2026, 11, 1) and out.new_this_week.iloc[0]


def test_match_coupang_never_searches_a_coupang_id_twice():
    cp = _cp([["c1", "movie", "A", 2020.0, [], "", [], None, 1, None, None],
              ["c2", "movie", "B", float("nan"), [], "", [], None, 1, None, None],
              ["c3", "movie", "C", 2001.0, [], "", [], None, 1, None, None]])
    calls = []

    def search(title, year):
        calls.append((title, year))
        return {"A": "11", "B": None}.get(title)

    known = {"c3": "33"}
    out = match_coupang(cp, search, known)
    assert calls == [("A", 2020), ("B", None)]
    assert list(out.tmdb_id) == ["11", None, "33"]
    assert known == {"c1": "11", "c2": None, "c3": "33"}
    match_coupang(cp, search, known)
    assert len(calls) == 2


class FakeClient:
    def __init__(self):
        self.objects = {}

    def put_object(self, Bucket, Key, Body, **kw):
        self.objects[(Bucket, Key)] = Body

    def get_object(self, Bucket, Key):
        return {"Body": io.BytesIO(self.objects[(Bucket, Key)])}

    def list_objects_v2(self, Bucket, Prefix, **kw):
        return {"Contents": [{"Key": k} for (b, k) in sorted(self.objects) if b == Bucket and k.startswith(Prefix)]}


def test_s3_helpers_roundtrip_with_fake_client(monkeypatch):
    fake = FakeClient()
    monkeypatch.setattr(s3, "client", lambda: fake)
    df = pd.DataFrame({"a": [1, 2], "b": [["x"], []]})
    s3.write_parquet(df, "catalog/x.parquet")
    s3.put_json({"k": 1}, "catalog/x.json")
    assert s3.read_parquet("catalog/x.parquet").a.tolist() == [1, 2]
    assert json.loads(fake.objects[("recommender", "catalog/x.json")]) == {"k": 1}
    assert s3.list_keys("catalog/") == ["catalog/x.json", "catalog/x.parquet"]


def test_s3_client_reads_env(monkeypatch):
    seen = {}
    monkeypatch.setenv("S3_ENDPOINT", "host:3900")
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "s")
    monkeypatch.setattr(s3.boto3, "client", lambda *a, **kw: seen.update(kw) or object())
    s3.client()
    assert seen["endpoint_url"] == "http://host:3900" and seen["region_name"] == "garage"
