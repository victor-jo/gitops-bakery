# Thin boto3 helpers for reading and writing parquet/json objects in the Garage recommender bucket
import io
import json
import os

import boto3
import pandas as pd

from recommender.config import BUCKET


def client():
    """Build an S3 client for Garage from S3_ENDPOINT (host:port) and the AWS key env vars."""
    return boto3.client(
        "s3", endpoint_url=f"http://{os.environ['S3_ENDPOINT']}",
        aws_access_key_id=os.environ["AWS_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["AWS_SECRET_ACCESS_KEY"], region_name="garage")


def read_parquet(key: str) -> pd.DataFrame:
    body = client().get_object(Bucket=BUCKET, Key=key)["Body"].read()
    return pd.read_parquet(io.BytesIO(body))


def write_parquet(df: pd.DataFrame, key: str) -> None:
    buf = io.BytesIO()
    df.to_parquet(buf, index=False)
    client().put_object(Bucket=BUCKET, Key=key, Body=buf.getvalue())


def put_json(obj, key: str) -> None:
    client().put_object(Bucket=BUCKET, Key=key, Body=json.dumps(obj, ensure_ascii=False).encode(),
                        ContentType="application/json")


def list_keys(prefix: str) -> list[str]:
    """Return every key under prefix, following pagination."""
    s3 = client()
    keys: list[str] = []
    token = None
    while True:
        kw = {"Bucket": BUCKET, "Prefix": prefix}
        if token:
            kw["ContinuationToken"] = token
        resp = s3.list_objects_v2(**kw)
        keys += [o["Key"] for o in resp.get("Contents", [])]
        token = resp.get("NextContinuationToken")
        if not token:
            return keys
