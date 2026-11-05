# Tests for the Coupang Play collector using trimmed real pages and a fake fetch function
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from recommender.catalog.coupang import content_urls, crawl, parse_page

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
