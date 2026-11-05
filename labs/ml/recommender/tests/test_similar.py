# Tests for the content similarity behind the liked-movie filter tabs
import numpy as np
import pandas as pd
import pytest

from recommender.core.similar import content_matrix, similarity_to


def test_movies_sharing_genres_and_words_are_closer_than_unrelated_ones():
    df = pd.DataFrame({
        "title": ["토이 스토리", "토이 스토리 2", "대부", "Ta"],
        "description": ["장난감 카우보이 우디", "장난감 우디와 버즈", "마피아 가문의 이야기", None],
        "actors": [["톰 행크스"], ["톰 행크스"], np.array(["말론 브란도"], dtype=object), None],
        "genres": [["animation", "family"], ["animation", "family"], ["crime", "drama"], []],
    })
    sim = similarity_to(content_matrix(df), 0)
    assert sim[0] == pytest.approx(1.0)
    assert sim[1] > 0.5 > sim[2]
    assert sim[3] < sim[1]  # missing text and genres give a weak, finite similarity


def test_a_catalog_without_text_columns_still_works():
    df = pd.DataFrame({"title": ["a", "b"], "genres": [["drama"], ["drama"]]})
    assert similarity_to(content_matrix(df), 0)[1] > 0
