# Ranking and classification metrics for the movie recommender
import numpy as np
from sklearn.metrics import roc_auc_score


def precision_recall_at_k(
    scores_by_user: dict[int, list[tuple[float, float]]], k: int = 10, threshold: float = 0.5
) -> tuple[float, float]:
    """Mean precision@k and recall@k over users; items are (score, true_label) and a label >= threshold is relevant.

    Users with no relevant item are skipped, since recall is undefined for them.
    """
    precisions, recalls = [], []
    for pairs in scores_by_user.values():
        relevant = sum(1 for _, y in pairs if y >= threshold)
        if relevant == 0:
            continue
        top = sorted(pairs, key=lambda p: p[0], reverse=True)[:k]
        hits = sum(1 for _, y in top if y >= threshold)
        precisions.append(hits / k)
        recalls.append(hits / relevant)
    if not precisions:
        return 0.0, 0.0
    return float(np.mean(precisions)), float(np.mean(recalls))


def auc(y_true, y_score) -> float:
    return float(roc_auc_score(y_true, y_score))
