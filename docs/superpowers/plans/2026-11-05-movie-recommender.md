# Weekend Movie Recommender for Two Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** A phone web page on the home Wi-Fi that shows the user and their wife 5–10 movies from Netflix, Disney+ and Coupang Play (Korea) that both are likely to enjoy, learning from every 👍/👎 immediately.

**Architecture:** KFP pipelines collect the Korean OTT catalog (JustWatch for Netflix/Disney+, Coupang Play's own `/content` pages) and train a binary matrix-factorization model on MovieLens 25M plus the couple's feedback, gated and registered in MLflow. A BentoML service (one container on the kind network, published on the Mac's LAN address) folds each person's taste vector in on every 👍/👎, stores it in Feast's online store, ranks with the veto rule, and serves the web page. A weekly KFP step writes an Evidently report on the joint-👍 rate and drift.

**Tech Stack:** Python 3.13, PyTorch (CPU), scikit-learn, pandas/pyarrow, KFP 2.18.0, MLflow 3.16.0, Feast 0.67.0 (Redis/Valkey online store), BentoML + FastAPI (mounted ASGI app), Evidently 0.7.23, Garage S3, plain HTML/JS front-end. Installer changes in TypeScript (vitest).

**Spec:** `docs/superpowers/specs/2026-11-05-movie-recommender-design.md`

## Global Constraints

- Services: Netflix (JustWatch package `nfx`), Disney+ (`dnp`), Coupang Play (official site). Country `KR`. Movies only, no series.
- No "upcoming" titles, no theatrical releases, no solo recommendations in v1.
- Two fixed viewers, ids `me` (label "나") and `wife` (label "아내"); no password, no age, no other personal data.
- Feedback is binary: 👍 = `liked: true`, 👎 = `liked: false`. MovieLens rating ≥ 4.0 counts as 👍.
- Veto: drop a movie if either person's predicted like-probability is below `VETO_P = 0.35`. Rank survivors by `min(p_me, p_wife)`. If fewer than `MIN_RESULTS = 5` survive, refill with the best movies whose lower score is in `[STRONG_DISLIKE_P = 0.20, 0.35)`, flagged `gamble: true` ("조금 모험"). Never show more than `MAX_RESULTS = 10`.
- Exclude every movie either person has marked (👍 or 👎) or that was recorded as watched.
- Coupang Play: read only `https://www.coupangplay.com/sitemap.xml` and `/content/<uuid>` pages, at most one request per second; never request any `/api` path. Full pass once, then only URLs not yet cached.
- JustWatch GraphQL `https://apis.justwatch.com/graphql`: unofficial; at least 0.3 s between requests; fetch `popularTitles` in release-year slices (paging stops near 1,900 results).
- Garage bucket `recommender` (owned by the `kfp` key). Feast project `movie_recommender`, registry `s3://recommender/feast/registry.db`, online store Valkey `db=2`.
- MLflow experiment and registered model `movie-recommender`, serving alias `champion`. Evidently project `movie-recommender`.
- The service listens on `0.0.0.0:3100` on the Mac (phone URL `http://<mac-lan-ip>:3100`), container name `movie-rec`, on the `kind` Docker network. The existing `income-clf-drift` container (port 3001) is untouched.
- No secrets in git, images or pipeline parameters; read credentials from Kubernetes Secrets at run time (pattern: `labs/ml/serving/run.sh`, `kubernetes.use_secret_as_env`). Never print secret values.
- Sslip hosts change after an OrbStack restart: every URL comes from `labs/ml/env.sh` / env vars, never hard-coded IPs.
- First line of every new source file is a one-line English comment stating its role; all comments in English; no ticket numbers in comments.
- UI copy is Korean. Commits are semantic, with no AI attribution trailers.

## Review Focus

1. **A viewer with no feedback yet** (wife skipped onboarding): recommendations still come back, from the genre prior, or from Korean popularity if no genres were chosen either. Pinned in Task 11 (`test_foldin_without_feedback_returns_prior`) and Task 12 (`test_rank_with_empty_viewer_uses_popularity`).
2. **The same movie on two services** (Netflix and Coupang): one card listing both services, never two cards. Pinned in Task 5 (`test_build_catalog_merges_services_by_tmdb_id`).
3. **A broken or removed Coupang page** (404, no JSON-LD, a `TVSeries`): skipped and remembered, the crawl continues. Pinned in Task 4 (`test_crawl_skips_404_and_series`).
4. **Service restart or container rebuild**: all marks, watched records and taste vectors come back from the feedback log in Garage. Pinned in Task 12 (`test_state_replay_rebuilds_marks_and_watched`).
5. **OrbStack restart moves the sslip hosts**: the service reads MLflow and Evidently URLs from env at start, so `run.sh` after `install --with-ml` is all that is needed. Pinned in Task 14 (`test_settings_come_from_env`).

---

## File Structure

```
labs/ml/recommender/
  README.md                     exercise walkthrough, phone URL, blog log pointer
  BLOG_NOTES.md                 running log of decisions, numbers, screenshots for the velog post
  requirements.txt              Mac/test venv (.venv-rec)
  pyproject.toml                pytest config only (rootdir, pythonpath)
  recommender/
    __init__.py
    config.py                   constants from Global Constraints + Settings from env
    genres.py                   canonical genre vocabulary and mappers (JustWatch, Coupang, MovieLens)
    s3.py                       Garage client and parquet/json helpers
    catalog/
      justwatch.py              JustWatch GraphQL collector (popular titles, new titles, title search)
      coupang.py                Coupang sitemap/page parser and polite crawler
      build.py                  merge services, match Coupang to TMDB, join MovieLens -> movies table
    model/
      data.py                   MovieLens 25M loading, binary labels, couple users appended
      mf.py                     binary matrix factorization (PyTorch) train/export
      content.py                content features -> embedding regressor for movies without MovieLens data
      evaluate.py               precision@k, recall@k, AUC
      gate.py                   promotion decision against the champion
    core/
      foldin.py                 per-viewer taste vector from 👍/👎 against frozen item vectors
      rank.py                   scoring, veto, gamble refill, genre lean, reasons
      state.py                  feedback events, log replay, viewer state
    monitoring.py               weekly Evidently report (joint-👍 rate, taste and genre drift)
  feature_repo/
    features.py                 Feast entities and feature views
  feast_config.py               writes feature_store.yaml for the service/Mac from the seeded Valkey config
  pipeline/
    src/Dockerfile              component image kfp/recommender-pipeline:0.1.0
    src/runtime-requirements.txt
    src/components.py           KFP components wrapping recommender.* functions
    catalog_pipeline.py         movie-catalog pipeline (daily)
    training_pipeline.py        movie-recommender-training pipeline
    monitoring_pipeline.py      movie-recommender-monitoring pipeline (weekly)
    run.py                      compile + submit helper
  serving/
    service.py                  BentoML service mounting the FastAPI app
    api.py                      FastAPI routes
    bentofile.yaml
    requirements.txt
    build.sh / run.sh
  web/
    index.html, app.js, style.css   phone UI: profile -> genres -> mark seen -> weekend picks
  tests/                        pytest, one file per module
src/steps/ml/storage.ts         + bucket recommender, kfp owner
src/steps/ml/kfp-image.ts       + ml-recommender-image step
labs/ml/env.sh                  + REC_IMAGE
test/unit/ml.test.ts            + step order, bucket grant
```

---

### Task 1: Lab plumbing (bucket, image step, env, venv)

**Files:**
- Modify: `src/steps/ml/storage.ts` (`ML_BUCKETS`, `ML_KEYS.kfp.owner`)
- Modify: `src/steps/ml/kfp-image.ts` (new exported step), the ML step list where `ml-drift-image` is registered
- Modify: `labs/ml/env.sh`, `labs/ml/.gitignore`
- Create: `labs/ml/recommender/requirements.txt`, `pyproject.toml`, `recommender/__init__.py`, `recommender/config.py`, `pipeline/src/Dockerfile`, `pipeline/src/runtime-requirements.txt`
- Test: `test/unit/ml.test.ts`, `labs/ml/recommender/tests/test_config.py`

**Interfaces:**
- Produces: bucket `recommender`; step id `ml-recommender-image` pushing `kfp/recommender-pipeline:0.1.0`; env `REC_IMAGE=<cluster>-control-plane:30001/kfp/recommender-pipeline:0.1.0`; `recommender.config` constants `VETO_P, STRONG_DISLIKE_P, MIN_RESULTS, MAX_RESULTS, LIKE_RATING, VIEWERS: dict[str, str]` (`{"me": "나", "wife": "아내"}`), `SERVICES: dict[str, str]` (`{"nfx": "Netflix", "dnp": "Disney+", "cou": "Coupang Play"}`), `BUCKET = "recommender"`, `VALKEY_DB = 2`, `MODEL_NAME = "movie-recommender"`, `ALIAS = "champion"`.

- [ ] **Step 1: Write the failing vitest tests** in `test/unit/ml.test.ts`: the `--with-ml` step order ends with `"ml-kfp-image", "ml-drift-image", "ml-recommender-image"`; `ML_BUCKETS` contains `"recommender"`; `grantCommands()` includes `["bucket","allow","--read","--write","--owner","recommender","--key","kfp"]`.
- [ ] **Step 2: Run** `npx vitest run test/unit/ml.test.ts` — expect FAIL on those three.
- [ ] **Step 3: Implement** the bucket and grant, and `mlRecommenderImageStep` (`id: "ml-recommender-image"`, title `"Recommender component image in Harbor"`) calling `pushLabImage(ctx, "recommender-pipeline:0.1.0", assetPath("labs","ml","recommender"))` with the Dockerfile at `pipeline/src/Dockerfile` (build context is `labs/ml/recommender` so the image contains the `recommender` package; pass `-f`, extending `buildArgs` with an optional dockerfile argument). Add `REC_IMAGE` to `env.sh`'s printed exports. Add `recommender/.venv-rec`, `recommender/pipeline/*.yaml`, `recommender/serving/.bento-tag` to `.gitignore`.
- [ ] **Step 4: Run** `npx vitest run` — expect all PASS (the whole suite, since the step list is shared).
- [ ] **Step 5: Write `tests/test_config.py::test_constants_match_spec`** asserting the exact values above, then create `config.py`, the venv (`python3 -m venv labs/ml/recommender/.venv-rec && .venv-rec/bin/pip install -r requirements.txt`), and pin in `requirements.txt` the versions pip resolves (keep `mlflow==3.16.0`, `feast[redis,aws]==0.67.0`, `evidently==0.7.23`, `pandas==2.3.3`, `numpy==2.5.4`, `pyarrow==25.0.1`, `kfp==2.18.0` equal to the lab's; add `torch` CPU, `scikit-learn==1.9.1`, `bentoml`, `fastapi`, `httpx`, `pytest`). Run `cd labs/ml/recommender && .venv-rec/bin/pytest -q` — PASS.
- [ ] **Step 6: Apply to the running lab**: remove `ml-storage` from `steps` in `~/.gitops-bakery/state.json` (back it up first), `npm run build`, `node dist/cli.js install --with-ml`; verify the `recommender` bucket exists (`garage bucket list` via the installer's helper or the Garage pod) and Harbor has `kfp/recommender-pipeline:0.1.0`.
- [ ] **Step 7: Commit** `feat: add the recommender bucket, image step and venv`.

### Task 2: Genre vocabulary

**Files:** Create `recommender/genres.py`; Test `tests/test_genres.py`

**Interfaces:**
- Produces: `CANONICAL: tuple[str, ...]` = `("action","adventure","animation","comedy","crime","documentary","drama","family","fantasy","history","horror","music","mystery","romance","scifi","thriller","war","western","sport","reality")`; `KOREAN_LABEL: dict[str, str]` for the UI (`"thriller": "스릴러"`, …); `from_justwatch(codes: list[str]) -> list[str]`; `from_coupang(names: list[str]) -> list[str]`; `from_movielens(pipe_joined: str) -> list[str]`. Unknown labels are dropped; output is sorted and unique.

- [ ] **Step 1: Write failing tests**: `from_justwatch(["act","drm","trl"]) == ["action","drama","thriller"]`; `from_justwatch(["scf","rma","xyz"]) == ["romance","scifi"]`; `from_coupang(["범죄","드라마","스릴러","실화 바탕"]) == ["crime","drama","thriller"]`; `from_coupang(["무협","시대극"]) == ["action","history"]`; `from_coupang(["키즈","가족"]) == ["family"]`; `from_movielens("Action|Sci-Fi|IMAX") == ["action","scifi"]`; every `CANONICAL` key has a `KOREAN_LABEL`.
- [ ] **Step 2: Run** `pytest tests/test_genres.py` — FAIL.
- [ ] **Step 3: Implement** with three lookup dicts. JustWatch codes: `act, ani, cmy, crm, doc, drm, eur→drop, fml, fnt, hst, hrr, msc, rly→reality, rma, scf, spt, trl, war, wsn`. MovieLens `Children→family, Film-Noir→crime, Musical→music, Mystery→mystery`. Coupang: map every genre string seen in the 30-page sample in the spec research plus `코미디, 로맨스, 액션, 어드벤처, 애니메이션, 판타지, 공포, 호러, SF, 다큐멘터리, 음악, 뮤지컬, 전쟁, 서부, 스포츠, 미스터리, 법정→drama`.
- [ ] **Step 4: Run** — PASS. **Step 5: Commit** `feat: map OTT and MovieLens genres to one vocabulary`.

### Task 3: JustWatch collector

**Files:** Create `recommender/catalog/justwatch.py`; Test `tests/test_justwatch.py`

**Interfaces:**
- Produces: `Post = Callable[[str, dict], dict]` (query, variables → parsed JSON); `fetch_service(package: str, post: Post, years: list[tuple[int,int]] | None = None, pause: float = 0.3) -> pd.DataFrame` with columns `justwatch_id:int, tmdb_id:str|None, imdb_id:str|None, title, original_title, release_year:int|None, runtime_min, genres:list[str] (canonical), description:str, popularity_rank:int, service:str`; `new_titles(day: date, packages: list[str], post: Post) -> pd.DataFrame` columns `justwatch_id, tmdb_id, service, added_on:date`; `search_tmdb_id(title: str, year: int | None, post: Post) -> str | None`; `http_post(query, variables) -> dict` (urllib, raises on GraphQL `errors`).
- Year slices default: `(1900,1979), (1980,1989), (1990,1999)`, then one per year from 2000 to the current year + 1.

- [ ] **Step 1: Write failing tests** with a fake `post` that pages: two slices × two pages → `fetch_service` returns the union with no duplicate `justwatch_id`, `popularity_rank` is 1..n in JustWatch order within the service, genres canonical; `new_titles` sends `pageType: "NEW"`, `date` as ISO and the package filter and stamps `added_on`; `search_tmdb_id("기생충", 2019, post)` returns the tmdb id only for an exact normalized title match (normalization: NFKC, lower, strip spaces and punctuation, drop a trailing `(1996)` or `(자막)`) and year within ±1, else `None`.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement**; GraphQL fields exactly as in the probe: `popularTitles(country, first: 100, after, filter: {objectTypes: [MOVIE], packages: [pkg], releaseYear: {min, max}})` with `content(country, language: "ko") { title originalTitle originalReleaseYear runtime shortDescription genres { shortName } externalIds { imdbId tmdbId } }`; `newTitles(country, date, first, after, pageType: NEW, filter: {objectTypes: [MOVIE], packages})`; search via `popularTitles(... filter: {searchQuery: title, objectTypes: [MOVIE]})`. Popularity rank across slices: sort the union by the per-slice rank interleaved isn't meaningful, so rank by a final `popularTitles` pass without year filter for the first 1,900 and append the rest by `tmdb_score` descending — document this in a comment.
- [ ] **Step 4: Run** — PASS. **Step 5: Live smoke** (Mac): `python -c "from recommender.catalog.justwatch import *; print(len(fetch_service('nfx', http_post)))"` prints about 5,047; record the number in `BLOG_NOTES.md`. **Step 6: Commit** `feat: collect Netflix and Disney+ Korea from JustWatch`.

### Task 4: Coupang Play collector

**Files:** Create `recommender/catalog/coupang.py`; Test `tests/test_coupang.py`, fixtures `tests/fixtures/coupang_movie.html`, `coupang_series.html` (trimmed copies of real pages: JSON-LD block plus `<title>`)

**Interfaces:**
- Produces: `content_urls(sitemap_xml: str) -> list[str]` (only `https://www.coupangplay.com/content/<uuid>`, Korean, deduped); `parse_page(html: str, url: str) -> dict | None` returning `coupang_id, title, year_hint:int|None (from a "(1996)" suffix), genres (canonical), description, actors:list[str], poster_url, rating:float|None, rating_count:int, added_on:date|None (datePublished)` or `None` when there is no `Movie` JSON-LD; `crawl(urls, fetch: Callable[[str], tuple[int,str]], cache: pd.DataFrame, pause: float = 1.0, sleep=time.sleep) -> pd.DataFrame` (cache rows carry `status: "movie"|"not_movie"|"gone"` and `fetched_at`).

- [ ] **Step 1: Write failing tests**: `content_urls` keeps the 2 content URLs of a 4-entry sitemap and drops `/en/` and the home page; `parse_page(movie fixture)` returns `title "트위스터"`, `year_hint 1996`, `added_on date(2023,8,21)`, `rating_count 74`; series fixture → `None`; `test_crawl_skips_404_and_series` — fetch returns 404 for one URL, the series HTML for another, a movie for the third: result has statuses `gone, not_movie, movie`, `sleep` was called with `1.0` between every request, and a second `crawl` with that cache fetches nothing; `test_crawl_refuses_api_paths` — a URL containing `/api/` raises `ValueError` before any fetch.
- [ ] **Step 2: Run** — FAIL. **Step 3: Implement**; `fetch` default uses urllib with `User-Agent: gitops-bakery-movie-rec (personal lab)` and a 20 s timeout. **Step 4: Run** — PASS. **Step 5: Live check of `datePublished`**: crawl 20 movie pages (`max_pages`-style slice of `content_urls`), compare `added_on` with the original release year for at least 10 old films; if `added_on` is ever before the release year or equals it for most, it is not an "added to Coupang" date — then set `added_on = None` for Coupang and note it in `BLOG_NOTES.md`. **Step 6: Commit** `feat: read Coupang Play movie pages politely`.

### Task 5: Catalog build and matching

**Files:** Create `recommender/catalog/build.py`, `recommender/s3.py`; Test `tests/test_build.py`

**Interfaces:**
- Consumes: Task 3 frames, Task 4 cache, `search_tmdb_id`.
- Produces: `match_coupang(coupang: pd.DataFrame, search: Callable[[str,int|None], str|None], known: dict[str,str]) -> pd.DataFrame` (adds `tmdb_id`, cached by `coupang_id` in `known`); `build_catalog(justwatch: pd.DataFrame, coupang: pd.DataFrame, new: pd.DataFrame, links: pd.DataFrame, today: date) -> pd.DataFrame` with one row per movie: `movie_key` (`"tmdb:<id>"`, else `"cp:<coupang_id>"`), `tmdb_id, movielens_id:int|None, title, release_year, genres, description, actors, poster_url, services:list[str]` (codes, sorted), `popularity_kr:float` (0..1, higher = more watched in Korea: per-service rank percentile, Coupang from `rating_count` percentile, max across services), `added_on:date|None` (latest across services), `new_this_week:bool` (`added_on >= today - 7 days`). `s3.py`: `client()` from env (`S3_ENDPOINT`, AWS keys), `read_parquet(key)`, `write_parquet(df, key)`, `put_json(obj, key)`, `list_keys(prefix)`.

- [ ] **Step 1: Write failing tests**: `test_build_catalog_merges_services_by_tmdb_id` — a Netflix row and a Coupang row with the same tmdb id give one row with `services == ["cou","nfx"]` and the Coupang poster used only if JustWatch has none; an unmatched Coupang row keeps `movie_key "cp:…"`; `movielens_id` filled from `links` by tmdb id; `new_this_week` true for `added_on = today - 7`, false for `today - 8`; series never appear (input already filtered).
- [ ] **Step 2–4:** Run FAIL → implement → PASS. **Step 5: Commit** `feat: merge the three services into one movie catalog`.

### Task 6: Training data and binary matrix factorization

**Files:** Create `recommender/model/data.py`, `recommender/model/mf.py`, `recommender/model/evaluate.py`; Test `tests/test_mf.py`, `tests/test_evaluate.py`

**Interfaces:**
- Produces:
  - `load_movielens(ratings: pd.DataFrame, couple: pd.DataFrame) -> tuple[pd.DataFrame, dict[str,int]]` — returns rows `user_idx:int, item_idx:int, label:float` (1.0 if rating ≥ 4.0 else 0.0) with the couple's events appended as two extra users, plus `user_index` mapping `{"me": n, "wife": n+1}`; `couple` columns `viewer, movielens_id, liked`.
  - `split(df, seed=42) -> (train, val, test)` 75/15/10 per the reference project; couple rows split 80/20 into train/`couple_holdout`.
  - `MF(n_users, n_items, dim=32)` (torch module: user/item embeddings + user/item bias + global bias, `forward(u, i) -> logits`); `train(df, n_users, n_items, dim=32, epochs=5, batch=65536, lr=0.01, weight_decay=1e-5) -> MF`; `export(model) -> dict` with numpy arrays `item_vecs (n_items, dim), item_bias (n_items,), global_bias float, user_vecs, user_bias`.
  - `evaluate.precision_recall_at_k(scores_by_user: dict[int, list[tuple[float, float]]], k=10, threshold=0.5) -> tuple[float,float]`, `auc(y_true, y_score) -> float` (sklearn).
- [ ] **Step 1: Write failing tests**: on a synthetic 50-user × 40-item dataset where users 0–24 like items 0–19 and dislike 20–39 (others vice versa), `train(..., epochs=30)` reaches AUC ≥ 0.95 on held-out pairs; `load_movielens` labels rating 4.0 as 1.0 and 3.5 as 0.0 and gives `me`/`wife` the last two user indices; `precision_recall_at_k` equals hand-computed values on a 2-user example; `export` shapes match.
- [ ] **Step 2–4:** FAIL → implement (BCEWithLogitsLoss, Adam) → PASS. Plain dot-product MF instead of the reference's MLP head: fold-in (Task 11) needs scores linear in the user vector — say so in the module header. **Step 5: Commit** `feat: train a binary matrix factorization on MovieLens`.

### Task 7: Promotion gate

**Files:** Create `recommender/model/gate.py`; Test `tests/test_gate.py`

**Interfaces:**
- Produces: `should_promote(new: dict[str,float], champion: dict[str,float] | None, couple_holdout_size: int) -> tuple[bool, str]`. Metrics keys `val_auc, precision_10, recall_10, couple_auc`. Rules: no champion → promote; `val_auc` drop > 0.005 → reject; `precision_10` drop > 0.01 → reject; when `couple_holdout_size >= 10`, `couple_auc` below the champion's → reject; otherwise promote. The string names the rule that decided.
- [ ] **Step 1: Failing tests**, one per rule, including "couple AUC ignored with 9 holdout rows". **Step 2–4:** FAIL → implement → PASS. **Step 5: Commit** `feat: gate promotion on MovieLens and the couple's own ratings`.

### Task 8: Content placement for movies without MovieLens data

**Files:** Create `recommender/model/content.py`; Test `tests/test_content.py`

**Interfaces:**
- Produces: `fit_content_model(catalog: pd.DataFrame, item_vecs: np.ndarray, item_bias: np.ndarray, movielens_to_idx: dict[int,int]) -> ContentModel`; `ContentModel.place(catalog: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]` (vectors, biases for every catalog row). Features: multi-hot canonical genres, release decade one-hot, `HashingVectorizer(analyzer="char_wb", ngram_range=(2,3), n_features=2**16)` on `title + description + actors` (Korean-friendly), TF-IDF weighted; target: MF item vectors and biases of matched movies; `Ridge(alpha=1.0)`. Rows that have a MovieLens id keep their MF vector; only the rest are predicted.
- [ ] **Step 1: Failing tests**: with synthetic vectors where genre "horror" items sit at `+e0` and "romance" at `-e0`, an unmatched horror movie is placed with positive first coordinate; matched rows are returned unchanged.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Commit** `feat: place new movies from their genres and descriptions`.

### Task 9: KFP pipelines (catalog, training)

**Files:** Create `pipeline/src/components.py`, `pipeline/catalog_pipeline.py`, `pipeline/training_pipeline.py`, `pipeline/run.py`; Test `tests/test_pipelines_compile.py`

**Interfaces:**
- Consumes: Tasks 3–8.
- Produces: pipeline `movie-catalog` (steps `collect_justwatch` → `collect_coupang` → `match_and_build`) writing `s3://recommender/catalog/movies.parquet` and dated copies `catalog/history/<date>.parquet`; pipeline `movie-recommender-training` (`prepare_movielens` (downloads `https://files.grouplens.org/datasets/movielens/ml-25m.zip` once into `s3://recommender/movielens/`) → `train` → `evaluate_and_gate` → `place_catalog`) logging to MLflow experiment `movie-recommender`, registering model `movie-recommender` with the exported arrays as an MLflow pyfunc artifact and moving alias `champion` only when `should_promote` says so; `place_catalog` writes `s3://recommender/features/movies.parquet` (catalog + `vector:list[float32]` + `bias:float`) for the champion. Couple feedback for training is read from `s3://recommender/feedback/events/` (Task 12 format).
- Wiring as in `labs/ml/drift/pipeline/pipeline.py::_wire`: secret `kfp-s3`, Garage env, `MLFLOW_TRACKING_URI=http://mlflow.mlflow.svc.cluster.local`, pull policy `Always`, caching off. Image `os.environ["REC_IMAGE"]`. `collect_coupang` gets `pause=1.0` and a `max_pages` parameter (default 0 = no limit) so a first run can be capped.
- [ ] **Step 1: Failing test**: both pipelines compile with `kfp.compiler.Compiler().compile` into a temp dir; the training YAML contains `movie-recommender`; no component input is named like `*secret*`, `*password*` or `*key*`.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Live run**: `run.py catalog --max-pages 200` then `run.py training`; check the KFP UI, the MLflow run with `val_auc`, `precision_10`, `recall_10`, and the `champion` alias. Record timings and metrics in `BLOG_NOTES.md`. Then start the full Coupang pass (`run.py catalog`, about 5 hours). **Step 6: Commit** `feat: add the catalog and training pipelines`.

### Task 10: Feast repository

**Files:** Create `feature_repo/features.py`, `feast_config.py`; Test `tests/test_feast_repo.py`

**Interfaces:**
- Produces: entities `movie` (join key `movie_key: str`), `viewer` (`viewer_id: str`); feature view `movie_features` (source `s3://recommender/features/movies.parquet`, fields `title, services, genres, popularity_kr, new_this_week, vector, bias, poster_url`); feature view `viewer_taste` with a `PushSource` named `viewer_taste_push` (fields `vector: Array(Float32)`, `updated_at`). `write_config(dest_dir: Path, valkey_connection: str, registry: str = "s3://recommender/feast/registry.db") -> Path` — builds `feature_store.yaml` with project `movie_recommender`, online store `redis` whose connection string is the seeded one with `db=1` replaced by `db=2`; the seeded string is read from `feature-registry/feature_store_local.yaml` at run time and never written to disk outside `dest_dir` or printed.
- [ ] **Step 1: Failing test**: `write_config` on a fake seeded string `"localhost:16379,db=1,password=x"` yields a YAML with `db=2` and project `movie_recommender`; `feast plan` style check: `FeatureStore(repo_path=tmp).apply([...])` with a local sqlite registry and SQLite online store accepts the definitions.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Live**: from the Mac with `feast/pf.sh` tunnels, `python feast_config.py --apply` applies to the Garage registry and materializes `movie_features`. **Step 6: Commit** `feat: define the recommender's Feast features`.

### Task 11: Fold-in (real-time taste)

**Files:** Create `recommender/core/foldin.py`; Test `tests/test_foldin.py`

**Interfaces:**
- Produces: `genre_prior(catalog_vecs: np.ndarray, genres_per_row: list[list[str]], popularity: np.ndarray, chosen: list[str], top_n: int = 50) -> np.ndarray` (popularity-weighted mean vector of the `top_n` most popular movies sharing a chosen genre; zero vector if `chosen` is empty); `fold_in(item_vecs: np.ndarray, item_bias: np.ndarray, global_bias: float, labels: np.ndarray, prior: np.ndarray, l2: float = 1.0, iters: int = 25) -> np.ndarray` — L2-regularized logistic regression on the user vector toward `prior`, Newton steps (dim ≤ 64, so a dense solve per step).
- [ ] **Step 1: Failing tests**: `test_foldin_without_feedback_returns_prior` (empty labels → exactly `prior`); with 10 👍 on items along `+e0` and 10 👎 along `-e0`, the result's `e0` coordinate is > 0 and the predicted probability of a new `+e0` item > 0.7; runtime for 200 labels and dim 32 under 20 ms (`time.perf_counter`).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Commit** `feat: fold a viewer's taste in from their thumbs`.

### Task 12: Ranking, veto and state

**Files:** Create `recommender/core/rank.py`, `recommender/core/state.py`; Test `tests/test_rank.py`, `tests/test_state.py`

**Interfaces:**
- Consumes: `fold_in`, `genre_prior`, catalog frame with `vector, bias`, config constants.
- Produces:
  - `state.Event` dataclass `kind: Literal["genres","mark","watched"], viewer: str | None, movie_key: str | None, liked: bool | None, genres: list[str] | None, at: datetime`; `to_json/from_json`; `replay(events: Iterable[Event]) -> dict[str, ViewerState]` with `ViewerState(genres: list[str], liked: set[str], disliked: set[str])` plus `watched: set[str]` on a `CoupleState`; later events win for the same viewer and movie.
  - `rank.recommend(catalog: pd.DataFrame, global_bias: float, taste: dict[str, np.ndarray], couple: CoupleState) -> list[dict]` — each dict `movie_key, title, poster_url, services:list[str] (display names), new_this_week, p_me, p_wife, gamble: bool, reason: str`.
  - Scoring: `p = sigmoid(u·v + b + global_bias + 0.3 * shares_chosen_genre - penalty)`, `penalty = max(0, cos_max_to_viewer_dislikes - 0.7) / 0.3`; veto and gamble refill per Global Constraints; exclusions per Global Constraints.
  - Reason copy (Korean, exact): shared 👍 nearest → `"둘 다 좋아한 '{title}'과 비슷해요"`; else the viewer with the higher p → `"{label}이(가) 좋아한 '{title}'과 비슷해요"`; no 👍 at all → `"{genre_label} 장르에서 한국 인기작이에요"`.
- [ ] **Step 1: Failing tests**:
  - `test_veto_drops_movie_one_dislikes` (p_me 0.9, p_wife 0.3 → absent);
  - `test_rank_by_lower_score` (0.8/0.6 ranks above 0.95/0.5);
  - `test_gamble_refill_to_five` (3 survivors + 4 in [0.20, 0.35) → 5 results, the last 2 `gamble`, none below 0.20);
  - `test_never_more_than_ten`;
  - `test_excludes_marked_and_watched`;
  - `test_rank_with_empty_viewer_uses_popularity` (no genres, no marks → results ordered by `popularity_kr`, reason uses the genre-popularity copy);
  - `test_reason_prefers_shared_like`;
  - `test_state_replay_rebuilds_marks_and_watched` (a 👍 then 👎 on the same movie leaves it disliked; watched survives replay).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Commit** `feat: rank with the couple's veto and give reasons`.

### Task 13: Phone web UI

**Files:** Create `web/index.html`, `web/app.js`, `web/style.css`; Test `tests/test_web_static.py`

**Interfaces:**
- Consumes the API of Task 14 (paths below). Screens follow the approved mockup (`.superpowers/brainstorm/15325-1793847089/content/onboarding-flow.html`):
  1. profile buttons "🙋 나" / "🙋‍♀️ 아내"; 2. genre chips from `GET /api/genres` (Korean labels, multi-select, "다음"); 3. poster grid from `GET /api/onboarding?viewer=&offset=` — tap a poster → 👍/👎 buttons (option A) → `POST /api/mark`; untapped posters are ignored; infinite scroll by `offset`; "추천 보기"; 4. picks from `GET /api/recommendations`: poster, title, service badges, "이번 주 새로 올라옴" when `new_this_week`, "조금 모험" when `gamble`, reason line; "같이 봤어요" → `POST /api/watched`, then each profile's 👍/👎 → `POST /api/mark` with `source: "watched"`.
- Mobile-first: `<meta name="viewport" content="width=device-width, initial-scale=1">`, one column, tap targets ≥ 44 px, no external scripts or fonts (works offline on the LAN).
- [ ] **Step 1: Failing test**: `index.html` has the viewport meta, references only local `app.js`/`style.css`, and `app.js` calls exactly the six API paths of Task 14.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Commit** `feat: add the phone UI for marking movies and weekend picks`.

### Task 14: BentoML service and API

**Files:** Create `serving/api.py`, `serving/service.py`, `serving/bentofile.yaml`, `serving/requirements.txt`; Test `tests/test_api.py`

**Interfaces:**
- Consumes: Tasks 10–13, `s3.py`, `feast_config.write_config`.
- Produces: `api.create_app(store: Store) -> FastAPI` where `Store` is a Protocol with `catalog() -> pd.DataFrame`, `global_bias() -> float`, `append(event: Event) -> None` (writes `s3://recommender/feedback/events/<iso>-<uuid>.json`), `events() -> list[Event]`, `push_taste(viewer: str, vector: np.ndarray) -> None` (Feast `push("viewer_taste_push", …)`), `taste(viewer) -> np.ndarray | None`. Routes:
  - `GET /api/genres` → `[{id, label}]` from `CANONICAL`/`KOREAN_LABEL`;
  - `POST /api/viewer/{viewer}/genres` body `{genres: [..]}`;
  - `GET /api/onboarding?viewer=&offset=0&limit=30` → posters of chosen genres by `popularity_kr`, excluding that viewer's marks;
  - `POST /api/mark` body `{viewer, movie_key, liked, source: "onboarding"|"watched"}` → append, refold that viewer, push taste, return `{ok: true}`;
  - `POST /api/watched` body `{movie_key}`;
  - `GET /api/recommendations` → `rank.recommend(...)`.
  - Unknown `viewer` → 404; unknown `movie_key` → 404; static `web/` mounted at `/`.
- `service.py`: `@bentoml.service(name="movie_recommender", workers=1)` with `@bentoml.asgi_app(app, path="/")`; at start loads the champion arrays from MLflow (`models:/movie-recommender@champion`), writes Feast config via `write_config`, replays events, refolds both viewers; a background thread reloads `features/movies.parquet` and re-materializes every 6 hours. `Settings.from_env()` reads `MLFLOW_TRACKING_URI, EVIDENTLY_URL, S3_ENDPOINT, VALKEY_ADDRESS` (no defaults with IPs).
- [ ] **Step 1: Failing tests** with an in-memory `Store`: onboarding excludes marked movies; `POST /api/mark` changes the next `/api/recommendations` (the marked movie disappears and a similar one moves up); unknown viewer → 404; `test_settings_come_from_env` (missing `MLFLOW_TRACKING_URI` raises a clear error, values are taken verbatim from env).
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Commit** `feat: serve recommendations and learn from marks in BentoML`.

### Task 15: Build, run and LAN entry

**Files:** Create `serving/build.sh`, `serving/run.sh`; Modify `labs/ml/recommender/README.md`

**Interfaces:** `build.sh` mirrors `labs/ml/serving/build.sh` (bentoml build from `labs/ml/recommender`, containerize for host arch, tag `movie-recommender:<bento-tag>`); `run.sh` mirrors `labs/ml/serving/run.sh`: `docker rm -f movie-rec`, `docker run -d --name movie-rec --network kind -p 0.0.0.0:3100:3000 --add-host host.docker.internal:host-gateway`, credentials from `kubeflow/kfp-s3` at run time, `S3_ENDPOINT=host.docker.internal:3900`, `VALKEY_ADDRESS=host.docker.internal:16379`, `MLFLOW_TRACKING_URI=$MLFLOW_URL`, `EVIDENTLY_URL=$EVIDENTLY_URL`; waits for `/readyz`; prints `http://$(ipconfig getifaddr en0):3100`.
- [ ] **Step 1:** Write both scripts; `bash -n` both. **Step 2: Run** `feast/pf.sh`, `build.sh`, `run.sh`; `curl -s http://127.0.0.1:3100/api/genres` returns 20 genres; open the printed LAN URL on the phone (macOS may ask to allow incoming connections). **Step 3:** Walk the four screens on the phone with real data; screenshot each for `BLOG_NOTES.md`. **Step 4: Commit** `feat: run the recommender on the home network`.

### Task 16: Evidently monitoring

**Files:** Create `recommender/monitoring.py`, `pipeline/monitoring_pipeline.py`; Test `tests/test_monitoring.py`

**Interfaces:**
- Produces: `weekly_frames(events: list[Event], catalog_now: pd.DataFrame, catalog_before: pd.DataFrame, taste_now: dict, taste_before: dict) -> dict[str, pd.DataFrame]` — `watched` (one row per watched movie: `both_liked: int` 1 if both later marked 👍, `week`), `genre_mix_now/before` (share per canonical genre), `taste_now/before` (rows per viewer, columns `d0..dN`); `report(frames, evidently_url: str, project: str = "movie-recommender") -> None` uploading one snapshot with a joint-👍 rate value and `DataDriftPreset` on genre mix and taste; reuse `ensure_project` from `labs/ml/drift/pipeline/src/drift_steps.py`. Pipeline `movie-recommender-monitoring` runs it; schedule weekly via a KFP recurring run created in `run.py monitoring --weekly`.
- [ ] **Step 1: Failing tests**: two watched movies, one liked by both and one by only one → rate 0.5; genre mix shares sum to 1.
- [ ] **Step 2–4:** FAIL → implement → PASS. **Step 5: Live**: run once; the snapshot appears in the Evidently project `movie-recommender`. **Step 6: Commit** `feat: report the joint-like rate and drift to Evidently weekly`.

### Task 17: Schedules, docs, end-to-end check

**Files:** Modify `labs/ml/recommender/README.md`, `BLOG_NOTES.md`, `labs/ml/README.md` (one pointer line), `docs/traps.md` if a new trap was hit

- [ ] **Step 1:** Create recurring runs: `movie-catalog` daily 05:00 KST, `movie-recommender-training` weekly Monday 06:00 KST, monitoring weekly Monday 07:00 KST (`run.py … --schedule`).
- [ ] **Step 2:** README: prerequisites (`install --with-ml`, `feast/pf.sh`, `.venv-rec`), the order (catalog → training → feast apply → build → run), phone URL, OrbStack restart recovery (rerun `ml-gateways`/`ml-platform`, `pf.sh`, `run.sh`), the Coupang crawl rule and its `robots.txt` context, JustWatch credit.
- [ ] **Step 3: End-to-end**: both profiles onboard about 20 movies each on the phone; `/api/recommendations` returns 5–10 items, none marked, none either is predicted to dislike below 0.20; mark one as watched and rate it; the next request reflects it; restart the container and confirm nothing was lost. Run `.venv-rec/bin/pytest -q` and `npx vitest run`; both green.
- [ ] **Step 4: Commit** `docs: document the movie recommender exercise`.
