# Tests for the JustWatch collector using a fake paging GraphQL post function
from datetime import date

from recommender.catalog.justwatch import fetch_service, new_titles, search_title, search_tmdb_id


def _node(oid, title, year, tmdb, score=1.0, genres=("drm",), poster=True):
    return {"objectId": oid, "content": {
        "title": title, "originalTitle": title + "-o", "originalReleaseYear": year,
        "runtime": 100, "shortDescription": "d",
        "posterUrl": "/poster/%s/{profile}/x.{format}" % oid if poster else None, "genres": [{"shortName": g} for g in genres],
        "externalIds": {"imdbId": "tt" + oid, "tmdbId": tmdb},
        "scoring": {"tmdbScore": score}}}


# (min, max) -> pages of nodes; None -> the unfiltered popularity pass
DATA = {
    (1900, 1979): [[_node("a", "A", 1970, "1", 5)], [_node("b", "B", 1975, "2", 9)]],
    (2000, 2000): [[_node("c", "C", 2000, "3", 7)], [_node("a", "A", 1970, "1", 5), _node("d", "D", 2000, None, 1)]],
    None: [[_node("c", "C", 2000, "3", 7)], [_node("a", "A", 1970, "1", 5)]],
}


def fake_post(query, variables):
    key = (variables["min"], variables["max"]) if "min" in variables else None
    pages = DATA.get(key, [[]])
    i = 0 if variables.get("after") is None else int(variables["after"])
    return {"data": {"popularTitles": {
        "totalCount": 9,
        "pageInfo": {"hasNextPage": i + 1 < len(pages), "endCursor": str(i + 1)},
        "edges": [{"node": n} for n in pages[i]]}}}


def test_fetch_service_unions_slices_and_ranks():
    df = fetch_service("nfx", fake_post, years=[(1900, 1979), (2000, 2000)], pause=0)
    assert len(df) == 4
    assert df.justwatch_id.is_unique
    # unfiltered pass order first (c, a), then the rest by tmdb score desc (b=9, d=1)
    assert list(df.title) == ["C", "A", "B", "D"]
    assert list(df.popularity_rank) == [1, 2, 3, 4]
    assert set(df.service) == {"nfx"}
    assert df.genres.iloc[0] == ["drama"]
    assert df.tmdb_id.iloc[3] is None
    assert df.poster_url.iloc[0] == "https://images.justwatch.com/poster/c/s332/x.webp"


def test_fetch_service_poster_is_none_when_absent():
    data = {None: [[_node("z", "Z", 2001, "9", poster=False)]]}

    def post(query, variables):
        pages = data.get((variables["min"], variables["max"]) if "min" in variables else None, [[]])
        return {"data": {"popularTitles": {
            "totalCount": 1, "pageInfo": {"hasNextPage": False, "endCursor": None},
            "edges": [{"node": n} for n in pages[0]]}}}

    df = fetch_service("nfx", post, years=[(2001, 2001)], pause=0)
    assert df.poster_url.iloc[0] is None


def test_new_titles_sends_new_page_type_and_stamps_day():
    seen = {}

    def post(query, variables):
        seen.update(variables)
        seen["query"] = query
        return {"data": {"newTitles": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "edges": [{"node": {"objectId": "x", "content": {"externalIds": {"tmdbId": "7"}}}}]}}}

    df = new_titles(date(2026, 11, 5), ["nfx"], post)
    assert seen["date"] == "2026-11-05" and seen["packages"] == ["nfx"]
    assert "NEW" in seen["query"]
    assert df.iloc[0].tolist() == ["x", "7", "nfx", date(2026, 11, 5)]


def _search_post(title, year, tmdb="496243"):
    def post(query, variables):
        return {"data": {"popularTitles": {"edges": [{"node": {"content": {
            "title": title, "originalReleaseYear": year, "externalIds": {"tmdbId": tmdb}}}}]}}}
    return post


def test_search_exact_normalized_title_and_year():
    assert search_tmdb_id("기생충", 2019, _search_post("기생충 (자막)", 2019)) == "496243"
    assert search_tmdb_id("기 생충!", 2019, _search_post("기생충", 2020)) == "496243"
    assert search_tmdb_id("기생충", 2019, _search_post("기생충2", 2019)) is None
    assert search_tmdb_id("기생충", 2019, _search_post("기생충", 2015)) is None


def test_pause_between_every_request_including_slice_boundaries(monkeypatch):
    sleeps = []
    monkeypatch.setattr("recommender.catalog.justwatch.time.sleep", sleeps.append)
    calls = []

    def post(query, variables):
        calls.append(variables)
        return fake_post(query, variables)

    fetch_service("nfx", post, years=[(1900, 1979), (1900, 1979)], pause=0.3)
    # 2 single-slice requests (2 pages each) + unfiltered pass (2 pages): sleep before all but the first
    assert len(calls) == 6 and sleeps == [0.3] * 5


def test_new_titles_queries_each_package_and_stamps_service(monkeypatch):
    monkeypatch.setattr("recommender.catalog.justwatch.time.sleep", lambda s: None)

    def post(query, variables):
        pkg = variables["packages"][0]
        return {"data": {"newTitles": {
            "pageInfo": {"hasNextPage": False, "endCursor": None},
            "edges": [{"node": {"objectId": pkg + "1", "content": {"externalIds": {"tmdbId": "1"}}}}]}}}

    df = new_titles(date(2026, 11, 5), ["nfx", "dnp"], post)
    assert list(df.service) == ["nfx", "dnp"] and list(df.justwatch_id) == ["nfx1", "dnp1"]


def test_search_title_returns_the_release_year_with_the_tmdb_id():
    assert search_title("기생충", None, _search_post("기생충", 2019)) == {"tmdb_id": "496243", "release_year": 2019}
    assert search_title("기생충", 2019, _search_post("기생충", 2015)) is None
