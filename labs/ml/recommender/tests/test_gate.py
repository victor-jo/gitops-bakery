# Tests for the promotion gate that decides whether a new model replaces the champion
import pytest

from recommender.model.gate import should_promote

CHAMPION = {"val_auc": 0.80, "precision_10": 0.30, "recall_10": 0.20, "couple_auc": 0.66}


def _new(**overrides):
    metrics = {"val_auc": 0.80, "precision_10": 0.30, "recall_10": 0.20, "couple_auc": 0.70}
    metrics.update(overrides)
    return metrics


def test_no_champion_promotes():
    ok, reason = should_promote(_new(), None, couple_holdout_size=0)
    assert ok is True
    assert reason == "no champion"


def test_all_gates_passed():
    ok, reason = should_promote(_new(), CHAMPION, couple_holdout_size=20)
    assert ok is True
    assert reason == "all gates passed"


def test_val_auc_drop_rejects():
    ok, reason = should_promote(_new(val_auc=0.7929), CHAMPION, couple_holdout_size=0)
    assert ok is False
    assert reason.startswith("val_auc dropped by")


def test_val_auc_drop_exactly_at_threshold_passes():
    ok, _ = should_promote(_new(val_auc=0.795), CHAMPION, couple_holdout_size=0)
    assert ok is True


def test_precision_10_drop_rejects():
    ok, reason = should_promote(_new(precision_10=0.2877), CHAMPION, couple_holdout_size=0)
    assert ok is False
    assert reason.startswith("precision_10 dropped by")


def test_precision_10_drop_exactly_at_threshold_passes():
    ok, _ = should_promote(_new(precision_10=0.29), CHAMPION, couple_holdout_size=0)
    assert ok is True


def test_couple_auc_below_champion_rejects():
    ok, reason = should_promote(_new(couple_auc=0.61), CHAMPION, couple_holdout_size=10)
    assert ok is False
    assert reason.startswith("couple_auc")


def test_couple_auc_equal_to_champion_passes():
    ok, _ = should_promote(_new(couple_auc=0.66), CHAMPION, couple_holdout_size=10)
    assert ok is True


def test_couple_auc_ignored_with_9_holdout_rows():
    ok, reason = should_promote(_new(couple_auc=0.10), CHAMPION, couple_holdout_size=9)
    assert ok is True
    assert reason == "all gates passed"


def test_couple_rule_skipped_when_champion_has_no_couple_auc():
    champion = {"val_auc": 0.80, "precision_10": 0.30, "recall_10": 0.20}
    ok, reason = should_promote(_new(couple_auc=0.10), champion, couple_holdout_size=50)
    assert ok is True
    assert reason == "all gates passed"


def test_missing_couple_auc_in_new_with_enough_holdout_raises():
    new = _new()
    del new["couple_auc"]
    with pytest.raises(KeyError):
        should_promote(new, CHAMPION, couple_holdout_size=10)


def test_missing_couple_auc_in_new_raises_even_when_champion_lacks_it():
    champion = {"val_auc": 0.80, "precision_10": 0.30, "recall_10": 0.20}
    new = _new()
    del new["couple_auc"]
    with pytest.raises(KeyError):
        should_promote(new, champion, couple_holdout_size=10)


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_val_auc_rejects(bad):
    ok, reason = should_promote(_new(val_auc=bad), CHAMPION, couple_holdout_size=0)
    assert ok is False
    assert reason == "val_auc is not finite"


@pytest.mark.parametrize("bad", [float("nan"), float("inf")])
def test_non_finite_precision_10_rejects(bad):
    ok, reason = should_promote(_new(precision_10=bad), CHAMPION, couple_holdout_size=0)
    assert ok is False
    assert reason == "precision_10 is not finite"


def test_non_finite_couple_auc_rejects_when_couple_rule_applies():
    ok, reason = should_promote(_new(couple_auc=float("nan")), CHAMPION, couple_holdout_size=10)
    assert ok is False
    assert reason == "couple_auc is not finite"


def test_non_finite_val_auc_rejects_without_champion():
    ok, reason = should_promote(_new(val_auc=float("nan")), None, couple_holdout_size=0)
    assert ok is False
    assert reason == "val_auc is not finite"


def test_non_finite_precision_10_rejects_without_champion():
    ok, reason = should_promote(_new(precision_10=float("nan")), None, couple_holdout_size=0)
    assert ok is False
    assert reason == "precision_10 is not finite"


def test_no_champion_missing_couple_auc_in_new_does_not_raise():
    new = _new()
    del new["couple_auc"]
    ok, reason = should_promote(new, None, couple_holdout_size=10)
    assert ok is True
    assert reason == "no champion"
