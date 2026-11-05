# BentoML service: serves the phone UI and recommender API over Garage events, the champion model and Feast
from __future__ import annotations

import importlib.util
import json
import logging
import os
import shutil
import tempfile
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import bentoml
import numpy as np
import pandas as pd
from fastapi import FastAPI

from recommender import s3
from recommender.config import ALIAS, BUCKET, MODEL_NAME
from recommender.core.state import Event
from serving.api import create_app

ROOT = Path(__file__).resolve().parent.parent
FEATURES = "features/movies.parquet"
FEEDBACK = "feedback/events/"
REFRESH_SECONDS = 6 * 3600

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Settings:
    mlflow_tracking_uri: str
    evidently_url: str
    s3_endpoint: str  # host:port of Garage
    valkey_address: str  # host:port of Valkey as this process reaches it

    @classmethod
    def from_env(cls) -> "Settings":
        names = ("MLFLOW_TRACKING_URI", "EVIDENTLY_URL", "S3_ENDPOINT", "VALKEY_ADDRESS")
        missing = [n for n in names if not os.environ.get(n)]
        if missing:
            raise RuntimeError(f"missing required environment variable(s): {', '.join(missing)}")
        return cls(*(os.environ[n] for n in names))


def event_key(event: Event) -> str:
    """Object key of one feedback event; time first so keys list in event order."""
    at = event.at.astimezone(timezone.utc)
    return f"{FEEDBACK}{at:%Y-%m-%dT%H%M%S.%fZ}-{uuid.uuid4().hex}.json"


def champion_global_bias() -> float:
    import mlflow
    from mlflow import MlflowClient

    version = MlflowClient().get_model_version_by_alias(MODEL_NAME, ALIAS)
    with tempfile.TemporaryDirectory() as tmp:
        path = mlflow.artifacts.download_artifacts(f"runs:/{version.run_id}/arrays/arrays.npz", dst_path=tmp)
        with np.load(path) as z:
            return float(z["global_bias"])


def feature_store(settings: Settings, repo_dir: Path):
    """Write this process's Feast config and re-apply the definitions so file sources carry its Garage endpoint."""
    from feast import FeatureStore

    import feast_config

    feast_config.write_config(repo_dir, feast_config.seeded_connection(), valkey_host=settings.valkey_address)
    shutil.copy(ROOT / "feature_repo" / "features.py", repo_dir)
    store = FeatureStore(repo_path=str(repo_dir))
    spec = importlib.util.spec_from_file_location("features", repo_dir / "features.py")
    defs = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(defs)  # reads FEAST_S3_ENDPOINT_URL, so the env must be set before this
    store.apply([defs.movie, defs.viewer, defs.movie_features, defs.viewer_taste])
    return store


class LiveStore:
    """The api Store over Garage (events, catalog), MLflow (global bias) and Feast (taste vectors, movie features)."""

    def __init__(self, settings: Settings):
        os.environ["FEAST_S3_ENDPOINT_URL"] = f"http://{settings.s3_endpoint}"
        os.environ.setdefault("AWS_DEFAULT_REGION", "garage")
        self.repo_dir = Path(tempfile.mkdtemp(prefix="feast-"))
        self.feast = feature_store(settings, self.repo_dir)
        self.reload()

    def reload(self) -> None:
        """Load the placed catalog with the champion's global bias, then materialize the movie features."""
        catalog, gb = s3.read_parquet(FEATURES), champion_global_bias()
        self._snapshot = (catalog, gb)  # one assignment, so readers never see a mixed pair
        self.feast.materialize_incremental(end_date=datetime.now(timezone.utc), feature_views=["movie_features"])
        log.info("catalog loaded: %d movies, global bias %.4f", len(catalog), gb)

    def catalog(self) -> pd.DataFrame:
        return self._snapshot[0]

    def global_bias(self) -> float:
        return self._snapshot[1]

    def append(self, event: Event) -> None:
        s3.put_json(json.loads(event.to_json()), event_key(event))

    def events(self) -> list[Event]:
        bucket = s3.client()
        out = []
        for key in s3.list_keys(FEEDBACK):
            if key.endswith(".json"):
                out.append(Event.from_json(bucket.get_object(Bucket=BUCKET, Key=key)["Body"].read().decode()))
        return out

    def push_taste(self, viewer: str, vector: np.ndarray) -> None:
        row = pd.DataFrame({"viewer_id": [viewer], "vector": [np.asarray(vector, np.float32).tolist()],
                            "updated_at": [pd.Timestamp.now(tz="UTC")]})
        self.feast.push("viewer_taste_push", row)

    def taste(self, viewer: str) -> np.ndarray | None:
        got = self.feast.get_online_features(features=["viewer_taste:vector"],
                                             entity_rows=[{"viewer_id": viewer}]).to_dict()["vector"][0]
        return None if got is None else np.asarray(got, np.float32)


def start_refresh(store: LiveStore, every: float = REFRESH_SECONDS) -> None:
    """Reload the catalog and re-materialize on a timer; a failed round keeps the previous catalog."""

    def loop() -> None:
        while True:
            time.sleep(every)
            try:
                store.reload()
            except Exception:
                log.exception("catalog refresh failed; keeping the previous catalog")

    threading.Thread(target=loop, name="catalog-refresh", daemon=True).start()


# The real API is mounted inside this shell once the store is up; its own docs routes stay off so BentoML's show
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


# One worker: the couple's state and taste vectors live in this process
@bentoml.service(name="movie_recommender", workers=1)
@bentoml.asgi_app(app, path="/")
class MovieRecommender:
    def __init__(self) -> None:
        store = LiveStore(Settings.from_env())
        app.mount("/", create_app(store))
        start_refresh(store)
