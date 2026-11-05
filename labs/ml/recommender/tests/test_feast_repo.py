# Tests for the Feast repository: the generated config, and that the feature definitions apply and match their writers
import importlib.util
import sys
from datetime import timedelta
from pathlib import Path

import pytest
import yaml
from feast import FeatureStore, FileSource

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import feast_config  # noqa: E402
from recommender import movie_features  # noqa: E402


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


def _apply_locally(tmp_path, monkeypatch, features):
    # Apply would otherwise open the s3:// parquet files to validate them, and this test has no network
    monkeypatch.setattr(FileSource, "validate", lambda self, config: None)
    (tmp_path / "feature_store.yaml").write_text(yaml.safe_dump({
        "project": "movie_recommender", "registry": str(tmp_path / "registry.db"), "provider": "local",
        "online_store": {"type": "sqlite", "path": str(tmp_path / "online.db")},
        "offline_store": {"type": "file"}, "entity_key_serialization_version": 3,
    }))
    store = FeatureStore(repo_path=str(tmp_path))
    store.apply(features.DEFINITIONS)
    return store


def test_definitions_apply_to_a_local_registry_and_sqlite_online_store(tmp_path, monkeypatch):
    store = _apply_locally(tmp_path, monkeypatch, _definitions())
    assert {v.name for v in store.list_feature_views()} == {
        "movie_catalog", "movie_popularity", "movie_embedding", "viewer_taste"}
    fields = {v.name: {f.name for f in v.features} for v in store.list_feature_views()}
    assert fields["movie_catalog"] == {"title", "services", "genres", "release_year", "korean", "new_this_week",
                                       "poster_url"}
    assert fields["movie_popularity"] == {"popularity_kr"}
    assert fields["movie_embedding"] == {"vector", "bias", "model_version"}
    assert fields["viewer_taste"] == {"vector", "updated_at"}


def test_each_movie_view_reads_the_parquet_its_writer_fills_with_the_same_columns():
    features = _definitions()
    for view in features.MOVIE_VIEWS:
        assert view.batch_source.path == f"s3://recommender/{movie_features.key(view.name)}"
        assert view.batch_source.timestamp_field == "event_timestamp"
        assert [f.name for f in view.features] == movie_features.COLUMNS[view.name]
    assert [v.name for v in features.MOVIE_VIEWS] == list(movie_features.COLUMNS)


def test_movie_view_ttls_follow_how_often_each_parquet_is_rewritten():
    features = _definitions()
    ttl = {v.name: v.ttl for v in features.MOVIE_VIEWS}
    # Popularity is daily and expires first; the champion's placement holds until it is replaced
    assert ttl["movie_popularity"] < ttl["movie_catalog"] < ttl["movie_embedding"]
    assert ttl["movie_popularity"] >= timedelta(days=1)
