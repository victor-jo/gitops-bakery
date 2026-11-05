# Shared constants of the movie recommender: thresholds, viewers, services and lab resource names
VETO_P = 0.35
STRONG_DISLIKE_P = 0.20
# Movies per page of /api/recommendations when the caller does not ask for a size
PAGE_SIZE = 20
# A movie needs at least this content similarity to a liked movie to appear under that movie's tab
SIMILAR_MIN = 0.3
LIKE_RATING = 4.0
# Newer releases rank higher: a movie from this year gets RECENCY_BONUS × its Korean popularity (0..1)
# added to its ranking score, fading linearly to nothing for movies RECENCY_YEARS or more years old.
# The veto ignores it.
RECENCY_YEARS = 5
RECENCY_BONUS = 0.33
# Korean films (Hangul original title) get this added to their ranking score; the veto ignores it too
KOREAN_BONUS = 0.2
# Within a year, a movie's review rating (0..1) above or below the catalog mean adds or takes RATING_BONUS ×
# the difference; an unrated movie gets nothing. Live, min(p) among picks has an IQR of 0.035 and the review
# rating about 0.09, so 0.5 lets reviews move the order about as much as taste does, and less than KOREAN_BONUS.
# The veto ignores it.
RATING_BONUS = 0.5

VIEWERS: dict[str, str] = {"me": "나", "wife": "아내"}
SERVICES: dict[str, str] = {"nfx": "Netflix", "dnp": "Disney+", "cou": "Coupang Play"}

BUCKET = "recommender"
VALKEY_DB = 2
MODEL_NAME = "movie-recommender"
ALIAS = "champion"
