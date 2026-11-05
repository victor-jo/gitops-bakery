# Tests for the Feast repository: the generated config and that the feature definitions apply to a local store
import importlib.util
import sys
from pathlib import Path

import pytest
import yaml
from feast import FeatureStore, FileSource

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import feast_config  # noqa: E402


def _definitions():
    spec = importlib.util.spec_from_file_location("features", ROOT / "feature_repo" / "features.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_write_config_moves_the_online_store_to_db_2(tmp_path):
    path = feast_config.write_config(tmp_path, "localhost:16379,db=1,password=x")
    config = yaml.safe_load(path.read_text())
    assert config["project"] == "movie_recommender"
    assert config["online_store"]["type"] == "redis"
    assert config["online_store"]["connection_string"] == "localhost:16379,db=2,password=x"
    assert config["registry"] == "s3://recommender/feast/registry.db"


def test_write_config_rejects_a_connection_without_the_db_1_token(tmp_path):
    with pytest.raises(ValueError):
        feast_config.write_config(tmp_path, "localhost:16379,db=2,password=x")


def test_write_config_only_replaces_the_exact_db_1_token(tmp_path):
    path = feast_config.write_config(tmp_path, "localhost:16379,db=1,password=db=1x,prefix=db=10")
    conn = yaml.safe_load(path.read_text())["online_store"]["connection_string"]
    assert conn == "localhost:16379,db=2,password=db=1x,prefix=db=10"


def test_write_config_can_swap_the_valkey_host(tmp_path):
    path = feast_config.write_config(tmp_path, "localhost:16379,db=1,password=x", valkey_host="host.docker.internal:16379")
    conn = yaml.safe_load(path.read_text())["online_store"]["connection_string"]
    assert conn == "host.docker.internal:16379,db=2,password=x"


def test_definitions_apply_to_a_local_registry_and_sqlite_online_store(tmp_path, monkeypatch):
    # Apply would otherwise open the s3:// parquet files to validate them, and this test has no network
    monkeypatch.setattr(FileSource, "validate", lambda self, config: None)
    features = _definitions()
    (tmp_path / "feature_store.yaml").write_text(yaml.safe_dump({
        "project": "movie_recommender", "registry": str(tmp_path / "registry.db"), "provider": "local",
        "online_store": {"type": "sqlite", "path": str(tmp_path / "online.db")},
        "offline_store": {"type": "file"}, "entity_key_serialization_version": 3,
    }))
    store = FeatureStore(repo_path=str(tmp_path))
    store.apply([features.movie, features.viewer, features.movie_features, features.viewer_taste])
    assert {v.name for v in store.list_feature_views()} == {"movie_features", "viewer_taste"}
    movie_fields = {f.name for f in store.get_feature_view("movie_features").features}
    assert movie_fields == {"title", "services", "genres", "popularity_kr", "new_this_week", "vector", "bias", "poster_url"}
    assert {f.name for f in store.get_feature_view("viewer_taste").features} == {"vector", "updated_at"}
