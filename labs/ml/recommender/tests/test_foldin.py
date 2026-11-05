# Tests for the real-time taste fold-in and the genre-based cold-start prior
import time

import numpy as np

from recommender.core.foldin import fold_in, genre_prior


def _sigmoid(x):
    return 1.0 / (1.0 + np.exp(-x))


def test_foldin_without_feedback_returns_prior():
    prior = np.arange(8, dtype=np.float32)
    out = fold_in(np.zeros((0, 8), np.float32), np.zeros(0, np.float32), 0.0, np.zeros(0), prior)
    assert out.dtype == np.float32
    assert np.array_equal(out, prior)
    assert out is not prior


def test_foldin_learns_direction():
    dim = 8
    rng = np.random.default_rng(0)
    pos = rng.normal(0, 0.1, (10, dim)).astype(np.float32)
    neg = pos.copy()
    pos[:, 0] += 1.0
    neg[:, 0] -= 1.0
    vecs = np.vstack([pos, neg])
    labels = np.array([1.0] * 10 + [0.0] * 10)
    u = fold_in(vecs, np.zeros(20, np.float32), 0.0, labels, np.zeros(dim, np.float32))
    assert u[0] > 0
    new_item = np.zeros(dim, np.float32)
    new_item[0] = 1.0
    assert _sigmoid(float(u @ new_item)) > 0.7


def test_foldin_runtime_under_20ms():
    rng = np.random.default_rng(1)
    vecs = rng.normal(0, 0.5, (200, 32)).astype(np.float32)
    bias = rng.normal(0, 0.1, 200).astype(np.float32)
    labels = (rng.random(200) > 0.5).astype(np.float64)
    prior = np.zeros(32, np.float32)
    times = []
    for _ in range(5):
        t0 = time.perf_counter()
        fold_in(vecs, bias, 0.1, labels, prior)
        times.append(time.perf_counter() - t0)
    assert float(np.median(times)) < 0.020


def test_genre_prior_weighted_top_n():
    vecs = np.array([[1, 0], [0, 1], [5, 5], [3, 3]], np.float32)
    genres = [["Drama"], ["Drama", "Comedy"], ["Horror"], ["Comedy"]]
    pop = np.array([3.0, 1.0, 100.0, 0.0])
    p = genre_prior(vecs, genres, pop, ["Drama", "Comedy"], top_n=2)
    assert np.allclose(p, [0.75, 0.25])
    # all-zero weights fall back to the plain mean
    p0 = genre_prior(vecs, genres, np.zeros(4), ["Comedy"], top_n=5)
    assert np.allclose(p0, [1.5, 2.0])


def test_genre_prior_empty_or_no_match_is_zero():
    vecs = np.ones((2, 3), np.float32)
    genres = [["Drama"], ["Comedy"]]
    pop = np.ones(2)
    assert np.array_equal(genre_prior(vecs, genres, pop, []), np.zeros(3, np.float32))
    assert np.array_equal(genre_prior(vecs, genres, pop, ["Horror"]), np.zeros(3, np.float32))


def _objective(u, v, off, y, prior, l2=1.0):
    z = v @ u + off
    return float(np.sum(np.logaddexp(0.0, z) - y * z) + 0.5 * l2 * np.sum((u - prior) ** 2))


def test_foldin_large_norm_opposing_bias_matches_reference_and_never_increases():
    rng = np.random.default_rng(3)
    for _ in range(20):
        dim = 8
        vec = rng.normal(size=(1, dim))
        vec = (10.0 * vec / np.linalg.norm(vec)).astype(np.float32)
        bias = np.array([rng.choice([-6.0, 6.0])], np.float32)
        label = np.array([1.0 if bias[0] < 0 else 0.0])  # label contradicts the bias
        prior = np.zeros(dim, np.float32)
        objs = [
            _objective(fold_in(vec, bias, 0.0, label, prior, iters=k).astype(np.float64),
                       vec.astype(np.float64), bias.astype(np.float64), label, prior.astype(np.float64))
            for k in range(0, 26)
        ]
        assert all(b <= a + 1e-9 for a, b in zip(objs, objs[1:]))
        ref = np.zeros(dim)
        v64, b64 = vec.astype(np.float64), bias.astype(np.float64)
        for _ in range(5000):
            z = v64 @ ref + b64
            pr = 1.0 / (1.0 + np.exp(-z))
            ref -= 0.01 * (v64.T @ (pr - label) + ref)
        got = fold_in(vec, bias, 0.0, label, prior)
        assert np.allclose(got, ref, atol=1e-3)


def test_foldin_label_length_mismatch_raises():
    import pytest

    with pytest.raises(ValueError):
        fold_in(np.zeros((3, 4), np.float32), np.zeros(3, np.float32), 0.0, np.zeros(2), np.zeros(4, np.float32))
