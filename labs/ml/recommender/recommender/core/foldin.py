# Real-time taste fold-in: solves a viewer's vector from their thumbs, plus the genre cold-start prior
import numpy as np


def genre_prior(
    catalog_vecs: np.ndarray,
    genres_per_row: list[list[str]],
    popularity: np.ndarray,
    chosen: list[str],
    top_n: int = 50,
) -> np.ndarray:
    """Popularity-weighted mean vector of the top_n most popular movies sharing a chosen genre."""
    dim = catalog_vecs.shape[1]
    if not chosen:
        return np.zeros(dim, np.float32)
    wanted = set(chosen)
    rows = np.fromiter((i for i, g in enumerate(genres_per_row) if wanted.intersection(g)), dtype=np.int64)
    if rows.size == 0:
        return np.zeros(dim, np.float32)
    pop = np.asarray(popularity, dtype=np.float64)[rows]
    if rows.size > top_n:
        keep = np.argsort(-pop, kind="stable")[:top_n]
        rows, pop = rows[keep], pop[keep]
    vecs = catalog_vecs[rows].astype(np.float64)
    total = pop.sum()
    if total <= 0:
        return vecs.mean(axis=0).astype(np.float32)
    return ((pop / total) @ vecs).astype(np.float32)


def fold_in(
    item_vecs: np.ndarray,
    item_bias: np.ndarray,
    global_bias: float,
    labels: np.ndarray,
    prior: np.ndarray,
    l2: float = 1.0,
    iters: int = 25,
) -> np.ndarray:
    """Newton-solve the L2-regularized logistic regression of the user vector toward prior."""
    if len(labels) == 0:
        return np.array(prior, dtype=np.float32)
    v = np.asarray(item_vecs, dtype=np.float64)
    offset = np.asarray(item_bias, dtype=np.float64) + float(global_bias)
    y = np.asarray(labels, dtype=np.float64)
    prior64 = np.asarray(prior, dtype=np.float64)
    eye = np.eye(v.shape[1])
    u = prior64.copy()
    for _ in range(iters):
        p = 1.0 / (1.0 + np.exp(-(v @ u + offset)))
        grad = v.T @ (p - y) + l2 * (u - prior64)
        hess = (v * (p * (1.0 - p))[:, None]).T @ v + l2 * eye
        step = np.linalg.solve(hess, grad)
        u -= step
        if np.linalg.norm(step) < 1e-6:
            break
    return u.astype(np.float32)
