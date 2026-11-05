# Promotion gate deciding whether a newly trained model replaces the MLflow champion
VAL_AUC_MAX_DROP = 0.005
PRECISION_10_MAX_DROP = 0.01
COUPLE_MIN_HOLDOUT = 10
# Absorbs float error so a drop exactly equal to a threshold is not rejected
_EPS = 1e-9


def _dropped_beyond(name: str, champion_value: float, new_value: float, max_drop: float) -> str | None:
    """Reason string when the metric fell by more than max_drop, otherwise None."""
    drop = champion_value - new_value
    if drop - max_drop > _EPS:
        return f"{name} dropped by {drop:.4f} > {max_drop:g}"
    return None


def should_promote(
    new: dict[str, float], champion: dict[str, float] | None, couple_holdout_size: int
) -> tuple[bool, str]:
    """Decide whether `new` replaces `champion`; returns (promote, reason naming the deciding rule).

    The couple rule needs both models to have a couple AUC. An older champion without one
    skips that rule, but a missing couple_auc in `new` raises KeyError once the holdout is large enough.
    """
    if champion is None:
        return True, "no champion"

    reason = _dropped_beyond("val_auc", champion["val_auc"], new["val_auc"], VAL_AUC_MAX_DROP)
    if reason:
        return False, reason

    reason = _dropped_beyond("precision_10", champion["precision_10"], new["precision_10"], PRECISION_10_MAX_DROP)
    if reason:
        return False, reason

    if couple_holdout_size >= COUPLE_MIN_HOLDOUT:
        new_couple = new["couple_auc"]
        if "couple_auc" in champion and new_couple < champion["couple_auc"]:
            return False, f"couple_auc {new_couple:.4f} < champion {champion['couple_auc']:.4f}"

    return True, "all gates passed"
