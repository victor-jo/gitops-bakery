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
# Today's sitemap URLs, so the build keeps only titles Coupang Play still lists
COUPANG_SITEMAP = "catalog/coupang/sitemap_urls.json"
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
    s3.put_json(urls, COUPANG_SITEMAP)
    cache = s3.read_parquet(COUPANG_PAGES) if _exists(COUPANG_PAGES) else None
    seen = set(cache["url"]) if cache is not None else set()
    todo = [u for u in urls if u not in seen]
    if max_pages > 0:
        todo = todo[:max_pages]
    recheck = coupang.recheck_candidates(cache)
    print(f"coupang: {len(urls)} content urls, {len(seen)} cached, fetching {len(todo)}, rechecking {len(recheck)}")
    pages = coupang.crawl(todo, cache=cache, pause=pause, recheck=recheck,
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
    from recommender.catalog.coupang import current_movies

    ensure_movielens()
    pages = s3.read_parquet(COUPANG_PAGES)
    # A collect step from an image older than the sitemap snapshot leaves no list; keep every movie then
    sitemap = _read_json(COUPANG_SITEMAP) if _exists(COUPANG_SITEMAP) else pages["url"].tolist()
    movies = current_movies(pages, sitemap)
    print(f"coupang: {len(movies)} cached movies still in the sitemap "
          f"(of {int((pages['status'] == 'movie').sum())} cached)")
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
    check_services(catalog, s3.read_parquet(CATALOG) if _exists(CATALOG) else None)
    s3.write_parquet(catalog, CATALOG)
    s3.write_parquet(catalog, f"catalog/history/{today.isoformat()}.parquet")
    print(f"catalog: {len(catalog)} movies, {int(catalog['movielens_id'].notna().sum())} with MovieLens ids")
    return len(catalog)


def _service_counts(catalog: pd.DataFrame) -> dict[str, int]:
    return catalog["services"].explode().value_counts().to_dict()


def check_services(catalog: pd.DataFrame, previous: pd.DataFrame | None) -> None:
    """Refuse a catalog where a service vanished or shrank below half of the previous catalog's count."""
    counts = _service_counts(catalog)
    before = _service_counts(previous) if previous is not None else {}
    for service in SERVICES + ["cou"]:
        now, then = counts.get(service, 0), before.get(service, 0)
        if now == 0 or now < then / 2:
            raise RuntimeError(f"catalog not written: {service} has {now} titles (previous catalog: {then}); "
                               "a collector probably failed")


# ---------- training ----------

def _events() -> list[dict]:
    return [_read_json(k) for k in s3.list_keys(FEEDBACK) if k.endswith(".json")]


def _sample(ratings: pd.DataFrame, sample_users: int) -> pd.DataFrame:
    if sample_users <= 0 or sample_users >= ratings["userId"].nunique():
        return ratings
    users = ratings["userId"].drop_duplicates().sample(n=sample_users, random_state=42)
    return ratings[ratings["userId"].isin(users)].reset_index(drop=True)


def train(epochs: int, sample_users: int, dim: int, holdout_path: str) -> str:
    """Train the MF on MovieLens plus the couple, fit the content model and log both to a new MLflow run."""
    import mlflow

    from recommender.model import data, mf
    from recommender.model.content import fit_content_model

    if not _exists(CATALOG):
        raise RuntimeError(f"s3://{BUCKET}/{CATALOG} does not exist yet; run the movie-catalog pipeline first")
    started = time.time()
    ratings = _sample(s3.read_parquet(MOVIELENS["ratings"]), sample_users)
    # factorize(sort=True) in load_movielens gives user_idx i to the i-th smallest userId
    user_ids = np.sort(ratings["userId"].unique())
    catalog = s3.read_parquet(CATALOG)
    couple = data.load_couple_feedback(_events(), catalog)
    couple_train, couple_holdout = data.split_couple(couple)
    rows, user_index, item_index = data.load_movielens(ratings, couple_train)
    del ratings
    train_rows, val, test = data.split_all(rows, user_index)
    holdout = data.couple_rows(couple_holdout, user_index, item_index)
    # The gate folds each viewer in from these rows, as serving does, before scoring the holdout
    folded = data.couple_rows(couple_train, user_index, item_index)
    n_users, n_items = max(user_index.values()) + 1, len(item_index)
    print(f"train: {len(train_rows)} rows, {n_users} users, {n_items} items, couple rows {len(couple)}")

    model = mf.train(train_rows, n_users, n_items, dim=dim, epochs=epochs)
    arrays = mf.export(model)
    content = fit_content_model(catalog, arrays["item_vecs"], arrays["item_bias"], item_index)
    train_s = time.time() - started

    pd.concat([val.assign(split="val"), test.assign(split="test"), holdout.assign(split="couple"),
               folded.assign(split="couple_train")], ignore_index=True).to_parquet(holdout_path, index=False)

    mlflow.set_experiment(MODEL_NAME)
    with mlflow.start_run() as run, tempfile.TemporaryDirectory() as tmp:
        mlflow.log_params({"epochs": epochs, "sample_users": sample_users, "dim": dim,
                           "train_rows": len(train_rows), "n_users": n_users, "n_items": n_items,
                           "couple_rows": len(couple)})
        mlflow.log_metric("train_seconds", train_s)
        np.savez(os.path.join(tmp, "arrays.npz"), **arrays, user_ids=user_ids,
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


def _couple_probs(arrays: dict, couple: pd.DataFrame, folded: pd.DataFrame) -> np.ndarray:
    """Like-probabilities of the couple holdout, each viewer folded in from their couple-train rows.

    Serving never uses the trained couple user vectors; it folds a taste from the marks against
    the item vectors, so the gate scores the couple the same way.
    """
    from recommender.core.foldin import fold_in

    item_vecs, item_bias = arrays["item_vecs"], arrays["item_bias"]
    global_bias = float(arrays["global_bias"])
    prior = np.zeros(item_vecs.shape[1], np.float32)
    out = np.empty(len(couple))
    for user, idx in couple.groupby("user_idx").indices.items():
        own = folded[folded["user_idx"] == user]
        items = own["item_idx"].to_numpy()
        taste = fold_in(item_vecs[items], item_bias[items], global_bias, own["label"].to_numpy(), prior)
        held = couple["item_idx"].to_numpy()[idx]
        out[idx] = item_vecs[held] @ taste + item_bias[held] + global_bias
    return 1 / (1 + np.exp(-out))


def _metrics(arrays: dict, holdout: pd.DataFrame) -> tuple[dict[str, float], int]:
    from recommender.model.evaluate import auc, precision_recall_at_k
    from recommender.model.gate import COUPLE_MIN_HOLDOUT

    def prob(df: pd.DataFrame) -> np.ndarray:
        u, i = df["user_idx"].to_numpy(), df["item_idx"].to_numpy()
        logit = ((arrays["user_vecs"][u] * arrays["item_vecs"][i]).sum(1) + arrays["user_bias"][u]
                 + arrays["item_bias"][i] + float(arrays["global_bias"]))
        return 1 / (1 + np.exp(-logit))

    val, test, couple, folded = (holdout[holdout["split"] == s]
                                 for s in ("val", "test", "couple", "couple_train"))
    precision, recall = precision_recall_at_k(_scores_by_user(test, prob(test)), k=TOP_K)
    metrics = {"val_auc": auc(val["label"], prob(val)), "precision_10": precision, "recall_10": recall}
    if len(couple) >= COUPLE_MIN_HOLDOUT and couple["label"].nunique() == 2:
        metrics["couple_auc"] = auc(couple["label"], _couple_probs(arrays, couple, folded))
    # A one-class couple holdout has no AUC, so the gate must not apply its couple rule
    return metrics, len(couple) if "couple_auc" in metrics else 0


def _user_keys(arrays: dict) -> np.ndarray:
    """MovieLens userId for each MovieLens user index, then the viewer names at their own indices."""
    names = json.loads(str(arrays["user_index"]))
    return np.array([*map(int, arrays["user_ids"]), *sorted(names, key=names.get)], dtype=object)


def _item_keys(arrays: dict) -> np.ndarray:
    index = json.loads(str(arrays["item_index"]))
    keys = np.empty(len(index), dtype=np.int64)
    keys[list(index.values())] = [int(m) for m in index]
    return keys


def compare_on_same_rows(new: dict, champion: dict, holdout: pd.DataFrame
                         ) -> tuple[dict[str, float], dict[str, float], int, int]:
    """Score both models on the holdout rows the champion can also score, each through its own index maps.

    Returns (new metrics, champion metrics, couple holdout size for the gate, rows compared).
    """
    champ_users = {k: i for i, k in enumerate(_user_keys(champion))}
    champ_items = {int(k): i for i, k in enumerate(_item_keys(champion))}
    users = pd.Series(_user_keys(new)[holdout["user_idx"].to_numpy()]).map(champ_users)
    items = pd.Series(_item_keys(new)[holdout["item_idx"].to_numpy()]).map(champ_items)
    known = (users.notna() & items.notna()).to_numpy()
    if not known.any():
        raise RuntimeError("no holdout rows are known to both the new model and the champion; "
                           "they share no users or movies, so the gate cannot compare them")
    rows = holdout[known].reset_index(drop=True)
    mapped = rows.assign(user_idx=users[known].astype(np.int64).to_numpy(),
                         item_idx=items[known].astype(np.int64).to_numpy())
    new_metrics, couple_size = _metrics(new, rows)
    champ_metrics, _ = _metrics(champion, mapped)
    # couple_train rows only feed the fold-in; they are not scored
    return new_metrics, champ_metrics, couple_size, int((rows["split"] != "couple_train").sum())


def _load_arrays(path: str) -> dict:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def _champion_arrays(client, tmp: str) -> dict | None:
    """The champion's MF arrays, or None when there is no champion yet."""
    import mlflow

    models = client.search_registered_models(filter_string=f"name='{MODEL_NAME}'")
    if not models or ALIAS not in models[0].aliases:
        return None
    version = client.get_model_version_by_alias(MODEL_NAME, ALIAS)
    local = mlflow.artifacts.download_artifacts(f"runs:/{version.run_id}/arrays/arrays.npz",
                                                dst_path=os.path.join(tmp, "champion"))
    arrays = _load_arrays(local)
    if "user_ids" not in arrays:
        # Models trained before user_ids was saved: redo their deterministic user sample
        sample_users = int(client.get_run(version.run_id).data.params.get("sample_users", 0))
        ratings = _sample(s3.read_parquet(MOVIELENS["ratings"]), sample_users)
        arrays["user_ids"] = np.sort(ratings["userId"].unique())
    print(f"gate: champion is v{version.version} (run {version.run_id})")
    return arrays


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
        arrays = _load_arrays(os.path.join(local, "arrays.npz"))
        holdout = pd.read_parquet(holdout_path)
        metrics, couple_size = _metrics(arrays, holdout)
        # The champion is re-scored on this run's holdout, so both models are judged on the same rows
        champion = _champion_arrays(client, tmp)
        gate_metrics = {}
        if champion is not None:
            new_same, champ_metrics, couple_size, n_rows = compare_on_same_rows(arrays, champion, holdout)
            gate_metrics = {"gate_rows": n_rows, **{f"gate_{k}": v for k, v in new_same.items()},
                            **{f"gate_champion_{k}": v for k, v in champ_metrics.items()}}
            promote, reason = should_promote(new_same, champ_metrics, couple_size)
        else:
            promote, reason = should_promote(metrics, None, couple_size)
        with mlflow.start_run(run_id=run_id):
            mlflow.log_metrics({**metrics, **gate_metrics})
            mlflow.set_tags({"gate_reason": reason, "gate_promoted": str(promote).lower()})
            info = mlflow.pyfunc.log_model(
                name="model", python_model=Wrapper(), registered_model_name=MODEL_NAME,
                artifacts={"arrays": os.path.join(local, "arrays.npz"),
                           "content": os.path.join(local, "content.pkl")})
    version = info.registered_model_version
    if promote:
        client.set_registered_model_alias(MODEL_NAME, ALIAS, version)
    print(f"gate: {metrics} same-rows {gate_metrics} couple_holdout={couple_size} "
          f"-> v{version} promote={promote} ({reason})")
    return reason


def _has_champion() -> bool:
    from mlflow import MlflowClient

    models = MlflowClient().search_registered_models(filter_string=f"name='{MODEL_NAME}'")
    return bool(models) and ALIAS in models[0].aliases


def place_catalog() -> int:
    """Give every catalog movie the champion's vector and bias and write the feature parquet.

    The catalog pipeline runs this daily as well, so a new catalog reaches the service without retraining.
    """
    import mlflow

    if not _has_champion():
        print(f"features: no {MODEL_NAME}@{ALIAS} yet; skipping placement until the training pipeline promotes one")
        return 0
    catalog = s3.read_parquet(CATALOG)
    with tempfile.TemporaryDirectory() as tmp:
        local = mlflow.artifacts.download_artifacts(f"models:/{MODEL_NAME}@{ALIAS}", dst_path=tmp)
        with open(os.path.join(local, "artifacts", "content.pkl"), "rb") as f:
            content = pickle.load(f)
    vecs, bias = content.place(catalog)
    # Feast's file source needs a timestamp column; every row shares the time this placement ran
    features = catalog.assign(vector=list(vecs), bias=bias.astype(float), event_timestamp=pd.Timestamp.now(tz="UTC"))
    s3.write_parquet(features, FEATURES)
    print(f"features: {len(features)} movies, vector dim {vecs.shape[1]}")
    return len(features)


# ---------- monitoring ----------

def report_monitoring() -> None:
    """Send the weekly joint thumbs-up rate and genre/taste drift to Evidently."""
    from recommender import monitoring

    monitoring.run(os.environ["EVIDENTLY_URL"])
