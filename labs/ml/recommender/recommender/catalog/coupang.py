# Politely collects Coupang Play movie metadata from public sitemap and /content pages
import json
import re
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import date, datetime, timezone
from xml.etree import ElementTree

import pandas as pd

from recommender.genres import from_coupang

USER_AGENT = "gitops-bakery-movie-rec (personal lab)"
TIMEOUT = 20
# Consecutive non-200/404 responses that end a pass.
MAX_FAILURES = 5
# When False, datePublished is not an "added to Coupang" date and added_on stays None.
COUPANG_ADDED_ON_IS_RELIABLE = True

_CONTENT_URL = re.compile(r"https://www\.coupangplay\.com/content/[0-9a-f-]{36}")
_LD_JSON = re.compile(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', re.S)
_SUFFIX = re.compile(r"\s*\((\d{4}|자막|더빙)\)\s*$")


def content_urls(sitemap_xml: str) -> list[str]:
    """Return unique Korean /content/<uuid> URLs in file order."""
    locs = (e.text.strip() for e in ElementTree.fromstring(sitemap_xml).iter()
            if e.tag.endswith("}loc") or e.tag == "loc")
    return list(dict.fromkeys(u for u in locs if _CONTENT_URL.fullmatch(u)))


def _split_title(name: str) -> tuple[str, int | None]:
    year = None
    while (m := _SUFFIX.search(name)):
        if m.group(1).isdigit() and year is None:
            year = int(m.group(1))
        name = name[:m.start()]
    return name.strip(), year


def parse_page(html: str, url: str) -> dict | None:
    """Return movie fields from the page's Movie JSON-LD, or None if it has none."""
    movie = None
    for block in _LD_JSON.findall(html):
        try:
            data = json.loads(block)
        except ValueError:
            continue
        if isinstance(data, dict) and data.get("@type") == "Movie":
            movie = data
            break
    if movie is None:
        return None
    title, year = _split_title(movie.get("name", ""))
    rating = movie.get("aggregateRating") or {}
    published = movie.get("datePublished")
    added_on = None
    if COUPANG_ADDED_ON_IS_RELIABLE and published:
        try:
            added_on = date.fromisoformat(published[:10])
        except ValueError:
            pass
    value = rating.get("ratingValue")
    return {
        "coupang_id": url.rstrip("/").rsplit("/", 1)[-1],
        "title": title,
        "year_hint": year,
        "genres": from_coupang(movie.get("genre") or []),
        "description": movie.get("description") or "",
        "actors": [a["name"] for a in movie.get("actor") or [] if a.get("name")],
        "poster_url": movie.get("image"),
        "rating": float(value) if value is not None else None,
        "rating_count": int(rating.get("ratingCount") or 0),
        "added_on": added_on,
    }


def default_fetch(url: str) -> tuple[int, str]:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            return r.status, r.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, ""
    except (OSError, UnicodeDecodeError):
        return 0, ""  # network failure: treated as transient by crawl


def crawl(urls: list[str], fetch: Callable[[str], tuple[int, str]] = default_fetch,
          cache: pd.DataFrame | None = None, pause: float = 1.0,
          sleep: Callable[[float], None] = time.sleep,
          on_batch: Callable[[pd.DataFrame], None] | None = None,
          batch_size: int = 200) -> pd.DataFrame:
    """Fetch only URLs missing from the cache, pausing between requests; return cache plus new rows.

    Stops early (returning the partial frame) on 429/403 or after 5 consecutive transient failures.
    on_batch receives the cache-so-far every batch_size new rows and once more if an error escapes.
    """
    if any("/api" in u for u in urls):
        raise ValueError("refusing to request an /api path")
    cache = pd.DataFrame() if cache is None else cache
    seen = set(cache["url"]) if "url" in cache else set()
    rows, first, failures, flushed = [], True, 0, 0

    def so_far() -> pd.DataFrame:
        return pd.concat([cache, pd.DataFrame(rows)], ignore_index=True) if rows else cache

    try:
        for url in dict.fromkeys(urls):
            if url in seen:
                continue
            if not first:
                sleep(pause)
            first = False
            code, html = fetch(url)
            if code in (429, 403):
                print(f"coupang crawl stopped: HTTP {code} (throttled or blocked)")
                break
            if code in (404, 410):
                row = {"status": "gone"}
            elif code != 200:
                failures += 1  # transient: leave uncached so the next pass retries it
                if failures >= MAX_FAILURES:
                    print(f"coupang crawl stopped: {failures} consecutive failures (last HTTP {code})")
                    break
                continue
            elif (page := parse_page(html, url)) is None:
                row = {"status": "not_movie"}
            else:
                row = {"status": "movie", **page}
            failures = 0
            rows.append({"url": url, "coupang_id": url.rsplit("/", 1)[-1], **row,
                         "fetched_at": datetime.now(timezone.utc)})
            if on_batch and len(rows) - flushed >= batch_size:
                on_batch(so_far())
                flushed = len(rows)
    except BaseException:
        if on_batch and len(rows) > flushed:
            on_batch(so_far())
        raise
    return so_far()
