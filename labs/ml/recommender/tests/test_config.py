# Pins the recommender constants so a threshold change is a deliberate edit
from recommender import config


def test_constants_match_spec():
    assert config.VETO_P == 0.35
    assert config.STRONG_DISLIKE_P == 0.20
    assert config.PAGE_SIZE == 20
    assert config.LIKE_RATING == 4.0
    assert config.VIEWERS == {"me": "나", "wife": "아내"}
    assert config.SERVICES == {"nfx": "Netflix", "dnp": "Disney+", "cou": "Coupang Play"}
    assert config.BUCKET == "recommender"
    assert config.VALKEY_DB == 2
    assert config.MODEL_NAME == "movie-recommender"
    assert config.ALIAS == "champion"
