# Feast entities, feature views and the push source for the movie recommender
"""File-source endpoints are read from FEAST_S3_ENDPOINT_URL at apply time and stored in the registry.

A process that reaches Garage at a different address must re-apply with its own env before materializing.
"""
import os
from datetime import timedelta

from feast import Entity, FeatureView, Field, FileSource, PushSource
from feast.value_type import ValueType
from feast.types import Array, Bool, Float32, Float64, Int64, String, UnixTimestamp

# Garage is reached through a tunnel from the Mac, so the S3 endpoint comes from the environment (unset means AWS)
S3_ENDPOINT = os.environ.get("FEAST_S3_ENDPOINT_URL")

movie = Entity(name="movie", join_keys=["movie_key"], value_type=ValueType.STRING)
viewer = Entity(name="viewer", join_keys=["viewer_id"], value_type=ValueType.STRING)


def _movie_source(name: str) -> FileSource:
    return FileSource(
        name=f"{name}_parquet",
        path=f"s3://recommender/features/{name}.parquet",
        timestamp_field="event_timestamp",
        s3_endpoint_override=S3_ENDPOINT,
    )


# The movie features are split by who writes them and how often, each view backed by its own parquet.
# The catalog run rewrites this one daily; services and new_this_week go stale within a week.
movie_catalog = FeatureView(
    name="movie_catalog",
    entities=[movie],
    ttl=timedelta(days=7),
    schema=[
        Field(name="title", dtype=String),
        Field(name="services", dtype=Array(String)),
        Field(name="genres", dtype=Array(String)),
        Field(name="release_year", dtype=Int64),
        Field(name="korean", dtype=Bool),
        Field(name="new_this_week", dtype=Bool),
        Field(name="poster_url", dtype=String),
        Field(name="description", dtype=String),
        Field(name="actors", dtype=Array(String)),
    ],
    source=_movie_source("movie_catalog"),
)

# Korean popularity is a daily signal from the catalog run, so it may outlive one missed run but not more
movie_popularity = FeatureView(
    name="movie_popularity",
    entities=[movie],
    ttl=timedelta(days=2),
    schema=[Field(name="popularity_kr", dtype=Float64)],
    source=_movie_source("movie_popularity"),
)

# The training run places the catalog with the champion; the rows stay valid until another champion replaces them
movie_embedding = FeatureView(
    name="movie_embedding",
    entities=[movie],
    ttl=timedelta(days=3650),
    schema=[
        Field(name="vector", dtype=Array(Float32)),
        Field(name="bias", dtype=Float64),
        Field(name="model_version", dtype=String),
    ],
    source=_movie_source("movie_embedding"),
)

MOVIE_VIEWS = [movie_catalog, movie_popularity, movie_embedding]

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

# Everything apply registers, in dependency order
DEFINITIONS = [movie, viewer, *MOVIE_VIEWS, viewer_taste]
