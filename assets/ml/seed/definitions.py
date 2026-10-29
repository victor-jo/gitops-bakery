# Feast definitions for the income lab: one user entity and three feature views over parquet files in Garage
import os
from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource, ValueType
from feast.data_format import ParquetFormat
from feast.types import String

# The same views are registered twice: once with the Mac's tunnel address, once with Garage's in-cluster address
S3_ENDPOINT = os.environ.get("FEAST_SOURCE_S3_ENDPOINT", "http://localhost:3900")

# Type and timestamp column are stated so `feast apply` never has to open the parquet files to infer them
user = Entity(name="user_id", value_type=ValueType.STRING)


def parquet(name: str) -> FileSource:
    return FileSource(
        file_format=ParquetFormat(),
        path=f"s3://feature-data-sets/{name}_features.parquet",
        s3_endpoint_override=S3_ENDPOINT,
        timestamp_field="feature_timestamp",
    )


def view(name: str, source: str, fields: list[str]) -> FeatureView:
    return FeatureView(
        name=name,
        entities=[user],
        schema=[Field(name=f, dtype=String) for f in fields],
        ttl=timedelta(days=365),
        source=parquet(source),
    )


demographic = view("demographic", "demographic", ["Native_country", "Sex", "Race"])
relationship = view("relationship", "relationship", ["Relationship", "Marital-Status"])
occupation = view("occupation", "occupational", ["Workclass", "Education", "Occupation"])
