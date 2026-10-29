# Reads income features from the Mac: a historical row from the parquet files in Garage, then the same user's online row from Valkey
import os
from pathlib import Path

import boto3
import pandas as pd
from feast import FeatureStore

GARAGE = "http://localhost:3900"
FEATURES = ["demographic:Sex", "demographic:Race", "relationship:Marital-Status", "occupation:Occupation"]
USER = "74b0638a-5742-4d1a-a03f-483794d7aa7c"

# Credentials come from feast/feast-s3 (see the README); Garage and Valkey are reached through the pf.sh tunnels
os.environ.setdefault("FEAST_S3_ENDPOINT_URL", GARAGE)
# Garage signs with its own region; the registry client would otherwise sign for us-east-1 and be refused
os.environ.setdefault("AWS_DEFAULT_REGION", "garage")
repo = Path(__file__).parent / "repo"
repo.mkdir(exist_ok=True)
# The seed Job stored a client config whose registry and online store point at those tunnels
boto3.client("s3", endpoint_url=GARAGE, region_name="garage").download_file(
    "feature-registry", "feature_store_local.yaml", str(repo / "feature_store.yaml"))
store = FeatureStore(repo_path=str(repo))

entities = pd.DataFrame({"user_id": [USER], "event_timestamp": [pd.Timestamp("2023-09-01", tz="UTC")]})
print("----- historical -----")
print(store.get_historical_features(entity_df=entities, features=FEATURES).to_df().T)
print("----- online -----")
print(store.get_online_features(entity_rows=[{"user_id": USER}], features=FEATURES).to_df().T)
