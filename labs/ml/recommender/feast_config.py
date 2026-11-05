# Builds the Feast config from the lab's seeded one (db 2) and applies/materializes the recommender features
import argparse
import importlib.util
import os
import shutil
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import boto3
import yaml

DEFAULT_GARAGE = "http://localhost:3900"
REPO = Path(__file__).parent / "feature_repo"


def write_config(dest_dir: Path, valkey_connection: str, registry: str = "s3://recommender/feast/registry.db",
                 valkey_host: str | None = None) -> Path:
    """Write feature_store.yaml with the online store moved from the seeded db=1 to db=2.

    valkey_host (host:port) replaces the seeded address for callers that reach Valkey elsewhere, e.g. from Docker.
    """
    parts = valkey_connection.split(",")
    if "db=1" not in parts[1:]:
        raise ValueError("seeded connection string has no db=1 token")
    parts = [("db=2" if i > 0 and p == "db=1" else p) for i, p in enumerate(parts)]
    if valkey_host:
        parts[0] = valkey_host
    config = {
        "project": "movie_recommender",
        "registry": registry,
        "provider": "local",
        "online_store": {"type": "redis", "connection_string": ",".join(parts)},
        "offline_store": {"type": "file"},
        "entity_key_serialization_version": 3,
    }
    path = Path(dest_dir) / "feature_store.yaml"
    path.write_text(yaml.safe_dump(config))
    return path


def seeded_connection() -> str:
    """Read the seeded Valkey connection string from Garage; it stays in memory."""
    endpoint = os.environ.get("FEAST_S3_ENDPOINT_URL", DEFAULT_GARAGE)
    s3 = boto3.client("s3", endpoint_url=endpoint, region_name="garage")
    body = s3.get_object(Bucket="feature-registry", Key="feature_store_local.yaml")["Body"].read()
    return yaml.safe_load(body)["online_store"]["connection_string"]


def apply() -> None:
    from feast import FeatureStore

    os.environ.setdefault("FEAST_S3_ENDPOINT_URL", DEFAULT_GARAGE)
    os.environ.setdefault("AWS_DEFAULT_REGION", "garage")
    with tempfile.TemporaryDirectory() as tmp:
        write_config(Path(tmp), seeded_connection())
        shutil.copy(REPO / "features.py", tmp)
        store = FeatureStore(repo_path=tmp)
        spec = importlib.util.spec_from_file_location("features", Path(tmp) / "features.py")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        store.apply([module.movie, module.viewer, module.movie_features, module.viewer_taste])
        print(f"applied: {len(store.list_entities())} entities, {len(store.list_feature_views())} feature views")
        store.materialize_incremental(end_date=datetime.now(timezone.utc), feature_views=["movie_features"])
        print("materialized: movie_features")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--apply", action="store_true")
    if parser.parse_args().apply:
        apply()
