# In-cluster seed for the ML lab: uploads the example datasets to Garage, registers Feast features and fills the online store
import os
import shutil
import subprocess
import sys
import urllib.request
from pathlib import Path

import boto3

# Upstream example data, pinned to one commit so every lab gets the same 30,162 users
DATA = "https://raw.githubusercontent.com/practical-mlops/chapter-4/b67a8228336781c933dd68bb7dc520bd484c3371/feast"
GARAGE = "http://garage.gitlab.svc.cluster.local:3900"
VALKEY = "valkey.gitlab.svc.cluster.local:6379"
# Mac-side addresses of the same services, opened by labs/ml/feast/pf.sh
MAC_GARAGE = "http://localhost:3900"
MAC_VALKEY = "localhost:16379"
WINDOW = ("2022-09-16T00:00:00", "2023-09-17T00:00:00")


def s3():
    return boto3.client("s3", endpoint_url=GARAGE, region_name="garage")


def upload_from_upstream(path: str, bucket: str, key: str) -> None:
    local = Path("/tmp") / Path(path).name
    urllib.request.urlretrieve(f"{DATA}/{path}", local)
    s3().upload_file(str(local), bucket, key)
    print(f"uploaded s3://{bucket}/{key} ({local.stat().st_size} bytes)")


def store_yaml(registry: str, redis: str) -> str:
    return "\n".join([
        "project: my_feature_repo",
        f"registry: s3://feature-registry/{registry}",
        "provider: local",
        "offline_store:",
        "  type: file",
        "online_store:",
        "  type: redis",
        f'  connection_string: "{redis}"',
        "",
    ])


def feast(repo: Path, *args: str, source_endpoint: str) -> None:
    env = {**os.environ, "FEAST_SOURCE_S3_ENDPOINT": source_endpoint}
    subprocess.run(["feast", *args], cwd=repo, env=env, check=True)


def seed_features() -> None:
    for name in ("demographic", "occupational", "relationship"):
        upload_from_upstream(f"feature_data/{name}_features.parquet", "feature-data-sets", f"{name}_features.parquet")

    # The Secret feast-online-store holds the operator's YAML snippet; the password is its last connection option
    password = os.environ["FEAST_ONLINE_STORE"].split("password=", 1)[1].strip()
    cluster_redis = f"{VALKEY},db=1,password={password}"
    mac_redis = f"{MAC_VALKEY},db=1,password={password}"
    repo = Path("/tmp/feature_repo")
    repo.mkdir(exist_ok=True)
    shutil.copy("/seed/definitions.py", repo / "definitions.py")

    # registry_local.db is read by the Mac and the online server; registry_cluster.db by pipeline pods
    for registry, endpoint in (("registry_local.db", MAC_GARAGE), ("registry_cluster.db", GARAGE)):
        (repo / "feature_store.yaml").write_text(store_yaml(registry, cluster_redis))
        feast(repo, "apply", "--skip-source-validation", source_endpoint=endpoint)
    feast(repo, "materialize", *WINDOW, source_endpoint=GARAGE)

    client = s3()
    for name, registry, redis in (("feature_store_cluster.yaml", "registry_cluster.db", cluster_redis),
                                  ("feature_store_local.yaml", "registry_local.db", mac_redis)):
        client.put_object(Bucket="feature-registry", Key=name, Body=store_yaml(registry, redis).encode())
        print(f"uploaded s3://feature-registry/{name}")

    import redis as redis_lib

    host, port = VALKEY.split(":")
    keys = redis_lib.Redis(host=host, port=int(port), db=1, password=password).dbsize()
    print(f"online store keys in Valkey db 1: {keys}")


def seed_inference() -> None:
    upload_from_upstream("data/entity_df.parquet", "inference-datasets", "entity_df.parquet")


if __name__ == "__main__":
    {"features": seed_features, "inference": seed_inference}[sys.argv[1]]()
