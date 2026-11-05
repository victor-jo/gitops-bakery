# Tests for the JustWatch collector using a fake paging GraphQL post function
from datetime import date

from recommender.catalog.justwatch import fetch_service, new_titles, search_tmdb_id


def _node(oid, title, year, tmdb, score=1.0, genres=("drm",)):
    return {"objectId": oid, "content": {
        "title": title, "originalTitle": title + "-o", "originalReleaseYear": year,
        "runtime": 100, "shortDescription": "d", "genres": [{"shortName": g} for g in genres],
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
