# Shared constants of the movie recommender: thresholds, viewers, services and lab resource names
VETO_P = 0.35
STRONG_DISLIKE_P = 0.20
MIN_RESULTS = 5
MAX_RESULTS = 10
LIKE_RATING = 4.0

VIEWERS: dict[str, str] = {"me": "나", "wife": "아내"}
SERVICES: dict[str, str] = {"nfx": "Netflix", "dnp": "Disney+", "cou": "Coupang Play"}

BUCKET = "recommender"
VALKEY_DB = 2
MODEL_NAME = "movie-recommender"
ALIAS = "champion"
