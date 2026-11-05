# Feast entities, feature views and the push source for the movie recommender
"""File-source endpoints are read from FEAST_S3_ENDPOINT_URL at apply time and stored in the registry.

A process that reaches Garage at a different address must re-apply with its own env before materializing.
"""
import os
from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource, PushSource
from feast.value_type import ValueType
from feast.types import Array, Bool, Float32, Float64, String, UnixTimestamp

# Garage is reached through a tunnel from the Mac, so the S3 endpoint comes from the environment (unset means AWS)
S3_ENDPOINT = os.environ.get("FEAST_S3_ENDPOINT_URL")

movie = Entity(name="movie", join_keys=["movie_key"], value_type=ValueType.STRING)
viewer = Entity(name="viewer", join_keys=["viewer_id"], value_type=ValueType.STRING)

movies_source = FileSource(
    name="movies_parquet",
    path="s3://recommender/features/movies.parquet",
    timestamp_field="event_timestamp",
    s3_endpoint_override=S3_ENDPOINT,
)

# Placement rewrites the whole parquet each training run, so a long TTL keeps older rows servable
movie_features = FeatureView(
    name="movie_features",
    entities=[movie],
    ttl=timedelta(days=3650),
    schema=[
        Field(name="title", dtype=String),
        Field(name="services", dtype=Array(String)),
        Field(name="genres", dtype=Array(String)),
        Field(name="popularity_kr", dtype=Float64),
        Field(name="new_this_week", dtype=Bool),
        Field(name="vector", dtype=Array(Float32)),
        Field(name="bias", dtype=Float64),
        Field(name="poster_url", dtype=String),
    ],
    source=movies_source,
)

# Feedback pushes land here; the parquet is only the batch side of the push source
viewer_taste_push = PushSource(
    name="viewer_taste_push",
    batch_source=FileSource(
        name="viewer_taste_parquet",
        path="s3://recommender/feast/viewer_taste.parquet",
        timestamp_field="updated_at",
        s3_endpoint_override=S3_ENDPOINT,
    ),
)

viewer_taste = FeatureView(
    name="viewer_taste",
    entities=[viewer],
    ttl=timedelta(days=3650),
    schema=[
        Field(name="vector", dtype=Array(Float32)),
        Field(name="updated_at", dtype=UnixTimestamp),
    ],
    source=viewer_taste_push,
)
