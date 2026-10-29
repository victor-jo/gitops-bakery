# Business logic of the four income-inference steps; the KFP components in components.py are thin wrappers around it
import os
import pickle
from pathlib import Path

import pandas as pd


def _minio_client():
    from minio import Minio

    # Garage signs with its own region, so it is passed explicitly instead of the client's us-east-1 default
    return Minio(
        os.environ["S3_ENDPOINT"],
        access_key=os.environ["AWS_ACCESS_KEY_ID"],
        secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        secure=False,
        region=os.environ.get("S3_REGION"),
    )


def read_entities(bucket: str, key: str, out_path: str) -> int:
    local = Path("/tmp") / Path(key).name
    _minio_client().fget_object(bucket, key, str(local))
    df = pd.read_parquet(local)
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    return len(df)


def retrieve_features(entities_path: str, config_bucket: str, config_key: str, feature_list: str, out_path: str) -> int:
    from feast import FeatureStore

    # The feature repo is just the feature_store.yaml; definitions come from the registry it points to
    repo = Path("/tmp/feature_repo")
    repo.mkdir(parents=True, exist_ok=True)
    _minio_client().fget_object(config_bucket, config_key, str(repo / "feature_store.yaml"))
    store = FeatureStore(repo_path=str(repo))
    entity_df = pd.read_parquet(entities_path)
    features = store.get_historical_features(entity_df=entity_df, features=feature_list.split(",")).to_df()
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    features.to_parquet(out_path)
    return len(features)


def run_inference(features_path: str, model_name: str, model_alias: str, out_path: str) -> int:
    import mlflow
    from mlflow import MlflowClient

    client = MlflowClient()
    # Registry stages are deprecated since MLflow 2.9, so the serving version is picked by alias
    version = client.get_model_version_by_alias(model_name, model_alias)
    columns_dir = mlflow.artifacts.download_artifacts(f"runs:/{version.run_id}/column_list.pkl", dst_path="/tmp/columns")
    with open(columns_dir, "rb") as f:
        columns = pickle.load(f)

    df = pd.read_parquet(features_path).drop(columns=["user_id", "event_timestamp"])
    df = pd.get_dummies(df, drop_first=True, sparse=False, dtype=float).reindex(columns=columns, fill_value=0)
    model = mlflow.sklearn.load_model(f"models:/{model_name}@{model_alias}")
    df["Predicted_Income_Class"] = [p[1] for p in model.predict_proba(df)]
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(out_path)
    return len(df)


def write_predictions(predictions_path: str, bucket: str, key: str) -> int:
    df = pd.read_parquet(predictions_path)
    local = Path("/tmp") / Path(key).name
    df.to_parquet(local, index=False)
    _minio_client().fput_object(bucket, key, str(local))
    return len(df)
