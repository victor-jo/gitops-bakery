# FastAPI app of the recommender: genres, onboarding posters, marks, watched and weekend picks
from __future__ import annotations

import logging
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Protocol

import numpy as np
import pandas as pd
from fastapi import FastAPI, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from recommender.config import SERVICES, VIEWERS
from recommender.core.foldin import fold_in, genre_prior
from recommender.core.rank import recommend
from recommender.core.state import CoupleState, Event, replay
from recommender.genres import CANONICAL, KOREAN_LABEL

WEB = Path(__file__).resolve().parent.parent / "web"

log = logging.getLogger(__name__)


class Store(Protocol):
    def catalog(self) -> pd.DataFrame: ...
    def global_bias(self) -> float: ...
    def append(self, event: Event) -> None: ...
    def events(self) -> list[Event]: ...
    def push_taste(self, viewer: str, vector: np.ndarray) -> None: ...
    def taste(self, viewer: str) -> np.ndarray | None: ...


class GenresBody(BaseModel):
    genres: list[Literal[CANONICAL]]


class MarkBody(BaseModel):
    viewer: str
    movie_key: str
    liked: bool
    source: Literal["onboarding", "watched"]


class WatchedBody(BaseModel):
    movie_key: str


class _Catalog:
    """Arrays derived once per catalog load, shared by fold-in and onboarding."""

    def __init__(self, df: pd.DataFrame, global_bias: float):
        self.df = df
        self.global_bias = global_bias
        self.vecs = np.stack(df["vector"].to_numpy()).astype(np.float32) if len(df) else np.zeros((0, 0), np.float32)
        self.bias = df["bias"].to_numpy(dtype=np.float64)
        self.genres = [list(g) for g in df["genres"]]
        self.popularity = df["popularity_kr"].to_numpy(dtype=np.float64)
        self.row = {k: i for i, k in enumerate(df["movie_key"])}
        # Onboarding order: newest release year first, then the more popular; unknown years last
        years = (pd.array(df["release_year"], dtype="Int64").to_numpy(dtype="float64", na_value=-np.inf)
                 if "release_year" in df else np.zeros(len(df)))
        self.onboarding_order = np.lexsort((-self.popularity, -years))


class _Couple:
    """The couple's replayed state and both taste vectors, kept in step with the store."""

    def __init__(self, store: Store):
        self.store = store
        self.lock = threading.Lock()
        self.log: list[Event] = store.events()
        self.state: CoupleState = replay(self.log)
        self.taste: dict[str, np.ndarray] = {}
        self.unpushed: dict[str, np.ndarray] = {}
        self.cat: _Catalog | None = None
        self.current()
        self.push()

    @contextmanager
    def session(self):
        """Hold the lock for reads and updates, then push any refolded tastes after releasing it."""
        with self.lock:
            yield
        self.push()

    def push(self) -> None:
        """Best-effort copy of new tastes to the store; the in-process vectors stay authoritative."""
        with self.lock:
            pending, self.unpushed = self.unpushed, {}
        for vid, u in pending.items():
            try:
                self.store.push_taste(vid, u)
            except Exception:
                log.warning("taste push failed for %s", vid, exc_info=True)

    def _pair(self) -> tuple[pd.DataFrame, float]:
        # Re-read the catalog after the bias so both come from the same store snapshot.
        while True:
            df, gb = self.store.catalog(), self.store.global_bias()
            if self.store.catalog() is df:
                return df, gb

    def current(self) -> _Catalog:
        """Return the catalog arrays, rebuilding them and refolding both viewers when the store has a new catalog."""
        df, gb = self._pair()
        if self.cat is None or self.cat.df is not df or self.cat.global_bias != gb:
            self.cat = _Catalog(df, gb)
            for vid in VIEWERS:
                self.refold(vid)
        return self.cat

    def apply(self, event: Event) -> None:
        """Store the event, then replay so live updates follow exactly the start-up rules."""
        self.store.append(event)
        self.log.append(event)
        self.state = replay(self.log)

    def refold(self, vid: str) -> None:
        cat, vs = self.cat, self.state.viewers[vid]
        marks = [(cat.row[k], 1.0) for k in vs.liked if k in cat.row]
        marks += [(cat.row[k], 0.0) for k in vs.disliked if k in cat.row]
        rows = np.array([r for r, _ in marks], dtype=np.int64)
        labels = np.array([y for _, y in marks], dtype=np.float64)
        prior = genre_prior(cat.vecs, cat.genres, cat.popularity, vs.genres)
        u = fold_in(cat.vecs[rows], cat.bias[rows], cat.global_bias, labels, prior)
        self.taste[vid] = u
        self.unpushed[vid] = u


def _viewer(vid: str) -> str:
    if vid not in VIEWERS:
        raise HTTPException(404, f"unknown viewer: {vid}")
    return vid


def _movie(cat: _Catalog, key: str) -> int:
    if key not in cat.row:
        raise HTTPException(404, f"unknown movie_key: {key}")
    return cat.row[key]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def create_app(store: Store) -> FastAPI:
    couple = _Couple(store)
    app = FastAPI(title="movie recommender")

    @app.get("/api/genres")
    def genres() -> list[dict]:
        return [{"id": g, "label": KOREAN_LABEL[g]} for g in CANONICAL]

    @app.post("/api/viewer/{viewer}/genres")
    def set_genres(viewer: str, body: GenresBody) -> dict:
        vid = _viewer(viewer)
        with couple.session():
            couple.current()
            couple.apply(Event("genres", vid, None, None, list(body.genres), _now()))
            couple.refold(vid)  # the genre prior changed
        return {"ok": True}

    @app.get("/api/onboarding")
    def onboarding(viewer: str, offset: int = Query(0, ge=0), limit: int = Query(30, ge=1, le=100)) -> list[dict]:
        vid = _viewer(viewer)
        with couple.session():
            cat = couple.current()
            vs = couple.state.viewers[vid]
            chosen, marked = set(vs.genres), vs.liked | vs.disliked
        df = cat.df
        keys = df["movie_key"].to_numpy()
        rows = [i for i in cat.onboarding_order
                if keys[i] not in marked and (not chosen or not chosen.isdisjoint(cat.genres[i]))]
        out = []
        for i in rows[offset:offset + limit]:
            r = df.iloc[i]
            poster = r["poster_url"]
            out.append({"movie_key": r["movie_key"], "title": r["title"],
                        "poster_url": poster if isinstance(poster, str) else None,
                        "services": [SERVICES.get(s, s) for s in r["services"]]})
        return out

    @app.post("/api/mark")
    def mark(body: MarkBody) -> dict:
        vid = _viewer(body.viewer)
        with couple.session():
            _movie(couple.current(), body.movie_key)
            couple.apply(Event("mark", vid, body.movie_key, body.liked, None, _now()))
            couple.refold(vid)
        return {"ok": True}

    @app.post("/api/watched")
    def watched(body: WatchedBody) -> dict:
        with couple.session():
            _movie(couple.current(), body.movie_key)
            couple.apply(Event("watched", None, body.movie_key, None, None, _now()))
        return {"ok": True}

    @app.get("/api/recommendations")
    def recommendations() -> list[dict]:
        with couple.session():
            cat = couple.current()
            return recommend(cat.df, cat.global_bias, dict(couple.taste), couple.state)

    app.mount("/", StaticFiles(directory=WEB, html=True), name="web")
    return app
