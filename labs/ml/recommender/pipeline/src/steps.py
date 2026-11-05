# Step bodies of the catalog and training pipelines; components.py wraps each one for KFP
import json
import os
import pickle
import tempfile
import time
import urllib.request
import zipfile
from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd

from recommender import s3
from recommender.config import ALIAS, BUCKET, MODEL_NAME

KST = timezone(timedelta(hours=9))
SERVICES = ["nfx", "dnp"]
# JustWatch asks for at least this long between requests; the collector's own pacing resets per call
JW_PAUSE = 0.3
NEW_DAYS = 7

JW_TITLES = "catalog/justwatch/titles.parquet"
JW_NEW = "catalog/justwatch/new.parquet"
COUPANG_PAGES = "catalog/coupang/pages.parquet"
COUPANG_MATCHES = "catalog/coupang/tmdb_matches.json"
SITEMAP = "https://www.coupangplay.com/sitemap.xml"
CATALOG = "catalog/movies.parquet"
FEATURES = "features/movies.parquet"
FEEDBACK = "feedback/events/"

MOVIELENS_ZIP = "https://files.grouplens.org/datasets/movielens/ml-25m.zip"
MOVIELENS = {name: f"movielens/{name}.parquet" for name in ("ratings", "movies", "links")}
# Searches between two writes of the Coupang tmdb match cache, so a crash loses little work
MATCH_FLUSH = 100
TOP_K = 10


def _today() -> date:
    return datetime.now(KST).date()


def _exists(key: str) -> bool:
    return key in s3.list_keys(key)


def _read_json(key: str):
    return json.loads(s3.client().get_object(Bucket=BUCKET, Key=key)["Body"].read())


# ---------- catalog ----------

def collect_justwatch() -> int:
    """Fetch both services and the last week's additions from JustWatch into the catalog staging keys."""
    from recommender.catalog import justwatch as jw

    frames = []
    for n, pkg in enumerate(SERVICES):
        if n:
            time.sleep(JW_PAUSE)
        frames.append(jw.fetch_service(pkg, jw.http_post, pause=JW_PAUSE))
    titles = pd.concat(frames, ignore_index=True)
    news = []
    for n in range(NEW_DAYS):
        time.sleep(JW_PAUSE)
        news.append(jw.new_titles(_today() - timedelta(days=n), SERVICES, jw.http_post, pause=JW_PAUSE))
    s3.write_parquet(titles, JW_TITLES)
    s3.write_parquet(pd.concat(news, ignore_index=True), JW_NEW)
    print(f"justwatch: {len(titles)} titles, {sum(map(len, news))} new in {NEW_DAYS} days")
    return len(titles)


def collect_coupang(max_pages: int, pause: float) -> int:
    """Crawl Coupang Play /content pages missing from the cache; max_pages > 0 caps the new fetches."""
    from recommender.catalog import coupang

    code, xml = coupang.default_fetch(SITEMAP)
    if code != 200:
        raise RuntimeError(f"sitemap answered HTTP {code}")
    urls = coupang.content_urls(xml)
    cache = s3.read_parquet(COUPANG_PAGES) if _exists(COUPANG_PAGES) else None
    seen = set(cache["url"]) if cache is not None else set()
    todo = [u for u in urls if u not in seen]
    if max_pages > 0:
        todo = todo[:max_pages]
    print(f"coupang: {len(urls)} content urls, {len(seen)} cached, fetching {len(todo)}")
    pages = coupang.crawl(todo, cache=cache, pause=pause,
                          on_batch=lambda df: s3.write_parquet(df, COUPANG_PAGES))
    s3.write_parquet(pages, COUPANG_PAGES)
    print(f"coupang: cache now {len(pages)} pages, {int((pages['status'] == 'movie').sum())} movies")
    return len(pages)


def ensure_movielens() -> None:
    """Download MovieLens 25M once and keep ratings, movies and links as parquet in the bucket."""
    if all(_exists(k) for k in MOVIELENS.values()):
        print("movielens: already in the bucket")
        return
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, "ml-25m.zip")
        started = time.time()
        urllib.request.urlretrieve(MOVIELENS_ZIP, path)
        print(f"movielens: downloaded {os.path.getsize(path) >> 20} MiB in {time.time() - started:.0f} s")
        with zipfile.ZipFile(path) as z:
            ratings = pd.read_csv(z.open("ml-25m/ratings.csv"), dtype={
                "userId": "int32", "movieId": "int32", "rating": "float32", "timestamp": "int64"})
            movies = pd.read_csv(z.open("ml-25m/movies.csv"))
            links = pd.read_csv(z.open("ml-25m/links.csv"), dtype={"tmdbId": "Int64"})
    s3.write_parquet(movies, MOVIELENS["movies"])
    s3.write_parquet(links, MOVIELENS["links"])
    s3.write_parquet(ratings, MOVIELENS["ratings"])
    print(f"movielens: {len(ratings)} ratings, {len(movies)} movies")


def match_and_build() -> int:
    """Match Coupang titles to tmdb ids, merge the three services and write today's catalog."""
    from recommender.catalog import justwatch as jw
    from recommender.catalog.build import build_catalog, match_coupang

    ensure_movielens()
    pages = s3.read_parquet(COUPANG_PAGES)
    movies = pages[pages["status"] == "movie"].reset_index(drop=True)
    known = _read_json(COUPANG_MATCHES) if _exists(COUPANG_MATCHES) else {}
    searched = 0

    def search(title, year):
        nonlocal searched
        if searched and searched % MATCH_FLUSH == 0:
            s3.put_json(known, COUPANG_MATCHES)
        searched += 1
        time.sleep(JW_PAUSE)
        return jw.search_tmdb_id(title, year, jw.http_post)

    try:
        matched = match_coupang(movies, search, known)
    finally:
        s3.put_json(known, COUPANG_MATCHES)
    hits = int(matched["tmdb_id"].notna().sum())
    print(f"coupang match: {searched} searched, {hits}/{len(matched)} movies have a tmdb id")

    today = _today()
    catalog = build_catalog(s3.read_parquet(JW_TITLES), matched, s3.read_parquet(JW_NEW),
                            s3.read_parquet(MOVIELENS["links"]), today)
    s3.write_parquet(catalog, CATALOG)
    s3.write_parquet(catalog, f"catalog/history/{today.isoformat()}.parquet")
    print(f"catalog: {len(catalog)} movies, {int(catalog['movielens_id'].notna().sum())} with MovieLens ids")
    return len(catalog)


# ---------- training ----------

def _events() -> list[dict]:
    return [_read_json(k) for k in s3.list_keys(FEEDBACK) if k.endswith(".json")]


def _sample(ratings: pd.DataFrame, sample_users: int) -> pd.DataFrame:
    if sample_users <= 0:
        return ratings
    users = ratings["userId"].drop_duplicates().sample(n=sample_users, random_state=42)
    return ratings[ratings["userId"].isin(users)].reset_index(drop=True)


def train(epochs: int, sample_users: int, dim: int, holdout_path: str) -> str:
    """Train the MF on MovieLens plus the couple, fit the content model and log both to a new MLflow run."""
    import mlflow

    from recommender.model import data, mf
    from recommender.model.content import fit_content_model

    started = time.time()
    ratings = _sample(s3.read_parquet(MOVIELENS["ratings"]), sample_users)
    catalog = s3.read_parquet(CATALOG)
    couple = data.load_couple_feedback(_events(), catalog)
    rows, user_index, item_index = data.load_movielens(ratings, couple)
    del ratings
    train_rows, val, test, holdout = data.split_all(rows, user_index)
    n_users, n_items = max(user_index.values()) + 1, len(item_index)
    print(f"train: {len(train_rows)} rows, {n_users} users, {n_items} items, couple rows {len(couple)}")

    model = mf.train(train_rows, n_users, n_items, dim=dim, epochs=epochs)
    arrays = mf.export(model)
    content = fit_content_model(catalog, arrays["item_vecs"], arrays["item_bias"], item_index)
    train_s = time.time() - started

    pd.concat([val.assign(split="val"), test.assign(split="test"), holdout.assign(split="couple")],
              ignore_index=True).to_parquet(holdout_path, index=False)

    mlflow.set_experiment(MODEL_NAME)
    with mlflow.start_run() as run, tempfile.TemporaryDirectory() as tmp:
        mlflow.log_params({"epochs": epochs, "sample_users": sample_users, "dim": dim,
                           "train_rows": len(train_rows), "n_users": n_users, "n_items": n_items,
                           "couple_rows": len(couple)})
        mlflow.log_metric("train_seconds", train_s)
        np.savez(os.path.join(tmp, "arrays.npz"), **arrays,
                 user_index=json.dumps(user_index), item_index=json.dumps(item_index))
        with open(os.path.join(tmp, "content.pkl"), "wb") as f:
            pickle.dump(content, f)
        mlflow.log_artifacts(tmp, "arrays")
        print(f"train: run {run.info.run_id} in {train_s:.0f} s")
        return run.info.run_id


def _scores_by_user(df: pd.DataFrame, p: np.ndarray) -> dict[int, list[tuple[float, float]]]:
    out: dict[int, list[tuple[float, float]]] = {}
    for u, s, y in zip(df["user_idx"].to_numpy(), p, df["label"].to_numpy()):
        out.setdefault(int(u), []).append((float(s), float(y)))
    return out


def _metrics(arrays: dict, holdout: pd.DataFrame) -> tuple[dict[str, float], int]:
    from recommender.model.evaluate import auc, precision_recall_at_k
    from recommender.model.gate import COUPLE_MIN_HOLDOUT

    def prob(df: pd.DataFrame) -> np.ndarray:
        u, i = df["user_idx"].to_numpy(), df["item_idx"].to_numpy()
        logit = ((arrays["user_vecs"][u] * arrays["item_vecs"][i]).sum(1) + arrays["user_bias"][u]
                 + arrays["item_bias"][i] + float(arrays["global_bias"]))
        return 1 / (1 + np.exp(-logit))

    val, test, couple = (holdout[holdout["split"] == s] for s in ("val", "test", "couple"))
    precision, recall = precision_recall_at_k(_scores_by_user(test, prob(test)), k=TOP_K)
    metrics = {"val_auc": auc(val["label"], prob(val)), "precision_10": precision, "recall_10": recall}
    if len(couple) >= COUPLE_MIN_HOLDOUT and couple["label"].nunique() == 2:
        metrics["couple_auc"] = auc(couple["label"], prob(couple))
    # A one-class couple holdout has no AUC, so the gate must not apply its couple rule
    return metrics, len(couple) if "couple_auc" in metrics else 0


def _champion_metrics(client) -> dict[str, float] | None:
    models = client.search_registered_models(filter_string=f"name='{MODEL_NAME}'")
    if not models or ALIAS not in models[0].aliases:
        return None
    version = client.get_model_version_by_alias(MODEL_NAME, ALIAS)
    return dict(client.get_run(version.run_id).data.metrics)


def evaluate_and_gate(run_id: str, holdout_path: str) -> str:
    """Score the run on its held-out rows, register it and move the champion alias if the gate passes."""
    import mlflow
    from mlflow import MlflowClient

    from recommender.model.gate import should_promote

    # Serving reads arrays.npz and content.pkl from the model's artifacts directly, so predict is never called
    class Wrapper(mlflow.pyfunc.PythonModel):
        def predict(self, context, model_input):
            raise NotImplementedError("score with the arrays artifact, not through pyfunc")

    client = MlflowClient()
    with tempfile.TemporaryDirectory() as tmp:
        local = mlflow.artifacts.download_artifacts(f"runs:/{run_id}/arrays", dst_path=tmp)
        with np.load(os.path.join(local, "arrays.npz")) as z:
            arrays = {k: z[k] for k in z.files}
        metrics, couple_size = _metrics(arrays, pd.read_parquet(holdout_path))
        champion = _champion_metrics(client)
        promote, reason = should_promote(metrics, champion, couple_size)
        with mlflow.start_run(run_id=run_id):
            mlflow.log_metrics(metrics)
            mlflow.set_tags({"gate_reason": reason, "gate_promoted": str(promote).lower()})
            info = mlflow.pyfunc.log_model(
                name="model", python_model=Wrapper(), registered_model_name=MODEL_NAME,
                artifacts={"arrays": os.path.join(local, "arrays.npz"),
                           "content": os.path.join(local, "content.pkl")})
    version = info.registered_model_version
    if promote:
        client.set_registered_model_alias(MODEL_NAME, ALIAS, version)
    print(f"gate: {metrics} couple_holdout={couple_size} -> v{version} promote={promote} ({reason})")
    return reason


def place_catalog() -> int:
    """Give every catalog movie the champion's vector and bias and write the feature parquet."""
    import mlflow

    catalog = s3.read_parquet(CATALOG)
    with tempfile.TemporaryDirectory() as tmp:
        local = mlflow.artifacts.download_artifacts(f"models:/{MODEL_NAME}@{ALIAS}", dst_path=tmp)
        with open(os.path.join(local, "artifacts", "content.pkl"), "rb") as f:
            content = pickle.load(f)
    vecs, bias = content.place(catalog)
    features = catalog.assign(vector=list(vecs), bias=bias.astype(float))
    s3.write_parquet(features, FEATURES)
    print(f"features: {len(features)} movies, vector dim {vecs.shape[1]}")
    return len(features)
