# Tests for feedback event serialization and state replay
from datetime import datetime, timedelta, timezone

from recommender.core.state import Event, replay

T0 = datetime(2026, 11, 1, tzinfo=timezone.utc)


def _mark(v, k, liked, m):
    return Event("mark", v, k, liked, None, T0 + timedelta(minutes=m))


def test_state_replay_rebuilds_marks_and_watched():
    ev = [
        _mark("me", "a", True, 1),
        _mark("me", "a", False, 2),
        _mark("wife", "b", True, 3),
        Event("watched", None, "c", None, None, T0 + timedelta(minutes=4)),
        Event("genres", "me", None, None, ["drama"], T0 + timedelta(minutes=5)),
        Event("genres", "me", None, None, ["comedy"], T0 + timedelta(minutes=6)),
    ]
    s = replay(reversed(ev))
    assert s.viewers["me"].disliked == {"a"} and not s.viewers["me"].liked
    assert s.viewers["wife"].liked == {"b"}
    assert s.watched == {"c"}
    assert s.viewers["me"].genres == ["comedy"]
    assert replay([]).viewers.keys() == {"me", "wife"}


def test_event_json_round_trip():
    e = _mark("me", "a", True, 1)
    assert Event.from_json(e.to_json()) == e
