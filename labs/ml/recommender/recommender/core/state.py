# Feedback events and the replay that rebuilds each viewer's marks and the watched set
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Iterable, Literal

from recommender.config import VIEWERS


@dataclass
class Event:
    kind: Literal["genres", "mark", "watched"]
    viewer: str | None
    movie_key: str | None
    liked: bool | None
    genres: list[str] | None
    at: datetime

    def to_json(self) -> str:
        return json.dumps(
            {
                "kind": self.kind,
                "viewer": self.viewer,
                "movie_key": self.movie_key,
                "liked": self.liked,
                "genres": self.genres,
                "at": self.at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            },
            ensure_ascii=False,
        )

    @classmethod
    def from_json(cls, raw: str | dict) -> "Event":
        d = json.loads(raw) if isinstance(raw, str) else raw
        at = datetime.fromisoformat(str(d["at"]).replace("Z", "+00:00"))
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        return cls(d["kind"], d.get("viewer"), d.get("movie_key"), d.get("liked"), d.get("genres"), at)


@dataclass
class ViewerState:
    genres: list[str] = field(default_factory=list)
    liked: set[str] = field(default_factory=set)
    disliked: set[str] = field(default_factory=set)


@dataclass
class CoupleState:
    viewers: dict[str, ViewerState]
    watched: set[str] = field(default_factory=set)


def replay(events: Iterable[Event]) -> CoupleState:
    """Rebuild the couple's state; events apply in `at` order and later marks win."""
    state = CoupleState({v: ViewerState() for v in VIEWERS})
    for e in sorted(events, key=lambda e: e.at):  # sorted() is stable for ties
        if e.kind == "watched" and e.movie_key:
            state.watched.add(e.movie_key)
        elif e.viewer in state.viewers:
            v = state.viewers[e.viewer]
            if e.kind == "genres":
                v.genres = list(e.genres or [])
            elif e.kind == "mark" and e.movie_key and e.liked is not None:
                v.liked.discard(e.movie_key)
                v.disliked.discard(e.movie_key)
                (v.liked if e.liked else v.disliked).add(e.movie_key)
    return state
