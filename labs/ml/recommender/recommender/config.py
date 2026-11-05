# Shared constants of the movie recommender: thresholds, viewers, services and lab resource names
VETO_P = 0.35
STRONG_DISLIKE_P = 0.20
# Movies per page of /api/recommendations when the caller does not ask for a size
PAGE_SIZE = 20
LIKE_RATING = 4.0
# Newer releases rank higher: a movie from this year gets RECENCY_BONUS × its Korean popularity (0..1)
# added to its ranking score, fading linearly to nothing for movies RECENCY_YEARS or more years old.
# The veto ignores it.
RECENCY_YEARS = 5
RECENCY_BONUS = 0.33
# Korean films (Hangul original title) get this added to their ranking score; the veto ignores it too
KOREAN_BONUS = 0.2

VIEWERS: dict[str, str] = {"me": "나", "wife": "아내"}
SERVICES: dict[str, str] = {"nfx": "Netflix", "dnp": "Disney+", "cou": "Coupang Play"}

BUCKET = "recommender"
VALKEY_DB = 2
MODEL_NAME = "movie-recommender"
ALIAS = "champion"
