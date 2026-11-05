# Tests for precision/recall at k and AUC helpers
import pytest

from recommender.model.evaluate import auc, precision_recall_at_k


def test_precision_recall_at_k_two_users():
    # (score, true_label); a user is judged on its top-k by score, relevant = label >= threshold
    scores = {
        0: [(0.9, 1.0), (0.8, 0.0), (0.7, 1.0), (0.1, 1.0)],  # top2: 1 hit; 3 relevant -> P=.5 R=1/3
        1: [(0.9, 0.0), (0.5, 1.0)],                            # top2: 1 hit; 1 relevant -> P=.5 R=1
    }
    p, r = precision_recall_at_k(scores, k=2)
    assert p == pytest.approx(0.5)
    assert r == pytest.approx((1 / 3 + 1) / 2)


def test_precision_recall_skips_users_without_relevant_items():
    p, r = precision_recall_at_k({0: [(0.9, 0.0)], 1: [(0.9, 1.0)]}, k=1)
    assert (p, r) == (1.0, 1.0)


def test_auc():
    assert auc([0, 0, 1, 1], [0.1, 0.2, 0.8, 0.9]) == 1.0
