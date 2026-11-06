# Weekend movie recommender

A movie recommender for two people, `me` (나) and `wife` (아내), built on the ML lab. It collects what Netflix, Disney+ and Coupang Play show in Korea, trains a matrix-factorisation model on MovieLens 25M, and serves a phone page on the home Wi-Fi. Each person marks posters 👍 or 👎. The page then lists this weekend's movies that both of them should like: a movie is dropped when either person's predicted like-probability is below 0.35. After those picks it keeps going with the movies most watched in Korea.

| Piece | Where |
|---|---|
| Catalog and training pipelines (KFP) | `pipeline/`, image `kfp/recommender-pipeline:0.1.0` (`$REC_IMAGE`) |
| Catalog, features, feedback events | Garage bucket `recommender` (`catalog/`, `features/movie_{catalog,popularity,embedding}.parquet`, `feedback/events/`) |
| Model | MLflow experiment and registered model `movie-recommender`, alias `champion` |
| Features | Feast project `movie_recommender`, registry `s3://recommender/feast/registry.db`, online store Valkey `db=2` |
| Service and phone UI | BentoML `serving/` + `web/`, container `movie-rec`, port 3100 on the Mac |

## Before you start

The lab must be up with `install --with-ml`, and `sudo cloud-provider-kind` must be running (see `labs/ml/README.md`).

```bash
source labs/ml/env.sh        # BAKERY_CONTEXT, MLFLOW_URL, KFP_URL, EVIDENTLY_URL, REC_IMAGE
python3.13 -m venv labs/ml/recommender/.venv-rec
labs/ml/recommender/.venv-rec/bin/pip install --extra-index-url https://download.pytorch.org/whl/cpu \
  -r labs/ml/recommender/requirements.txt
cd labs/ml/recommender && .venv-rec/bin/pytest -q && cd -     # offline unit tests
```

The Mac-side steps read Garage with the `kfp` key. Pass it through the environment and never print it:

```bash
key() { kubectl --context "$BAKERY_CONTEXT" -n kubeflow get secret kfp-s3 -o jsonpath="{.data.$1}" | base64 -d; }
export AWS_ACCESS_KEY_ID="$(key AWS_ACCESS_KEY_ID)" AWS_SECRET_ACCESS_KEY="$(key AWS_SECRET_ACCESS_KEY)"
```

## Run it, in this order

```bash
cd labs/ml/recommender
# 1. Catalog: JustWatch (Netflix, Disney+) and Coupang Play -> catalog/ in Garage, then
#    features/movie_catalog.parquet and features/movie_popularity.parquet.
#    The first full Coupang pass takes hours at one page per second; --max-pages caps it for a quick run.
.venv-rec/bin/python pipeline/run.py catalog
# 2. Training: MovieLens + catalog -> MLflow run, gate, champion, features/movie_embedding.parquet
.venv-rec/bin/python pipeline/run.py training
# Monitoring (any time): joint thumbs-up rate, genre drift and taste shift -> Evidently project movie-recommender
.venv-rec/bin/python pipeline/run.py monitoring
# 3. Feast: apply the definitions and materialize the movie features (needs the tunnels)
serving/tunnels.sh                                       # supervised Garage on 3900, Valkey on 16379
FEAST_S3_ENDPOINT_URL=http://localhost:3900 .venv-rec/bin/python feast_config.py --apply
# 4. Build: bentoml build + containerize for the host architecture -> movie-recommender:<bento tag>
serving/build.sh
# 5. Run: brings up the supervised tunnels (serving/tunnels.sh), then docker run on the kind network, 0.0.0.0:3100
serving/run.sh                                           # prints the phone URL
```

`run.sh` reads the credentials from `kubeflow/kfp-s3` when it starts the container; they are never baked into the image. The container reaches the tunnels as `host.docker.internal`, and MLflow artifacts come through the MLflow server (`MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false`), because the presigned Garage URLs do not resolve outside the cluster.

The container re-applies the Feast definitions at start-up, and reloads the catalog every 6 hours. The Feast registry's file-source endpoint is whatever the last process to apply wrote: `localhost:3900` after a Mac-side `feast_config.py --apply`, `host.docker.internal:3900` after the container starts. Each process applies before it materializes, so both work, but the registry shows only the last one. A rebuild is needed only when the code changes. The daily catalog run rewrites the catalog and popularity parquets and the daily training run rewrites the embedding parquet, so a new catalog or champion needs only a `docker restart movie-rec`, or a wait for the next reload.

## Movie features

The movie features are split by who writes them and how often. Each Feast feature view has its own parquet under `s3://recommender/features/`, and every row carries the `event_timestamp` of the write. The views are defined in `feature_repo/features.py` and the writers and the reader in `recommender/movie_features.py`.

| Feature view | Parquet | Written by | Fields | TTL |
|---|---|---|---|---|
| `movie_catalog` | `features/movie_catalog.parquet` | catalog run (`match_and_build`), daily | `title`, `services`, `genres`, `release_year`, `korean`, `new_this_week`, `poster_url`, `description`, `actors` (for the liked-movie tabs' content similarity), `review_rating` | 7 days |
| `movie_popularity` | `features/movie_popularity.parquet` | catalog run (`match_and_build`), daily | `popularity_kr` | 2 days |
| `movie_embedding` | `features/movie_embedding.parquet` | training run (`place_catalog`) | `vector`, `bias`, `model_version` (the champion's registered version) | 3650 days |

The service and the monitoring report join the three on `movie_key` in catalog order. A movie the champion has not placed yet has no vector, so it is left out until the next training run places it. A placed movie that has left the catalog drops out with the catalog run.

The catalog run no longer places movies, so a new title appears in the picks only after the next training run.

**Upgrading from the single `features/movies.parquet`.** Until all three parquets exist, the service and the monitoring report read the old `features/movies.parquet` as before, and the service materializes nothing. Run the pipelines once in this order, then restart the service or wait for its next reload:

1. `pipeline/run.py catalog` writes the catalog and popularity parquets.
2. `pipeline/run.py training` writes the embedding parquet.
3. `feast_config.py --apply` (or a service restart) applies and materializes the three views.

Applying registers the new views but does not delete the old `movie_features` view from the registry. Once nothing reads it, remove it with `FeatureStore(repo_path=...).delete_feature_view("movie_features")` from a store configured by `feast_config.write_config`.

The container reaches Garage and Valkey through two Mac-side port-forwards. `serving/tunnels.sh` (run by `run.sh`) keeps each one in a `while true; do kubectl port-forward ...; sleep 2; done` loop, so a dropped forward comes back within seconds. Logs and pid files are `/tmp/movie-rec-tunnel-<port>.{log,pid}`, and a second call does not start a duplicate. If a port already listens (for example from `labs/ml/feast/pf.sh`), it is left alone and is not supervised.

**Picks show but 👍/👎 fails → run `serving/tunnels.sh`.** Picks fall back to the in-memory tastes when Valkey is unreachable, but every mark is written to Garage, so a dead tunnel shows up first as a failing mark (and as `taste of <viewer> comes from memory` warnings in the container log).

## Model: plain MF or hybrid

The training step takes `model_type`. The default is `hybrid`, which feeds genres, release decade, the Korean flag and popularity into the model. `mf` remains as an explicit option: it learns from ids alone, so those signals reach the picks only as ranking rules after scoring. The hybrid model:

```
item_vec[i]  = item_emb[i]  + W f[i]
item_bias[i] = item_bias[i] + w · f[i]
logit(u, i)  = user_vec[u] · item_vec[i] + user_bias[u] + item_bias[i] + global_bias
```

`f[i]` is fixed per MovieLens movie (`recommender/model/item_features.py`):

| Feature | Columns | Source |
|---|---|---|
| Genres | 20, multi-hot | MovieLens genres mapped to the shared vocabulary |
| Release decade | 14, one-hot (1900s–2020s, unknown) | the year at the end of the MovieLens title, bucketed as the content model does |
| Korean | 1 | today's catalog (Hangul original title); MovieLens has no language, so only MovieLens movies in the catalog can carry it (388 on 2026-11-05) |
| Popularity | 1 | `log1p` of the movie's training rows, standardized; held-out rows are not counted |

`W` and `w` start at zero, so training begins from the plain MF and learns what the features add. The loss, optimizer, epochs and seed are the MF's. The score stays linear in the user vector. `export` writes the summed vectors and biases to `arrays.npz` in the MF layout, so the gate, the fold-in, the content model that places catalog movies and the service read a hybrid run unchanged.

```bash
.venv-rec/bin/python pipeline/run.py training                    # hybrid, the default (KFP parameter model_type)
.venv-rec/bin/python pipeline/run.py training --model-type mf    # plain MF
.venv-rec/bin/python pipeline/run.py training --weight-decay 1e-5   # Adam L2; the default is 0 (KFP parameter weight_decay)
```

**Weight decay is 0 by default.** Training used Adam with `weight_decay=1e-5`. That L2 pulled the MF item vectors onto one popularity axis: 97% of their variance lay on the first principal axis. The same holdout rows the gate uses (6,250,024, full ml-25m) give these numbers:

| Model | weight_decay | val_auc | precision@10 | recall@10 | first-axis variance |
|---|---|---|---|---|---|
| MF | 1e-5 | 0.7631 | 0.4614 | 0.8316 | 97.4% |
| MF | 0 | 0.8174 | 0.4735 | 0.8402 | 10.4% |
| hybrid (champion v8) | 1e-5 | 0.8036 | 0.4671 | 0.8357 | 28.3% |
| hybrid | 0 | 0.8212 | 0.4749 | 0.8415 | 10.5% |

The component passes `model_type` and `weight_decay` to `steps.train`, so a pipeline compiled from this code needs a pipeline image built from it too. Each run logs both as MLflow parameters. A new champion exists only after a run passes the gate. The hybrid's first numbers against the MF champion are in `BLOG_NOTES.md`.

## Schedules

Each pipeline takes `--schedule` to create a KFP recurring run instead of a single run:

```bash
cd labs/ml/recommender && source ../env.sh
for p in catalog training monitoring; do .venv-rec/bin/python pipeline/run.py $p --schedule; done
```

| Recurring run | When (KST) | Cron in UTC |
|---|---|---|
| `movie-catalog` | every day 05:00 | `0 0 20 * * *` |
| `movie-recommender-training` | every day 06:00 | `0 0 21 * * *` |
| `movie-recommender-monitoring` | Monday 07:00 | `0 0 22 * * 0` |

- Creating is idempotent: the new recurring run is created first, then every older one with the same name is deleted, so rerunning the command never leaves duplicates and a failed create keeps the old schedule.
- All three use `max_concurrency=1` and `no_catchup`. That matters most for the catalog: the first Coupang pass takes hours, and a daily trigger must not start a second crawl while one is running. After the first pass only new URLs and 300 rechecks (about 5 minutes) are fetched, so the daily run is short.
- Training runs daily right after the catalog run (about 4 to 4.5 minutes on 4 CPU / 8Gi). Hourly retraining would add little: MovieLens 25M dominates the training data, and new marks already reach the tastes in real time through fold-in.
- Check them in the KFP UI (Recurring runs), or list them:

```bash
.venv-rec/bin/python -c "import os; from kfp import Client; [print(j.recurring_run_id, j.display_name, j.status, j.trigger.cron_schedule.cron) for j in Client(host=os.environ['KFP_URL']).list_recurring_runs(page_size=50).recurring_runs]"
```

The numbers from the first live runs and the end-to-end check are in `BLOG_NOTES.md`.

## Open it on the phone

`run.sh` ends with `ready: http://<Mac LAN IP>:3100`, e.g. `http://192.168.1.60:3100` (the address of `en0`). Open it on a phone on the same Wi-Fi. The Mac must be on and awake. If macOS asks whether to accept incoming connections, allow them. The address can change when the router hands out another lease, so `ipconfig getifaddr en0` gives the current one.

On the Mac itself use `http://127.0.0.1:3100`, not `localhost`: OrbStack also listens on `::1` for the mapped port but never answers there.

The page has four screens: choose a profile, pick favourite genres, mark posters 👍/👎, and this weekend's candidates. After watching one, press "같이 봤어요" and both rate it.

The candidates screen scrolls without end, 20 movies per page of `/api/recommendations?offset=&limit=`. Each item says where it came from:

- `"source": "pick"`: both viewers pass the veto. Picks come first, newest release year first, and movies without a known year come last. Within a year they go by score: the lower of the two like-probabilities (Korean popularity before anyone has given feedback), plus the Korean-film bonus, the recency bonus (which within a year favours the movies more people watch) and the review-rating bonus below.
- `"source": "popular"`: the movies the veto caught, most popular in Korea first, shown under an '인기' divider. A movie still never appears when a viewer's like-probability is below 0.20.

Watched and marked movies are never listed. When both lists run out the screen ends with '더 이상 없어요.'.

Above the list sits a tab row: [전체] (the list above) and then one tab per movie the current profile liked, most recently liked first (`GET /api/viewer/<viewer>/liked`). A liked-movie tab calls `/api/recommendations?viewer=<viewer>&like=<movie_key>`, which answers 422 unless that viewer currently likes that movie. The tab lists the movies that pass the same exclusions and veto as the picks and are at least 0.3 similar to the liked one (`"source": "similar"`, with `"similarity"`). They come most similar first, and newest first when two round to the same whole percent. Each card shows "닮음 NN%" instead of the reason, a tab has no popular fallback, and it ends with '더 이상 없어요.'.

Similarity here is content cosine, built once per catalog load: the canonical genres and a character 2–3-gram TF-IDF of title, description and actors, weighted equally (`recommender/core/similar.py`). The taste vectors cannot be used for it. In the live catalog (9,651 movies, 32 dimensions) the first principal axis carries 81% of their variance, so their cosine puts more than 6,000 movies at 0.7 or above, and 토이 스토리's nearest neighbours come out as 피노키오 and 포레스트 검프 at 1.00. By content, its nearest are 토이 스토리 2, 4 and 5, and 기생충's are 완벽한 타인 and 백수아파트. The measurements are in `/Users/wj.cho/dev/platforms/firstmate/data/rec-feast-read/similarity-evidence.md` on the lab Mac. The reason sentence ("…와 비슷해요") still uses the taste-vector cosine, which is why it names the same liked movie so often.

**Review rating.** The catalog run combines each movie's review scores into one `review_rating` in 0..1 (`recommender/catalog/rating.py`). It uses the IMDb score with its vote count and the TMDB score from JustWatch, and the Coupang Play `aggregateRating` with its count. Scores are rescaled to 0..1 (IMDb 1–10, TMDB 0–10, Coupang 1–5). Votes count in units of that source's median count among rated movies, so IMDb's thousands and Coupang's handfuls weigh alike. TMDB gives no count and weighs a quarter. The result is a Bayesian average with the catalog mean as a prior worth one typical source, so a movie with a few votes stays near the mean. A movie no source rates has no rating.

Within a year, the picks' score gets `RATING_BONUS` (0.5) × the difference between the movie's rating and the catalog mean. An unrated movie gets nothing, neither a lift nor a penalty. Centring matters: an uncentred bonus would hand every rated movie about 0.4, which would bury all unrated ones. On the live catalog, `min(p)` among picks has an interquartile range of 0.035 and the Coupang-based rating about 0.09, so 0.5 lets reviews move the order about as much as taste does, and less than the Korean bonus. The veto, the popular fallback and the liked-movie tabs ignore it. The rating reaches the service through the `movie_catalog` parquet, so it shows up only after a catalog run and a training run have written the three movie parquets (see Movie features). Until then the service reads the legacy `features/movies.parquet`, which has no rating, and the order is unchanged.

This replaced the old fixed list of ten. Every movie that passes the veto is now listed, so the two places per service among the ten (`MIN_PER_SERVICE`) are gone, since keeping them would break the year order. The 조금 모험 refill up to five (`MIN_RESULTS`) is gone too: those movies are now part of the popular list.

Every mark is an event in `s3://recommender/feedback/events/`, one JSON object per mark, so the couple's state survives a restart or a rebuild. The same marks refold that person's taste vector in the service and push it to Feast (`viewer_taste`).

Feast serves the tastes; the event log in Garage stays authoritative. At start-up the service rebuilds both tastes from the log and pushes them to Feast's online store before it serves. Each mark refolds that viewer's taste in the service and pushes it, and the weekend picks read every viewer's taste back from Feast (`viewer_taste:vector`) for scoring, so the next read returns the new vector. When the read fails, returns nothing, has the wrong length, or the viewer's last push has not landed yet, the service scores with its in-memory taste instead and logs one warning naming the viewer and the reason; a failed push is retried on the next request. Movie features stay in the in-memory catalog, read from the parquets described under Movie features: Feast materializes the three movie views after each catalog reload for other consumers, and the app does not read them back from Feast.

## After an OrbStack restart

The kind network addresses change, so the sslip.io names in `~/.gitops-bakery/state.json` and the gateways break:

1. Stop `sudo cloud-provider-kind`, then `docker rm -f` every `kindccm*` container.
2. Start `sudo cloud-provider-kind` again.
3. Remove `ml-gateways` and `ml-platform` from `steps` in `~/.gitops-bakery/state.json` and run `npx github:victor-jo/gitops-bakery install --with-ml`.
4. `serving/run.sh`: its tunnel loops reconnect once the cluster answers again (it starts them if they are not running). It sources `env.sh` again, so the container gets the new MLflow and Evidently URLs. The image does not need a rebuild.

## Sources and their rules

- **JustWatch** (Netflix `nfx` and Disney+ `dnp`, country `KR`): data from [JustWatch](https://www.justwatch.com). The GraphQL endpoint `https://apis.justwatch.com/graphql` is unofficial. The collector waits at least 0.3 s between requests and fetches `popularTitles` in release-year slices, because deep paging stops near 1,900 results.
- **Coupang Play**: there is no catalog API we may use. `robots.txt` disallows `/api`, allows user-requested AI retrieval (`Claude-User`) on `/content`, and carries `Content-Signal: ai-train=no`. The owner knew this and chose to read the public pages anyway, under these rules:
  - read only `https://www.coupangplay.com/sitemap.xml` and `/content/<uuid>` pages, never an `/api` path;
  - at most one request per second;
  - one full pass, then only URLs not yet cached, plus a recheck of the 300 oldest-fetched cached pages per run (a 404/410 marks the title gone, a page without Movie JSON-LD marks it not a movie).
  The catalog keeps only Coupang titles whose URL is in that day's sitemap, so departed titles drop out. The descriptions and cast are used as content features to place new movies. The sitemap may be stale, so movies added after it can be missing.
- **MovieLens 25M**: GroupLens, non-commercial research licence, fine for this personal lab.

Posters are loaded by the phone straight from JustWatch's and Coupang's image servers. Nothing is stored in this repository.
