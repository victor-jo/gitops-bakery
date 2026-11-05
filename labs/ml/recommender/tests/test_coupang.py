# Tests for the Coupang Play collector using trimmed real pages and a fake fetch function
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from recommender.catalog.coupang import content_urls, crawl, current_movies, parse_page, recheck_candidates

FIX = Path(__file__).parent / "fixtures"
MOVIE = (FIX / "coupang_movie.html").read_text()
SERIES = (FIX / "coupang_series.html").read_text()
BASE = "https://www.coupangplay.com/content/"


def test_content_urls_keeps_only_korean_content_pages():
    urls = content_urls((FIX / "coupang_sitemap.xml").read_text())
    assert len(urls) == 2
    assert all(u.startswith(BASE) for u in urls)


def test_content_urls_dedupes_in_file_order():
    xml = "<urlset>" + "".join(f"<url><loc>{BASE}{i}</loc></url>" for i in (
        "00000000-0000-0000-0000-00000000000b", "00000000-0000-0000-0000-00000000000a",
        "00000000-0000-0000-0000-00000000000b")) + "</urlset>"
    assert [u[-1] for u in content_urls(xml)] == ["b", "a"]


def test_parse_page_movie():
    m = parse_page(MOVIE, BASE + "3261dee8-1070-4e30-a435-3365130529a6")
    assert m["coupang_id"] == "3261dee8-1070-4e30-a435-3365130529a6"
    assert m["title"] == "트위스터"
    assert m["year_hint"] == 1996
    assert m["added_on"] == date(2023, 8, 21)
    assert m["rating_count"] == 74
    assert m["rating"] == 4.6
    assert m["actors"][0] == "빌 팩스톤"
    assert m["genres"] and m["poster_url"].startswith("https://")


def test_parse_page_series_is_none():
    assert parse_page(SERIES, BASE + "00039ec7-5143-4504-b58b-f12bf6cefa21") is None


def test_parse_page_without_rating():
    html = MOVIE.replace(',"aggregateRating":{"@type":"AggregateRating","ratingValue":4.6,"bestRating":5,"worstRating":1,"ratingCount":74}', "")
    m = parse_page(html, BASE + "x")
    assert m["rating"] is None and m["rating_count"] == 0


def test_parse_page_strips_subtitle_suffix():
    m = parse_page(MOVIE.replace("트위스터(1996)", "마션 (자막)"), BASE + "x")
    assert m["title"] == "마션" and m["year_hint"] is None


def test_crawl_skips_404_and_series():
    urls = [BASE + "a", BASE + "b", BASE + "c"]
    pages = {urls[0]: (404, ""), urls[1]: (200, SERIES), urls[2]: (200, MOVIE)}
    calls, sleeps = [], []

    def fetch(u):
        calls.append(u)
        return pages[u]

    out = crawl(urls, fetch, pd.DataFrame(), sleep=sleeps.append)
    assert list(out["status"]) == ["gone", "not_movie", "movie"]
    assert out["fetched_at"].notna().all()
    assert sleeps == [1.0, 1.0]
    calls.clear()
    again = crawl(urls, fetch, out, sleep=sleeps.append)
    assert calls == [] and len(again) == 3


def test_crawl_refuses_api_paths():
    calls = []
    with pytest.raises(ValueError):
        crawl([BASE + "a", "https://www.coupangplay.com/api/v1/x"],
              lambda u: calls.append(u) or (200, MOVIE), pd.DataFrame(), sleep=lambda s: None)
    assert calls == []


def test_crawl_checkpoints_before_an_error_escapes():
    urls = [BASE + "a", BASE + "b", BASE + "c"]
    saved = []

    def fetch(u):
        if u.endswith("c"):
            raise RuntimeError("boom")
        return 200, MOVIE

    with pytest.raises(RuntimeError):
        crawl(urls, fetch, pd.DataFrame(), sleep=lambda s: None, on_batch=saved.append)
    assert len(saved[-1]) == 2


def test_crawl_calls_on_batch_every_batch_size_rows():
    saved = []
    crawl([BASE + str(i) for i in range(5)], lambda u: (200, MOVIE), pd.DataFrame(),
          sleep=lambda s: None, on_batch=lambda df: saved.append(len(df)), batch_size=2)
    assert saved == [2, 4]


def test_crawl_stops_on_429_and_after_repeated_failures_and_maps_410_to_gone():
    urls = [BASE + str(i) for i in range(10)]
    calls = []
    out = crawl(urls, lambda u: calls.append(u) or ((410, "") if len(calls) == 1 else (429, "")),
                pd.DataFrame(), sleep=lambda s: None)
    assert list(out["status"]) == ["gone"] and len(calls) == 2
    calls.clear()
    out = crawl(urls, lambda u: calls.append(u) or (503, ""), pd.DataFrame(), sleep=lambda s: None)
    assert len(calls) == 5 and len(out) == 0


def _cache(rows):
    """rows: (suffix, status, fetched_at day)."""
    return pd.DataFrame([{"url": BASE + k, "coupang_id": k, "status": st, "title": f"T{k}",
                          "fetched_at": pd.Timestamp(f"2026-01-{day:02d}", tz="UTC")} for k, st, day in rows])


def test_current_movies_keeps_only_movies_still_in_the_sitemap():
    cache = _cache([("a", "movie", 1), ("b", "movie", 2), ("c", "not_movie", 3), ("d", "gone", 4)])
    out = current_movies(cache, [BASE + "a", BASE + "c", BASE + "d", BASE + "new"])
    assert list(out["coupang_id"]) == ["a"]


def test_recheck_picks_the_oldest_live_rows_and_skips_gone():
    cache = _cache([("a", "movie", 5), ("b", "gone", 1), ("c", "not_movie", 2), ("d", "movie", 9),
                    ("e", "movie", 3)])
    assert recheck_candidates(cache, 3) == [BASE + "c", BASE + "e", BASE + "a"]
    assert recheck_candidates(None) == [] and recheck_candidates(pd.DataFrame()) == []


def test_crawl_rechecks_cached_rows_and_updates_status_and_time():
    cache = _cache([("a", "movie", 1), ("b", "movie", 2), ("c", "not_movie", 3), ("d", "movie", 4)])
    pages = {BASE + "a": (404, ""), BASE + "b": (200, SERIES), BASE + "c": (503, ""), BASE + "new": (200, MOVIE)}
    calls, sleeps = [], []
    out = crawl([BASE + "new"], lambda u: calls.append(u) or pages[u], cache, sleep=sleeps.append,
                recheck=[BASE + "a", BASE + "b", BASE + "c"])
    # New URLs first, then the rechecks, all one second apart; "d" was not due
    assert calls == [BASE + "new", BASE + "a", BASE + "b", BASE + "c"] and sleeps == [1.0] * 3
    by = out.set_index("coupang_id")
    assert len(out) == 5 and out["url"].is_unique
    assert by.loc["a", "status"] == "gone" and by.loc["b", "status"] == "not_movie"
    assert by.loc["a", "fetched_at"] > pd.Timestamp("2026-02-01", tz="UTC")
    # A transient failure keeps the old row as it was
    assert by.loc["c", "status"] == "not_movie" and by.loc["c", "fetched_at"] == pd.Timestamp("2026-01-03", tz="UTC")
    assert by.loc["d", "status"] == "movie" and by.loc["new", "status"] == "movie"


def test_recheck_stops_on_429_and_refuses_api_paths():
    cache = _cache([("a", "movie", 1), ("b", "movie", 2)])
    calls = []
    out = crawl([], lambda u: calls.append(u) or (429, ""), cache, sleep=lambda s: None,
                recheck=[BASE + "a", BASE + "b"])
    assert calls == [BASE + "a"] and out.equals(cache)
    with pytest.raises(ValueError):
        crawl([], lambda u: (200, MOVIE), cache, recheck=["https://www.coupangplay.com/api/x"])
