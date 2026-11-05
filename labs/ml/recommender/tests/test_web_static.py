# Static checks of the phone UI files: viewport, local-only assets and the six API paths
import re
from html.parser import HTMLParser
from pathlib import Path

WEB = Path(__file__).resolve().parent.parent / "web"
API_PATHS = {
    "/api/genres",
    "/api/viewer/",
    "/api/onboarding",
    "/api/mark",
    "/api/watched",
    "/api/recommendations",
}


class _Refs(HTMLParser):
    def __init__(self):
        super().__init__()
        self.viewport = None
        self.refs = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "meta" and a.get("name") == "viewport":
            self.viewport = a.get("content")
        if tag == "script" and "src" in a:
            self.refs.append(a["src"])
        if tag == "link" and "href" in a:
            self.refs.append(a["href"])


def _parse():
    p = _Refs()
    p.feed((WEB / "index.html").read_text(encoding="utf-8"))
    return p


def test_viewport_and_local_assets_only():
    p = _parse()
    assert p.viewport == "width=device-width, initial-scale=1"
    assert sorted(p.refs) == ["app.js", "style.css"]


def test_app_calls_exactly_the_six_api_paths():
    js = (WEB / "app.js").read_text(encoding="utf-8")
    found = set(re.findall(r"/api/[a-z]+/?", js))
    assert found == API_PATHS
    assert "/genres" in js  # POST /api/viewer/{viewer}/genres
    assert not re.search(r"https?://", js)


def test_no_external_urls_in_css_or_html():
    for name in ("index.html", "style.css"):
        text = (WEB / name).read_text(encoding="utf-8")
        assert not re.search(r"(https?:)?//[a-z0-9.-]+\.[a-z]{2,}", text), name
