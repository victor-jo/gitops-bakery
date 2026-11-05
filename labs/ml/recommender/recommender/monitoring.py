# Weekly monitoring of the couple recommender: joint thumbs-up rate and genre/taste drift sent to Evidently
from __future__ import annotations

import warnings
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from recommender.config import VIEWERS
from recommender.core.foldin import fold_in, genre_prior
from recommender.core.state import Event, replay
from recommender.genres import CANONICAL

KST = timezone(timedelta(hours=9))
PROJECT = "movie-recommender"
WINDOW = timedelta(days=7)
HISTORY = "catalog/history/"
# Rows a genre mix is expanded to for the category drift test; shares are rounded to 1/GENRE_ROWS
GENRE_ROWS = 200
JOINT_PANEL = "Joint thumbs-up rate (last run)"
WATCHED_PANEL = "Watched movies (last run)"
DRIFT_PANEL = "Share of drifted columns"


def _week(at: datetime) -> str:
    iso = at.astimezone(KST).isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def _both_liked(events: list[Event], watched: Event) -> int:
    """1 when every viewer's latest mark on the movie at or after the watch is a thumbs-up."""
    for viewer in VIEWERS:
        marks = [e for e in events if e.kind == "mark" and e.viewer == viewer
                 and e.movie_key == watched.movie_key and e.at >= watched.at]
        if not marks or not max(marks, key=lambda e: e.at).liked:
            return 0
    return 1


def _genre_mix(catalog: pd.DataFrame) -> pd.DataFrame:
    counts = catalog["genres"].explode().value_counts()
    share = pd.Series({g: float(counts.get(g, 0)) for g in CANONICAL})
    total = share.sum()
    return pd.DataFrame({"genre": list(CANONICAL), "share": (share / total if total else share).to_numpy()})


def _taste(vectors: dict[str, np.ndarray]) -> pd.DataFrame:
    rows = [np.asarray(vectors[v], dtype=float) for v in VIEWERS if v in vectors]
    dim = len(rows[0]) if rows else 0
    return pd.DataFrame(rows, columns=[f"d{i}" for i in range(dim)], index=[v for v in VIEWERS if v in vectors])


def weekly_frames(events: list[Event], catalog_now: pd.DataFrame, catalog_before: pd.DataFrame,
                  taste_now: dict, taste_before: dict) -> dict[str, pd.DataFrame]:
    """Pure frame building: one row per watched movie, genre shares per snapshot, one taste row per viewer."""
    watched = [e for e in sorted(events, key=lambda e: e.at) if e.kind == "watched" and e.movie_key]
    return {
        "watched": pd.DataFrame({
            "movie_key": [e.movie_key for e in watched],
            "both_liked": pd.Series([_both_liked(events, e) for e in watched], dtype=int),
            "week": [_week(e.at) for e in watched],
        }),
        "genre_mix_now": _genre_mix(catalog_now),
        "genre_mix_before": _genre_mix(catalog_before),
        "taste_now": _taste(taste_now),
        "taste_before": _taste(taste_before),
    }


def taste_vectors(events: list[Event], features: pd.DataFrame, global_bias: float,
                  until: datetime | None = None) -> dict[str, np.ndarray]:
    """Each viewer's folded-in taste from the events up to `until`, exactly as the service folds it."""
    state = replay([e for e in events if until is None or e.at <= until])
    vecs = np.stack(features["vector"].to_numpy()).astype(np.float32)
    bias = features["bias"].to_numpy(dtype=np.float64)
    genres = [list(g) for g in features["genres"]]
    popularity = features["popularity_kr"].to_numpy(dtype=np.float64)
    row = {k: i for i, k in enumerate(features["movie_key"])}
    out = {}
    for vid, vs in state.viewers.items():
        marks = [(row[k], 1.0) for k in vs.liked if k in row] + [(row[k], 0.0) for k in vs.disliked if k in row]
        rows = np.array([r for r, _ in marks], dtype=np.int64)
        labels = np.array([y for _, y in marks], dtype=np.float64)
        out[vid] = fold_in(vecs[rows], bias[rows], global_bias, labels,
                           genre_prior(vecs, genres, popularity, vs.genres))
    return out


def pick_history(keys: list[str], today: date) -> str | None:
    """The newest snapshot at least 7 days old, else the oldest one; None when there is none."""
    dated = sorted((date.fromisoformat(k.removeprefix(HISTORY).removesuffix(".parquet")), k)
                   for k in keys if k.startswith(HISTORY) and k.endswith(".parquet"))
    if not dated:
        return None
    old = [k for d, k in dated if d <= today - WINDOW]
    return old[-1] if old else dated[0][1]


def joint_like(watched: pd.DataFrame) -> pd.DataFrame:
    """One row with the joint thumbs-up rate (NaN with nothing watched yet) and the watched count."""
    rate = float(watched["both_liked"].mean()) if len(watched) else float("nan")
    return pd.DataFrame({"joint_like_rate": [rate], "watched_count": [float(len(watched))]})


def _genre_rows(mix: pd.DataFrame) -> pd.Series:
    """The mix as GENRE_ROWS category observations, the form a category drift test needs."""
    counts = (mix["share"] * GENRE_ROWS).round().astype(int)
    return pd.Series(np.repeat(mix["genre"].to_numpy(), counts.to_numpy()), name="genre", dtype=object)


def _wide(frames: dict[str, pd.DataFrame], side: str) -> pd.DataFrame:
    """The genre rows and taste rows of one side in one frame, padded with NaN to the same length."""
    parts = [_genre_rows(frames[f"genre_mix_{side}"]).to_frame(), frames[f"taste_{side}"].reset_index(drop=True)]
    out = pd.concat(parts, axis=1)
    return out.assign(**{c: v for c, v in joint_like(frames["watched"]).iloc[0].items()} if side == "now" else
                      {"joint_like_rate": np.nan, "watched_count": np.nan})


def ensure_project(ws, name: str):
    """Finds the evidently project or creates it, and adds the dashboard panels that are missing."""
    from evidently.sdk.models import PanelMetric
    from evidently.sdk.panels import counter_panel, line_plot_panel

    found = ws.search_project(name)
    project = found[0] if found else ws.create_project(name, description="Joint thumbs-up rate and drift of the couple recommender")
    existing = {p.title for p in ws.get_dashboard(project.id).panels}
    if JOINT_PANEL not in existing:
        rate = PanelMetric(legend="joint thumbs-up rate", metric="MeanValue", metric_labels={"column": "joint_like_rate"})
        project.dashboard.add_panel(counter_panel(title=JOINT_PANEL, values=[rate], aggregation="last", size="half"))
    if WATCHED_PANEL not in existing:
        count = PanelMetric(legend="watched", metric="MeanValue", metric_labels={"column": "watched_count"})
        project.dashboard.add_panel(counter_panel(title=WATCHED_PANEL, values=[count], aggregation="last", size="half"))
    if DRIFT_PANEL not in existing:
        share = PanelMetric(legend="share", metric="DriftedColumnsCount", metric_labels={"value_type": "share"})
        project.dashboard.add_panel(line_plot_panel(title=DRIFT_PANEL, values=[share]))
    return project


def build_snapshot(frames: dict[str, pd.DataFrame]):
    """The Evidently snapshot of one weekly run, built locally without any upload."""
    from evidently import DataDefinition, Dataset, Report
    from evidently.metrics import MeanValue
    from evidently.presets import DataDriftPreset

    now, before = _wide(frames, "now"), _wide(frames, "before")
    taste = [c for c in now.columns if c.startswith("d") and c[1:].isdigit()]
    definition = DataDefinition(categorical_columns=["genre"], numerical_columns=[*taste, "joint_like_rate", "watched_count"])
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        return Report([MeanValue(column="joint_like_rate"), MeanValue(column="watched_count"),
                       DataDriftPreset(columns=["genre", *taste])]).run(
            Dataset.from_pandas(now, data_definition=definition),
            Dataset.from_pandas(before, data_definition=definition),
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
            tags=["weekly"], metadata={"watched_count": str(len(frames["watched"]))})


def report(frames: dict[str, pd.DataFrame], evidently_url: str, project: str = PROJECT) -> None:
    """Uploads one snapshot: the joint thumbs-up rate plus drift of the genre mix and of both tastes."""
    from evidently.ui.workspace import RemoteWorkspace

    snapshot = build_snapshot(frames)
    ws = RemoteWorkspace(evidently_url)
    ws.add_run(ensure_project(ws, project).id, snapshot, include_data=False)


def run(evidently_url: str) -> dict[str, pd.DataFrame]:
    """Reads events, catalogs and the champion from Garage and MLflow, then reports one weekly snapshot."""
    import tempfile

    import mlflow
    from mlflow import MlflowClient

    from recommender import s3
    from recommender.config import ALIAS, MODEL_NAME

    events = [Event.from_json(s3.client().get_object(Bucket="recommender", Key=k)["Body"].read().decode())
              for k in s3.list_keys("feedback/events/") if k.endswith(".json")]
    features = s3.read_parquet("features/movies.parquet")
    version = MlflowClient().get_model_version_by_alias(MODEL_NAME, ALIAS)
    with tempfile.TemporaryDirectory() as tmp:
        path = mlflow.artifacts.download_artifacts(f"runs:/{version.run_id}/arrays/arrays.npz", dst_path=tmp)
        with np.load(path) as z:
            bias = float(z["global_bias"])
    now = datetime.now(timezone.utc)
    before_key = pick_history(s3.list_keys(HISTORY), now.astimezone(KST).date())
    catalog_now = s3.read_parquet("catalog/movies.parquet")
    frames = weekly_frames(events, catalog_now, s3.read_parquet(before_key) if before_key else catalog_now,
                           taste_vectors(events, features, bias), taste_vectors(events, features, bias, now - WINDOW))
    report(frames, evidently_url)
    print(f"reported: {len(frames['watched'])} watched, catalog before {before_key or 'none (self)'}")
    return frames
