# Weekend movie recommender

A movie recommender for two people, `me` (나) and `wife` (아내), built on the ML lab. It collects what Netflix, Disney+ and Coupang Play show in Korea, trains a matrix-factorisation model on MovieLens 25M, and serves a phone page on the home Wi-Fi. Each person marks posters 👍 or 👎. The page then lists this weekend's movies that both of them should like: a movie is dropped when either person's predicted like-probability is below 0.35.

| Piece | Where |
|---|---|
| Catalog and training pipelines (KFP) | `pipeline/`, image `kfp/recommender-pipeline:0.1.0` (`$REC_IMAGE`) |
| Catalog, features, feedback events | Garage bucket `recommender` (`catalog/`, `features/movies.parquet`, `feedback/events/`) |
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
# 1. Catalog: JustWatch (Netflix, Disney+) and Coupang Play -> catalog/ in Garage.
#    The first full Coupang pass takes hours at one page per second; --max-pages caps it for a quick run.
.venv-rec/bin/python pipeline/run.py catalog
# 2. Training: MovieLens + catalog -> MLflow run, gate, champion, features/movies.parquet
.venv-rec/bin/python pipeline/run.py training
# 3. Feast: apply the definitions and materialize the movie features (needs the tunnels)
bash ../feast/pf.sh                                      # Garage on 3900, Valkey on 16379
FEAST_S3_ENDPOINT_URL=http://localhost:3900 .venv-rec/bin/python feast_config.py --apply
# 4. Build: bentoml build + containerize for the host architecture -> movie-recommender:<bento tag>
serving/build.sh
# 5. Tunnels: the container reaches Garage and Valkey through them; run.sh stops if either is down
bash ../feast/pf.sh                                      # rerun it: a no-op when both ports already listen
# 6. Run: docker run on the kind network, published on 0.0.0.0:3100
serving/run.sh                                           # prints the phone URL
```

`run.sh` reads the credentials from `kubeflow/kfp-s3` when it starts the container; they are never baked into the image. The container reaches the tunnels as `host.docker.internal`, and MLflow artifacts come through the MLflow server (`MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false`), because the presigned Garage URLs do not resolve outside the cluster.

The container re-applies the Feast definitions at start-up, and reloads the catalog every 6 hours. The Feast registry's file-source endpoint is whatever the last process to apply wrote: `localhost:3900` after a Mac-side `feast_config.py --apply`, `host.docker.internal:3900` after the container starts. Each process applies before it materializes, so both work, but the registry shows only the last one. A rebuild is needed only when the code changes. A new champion or catalog needs only a `docker restart movie-rec`, or a wait for the next reload.

## Open it on the phone

`run.sh` ends with `ready: http://<Mac LAN IP>:3100`, e.g. `http://192.168.1.60:3100` (the address of `en0`). Open it on a phone on the same Wi-Fi. The Mac must be on and awake. If macOS asks whether to accept incoming connections, allow them. The address can change when the router hands out another lease, so `ipconfig getifaddr en0` gives the current one.

On the Mac itself use `http://127.0.0.1:3100`, not `localhost`: OrbStack also listens on `::1` for the mapped port but never answers there.

The page has four screens: choose a profile, pick favourite genres, mark posters 👍/👎, and this weekend's candidates. After watching one, press "같이 봤어요" and both rate it.

Every mark is an event in `s3://recommender/feedback/events/`, one JSON object per mark, so the couple's state survives a restart or a rebuild. The same marks refold that person's taste vector in the service and push it to Feast (`viewer_taste`).

## After an OrbStack restart

The kind network addresses change, so the sslip.io names in `~/.gitops-bakery/state.json` and the gateways break:

1. Stop `sudo cloud-provider-kind`, then `docker rm -f` every `kindccm*` container.
2. Start `sudo cloud-provider-kind` again.
3. Remove `ml-gateways` and `ml-platform` from `steps` in `~/.gitops-bakery/state.json` and run `npx github:victor-jo/gitops-bakery install --with-ml`.
4. `bash labs/ml/feast/pf.sh` (the port-forwards died with the cluster), then `serving/run.sh`. It sources `env.sh` again, so the container gets the new MLflow and Evidently URLs. The image does not need a rebuild.

## Sources and their rules

- **JustWatch** (Netflix `nfx` and Disney+ `dnp`, country `KR`): data from [JustWatch](https://www.justwatch.com). The GraphQL endpoint `https://apis.justwatch.com/graphql` is unofficial. The collector waits at least 0.3 s between requests and fetches `popularTitles` in release-year slices, because deep paging stops near 1,900 results.
- **Coupang Play**: there is no catalog API we may use. `robots.txt` disallows `/api`, allows user-requested AI retrieval (`Claude-User`) on `/content`, and carries `Content-Signal: ai-train=no`. The owner knew this and chose to read the public pages anyway, under these rules:
  - read only `https://www.coupangplay.com/sitemap.xml` and `/content/<uuid>` pages, never an `/api` path;
  - at most one request per second;
  - one full pass, then only URLs not yet cached.
  The descriptions and cast are used as content features to place new movies. The sitemap may be stale, so movies added after it can be missing.
- **MovieLens 25M**: GroupLens, non-commercial research licence, fine for this personal lab.

Posters are loaded by the phone straight from JustWatch's and Coupang's image servers. Nothing is stored in this repository.
