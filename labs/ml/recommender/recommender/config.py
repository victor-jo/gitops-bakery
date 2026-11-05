# Shared constants of the movie recommender: thresholds, viewers, services and lab resource names
VETO_P = 0.35
STRONG_DISLIKE_P = 0.20
MIN_RESULTS = 5
MAX_RESULTS = 10
LIKE_RATING = 4.0
# Newer releases rank higher: a movie from this year gets RECENCY_BONUS added to its ranking score,
# fading linearly to nothing for movies RECENCY_YEARS or more years old. The veto ignores it.
RECENCY_YEARS = 5
RECENCY_BONUS = 0.15

VIEWERS: dict[str, str] = {"me": "나", "wife": "아내"}
SERVICES: dict[str, str] = {"nfx": "Netflix", "dnp": "Disney+", "cou": "Coupang Play"}

BUCKET = "recommender"
VALKEY_DB = 2
MODEL_NAME = "movie-recommender"
ALIAS = "champion"
