# ML lab exercises

Exercises for the ML layer that `install --with-ml` adds to the bakery lab: MLflow, JupyterLab, Feast and Kubeflow Pipelines, each reachable through a cloud-provider-kind gateway under an `sslip.io` name.

The installer already did the platform part:

| Done by `install --with-ml` | Where |
|---|---|
| Garage buckets `mlflow`, `mlflow-datasets`, `feature-registry`, `feature-data-sets`, `inference-datasets`, `mlpipeline` and one key per consumer | Garage in namespace `gitlab` |
| Secrets `mlflow-s3`, `jupyter-token`, `feast-s3`, `feast-online-store`, `kfp-s3`, `kfp-garage-artifact` | namespaces `mlflow`, `feast`, `kubeflow` |
| Argo CD apps `mlflow`, `jupyter`, `feast-operator`, `feast-store`, `kfp` | `devops/platform` in GitLab |
| Example datasets, both Feast registries, 30,162 users in the online store | seed Jobs `ml-seed-features`, `ml-seed-inference` |
| Pipeline image `kfp/income-pipeline:0.1.0` | Harbor |

What is left are the exercises themselves: train a model, pick the serving version, run the pipeline.

## Before you start

```bash
brew install cloud-provider-kind
sudo cloud-provider-kind          # keep it running in its own terminal
source labs/ml/env.sh             # BAKERY_CONTEXT, MLFLOW_URL, JUPYTER_URL, FEAST_URL, KFP_URL, KFP_IMAGE
```

`npx github:victor-jo/gitops-bakery status` prints the same URLs. The Jupyter token is `jupyterToken` in `~/.gitops-bakery/secrets.json`.

Mac-side Python (3.13) is needed only for the Feast and KFP exercises:

```bash
python3 -m venv labs/ml/.venv     && labs/ml/.venv/bin/pip install -r labs/ml/requirements.txt
python3 -m venv labs/ml/.venv-kfp && labs/ml/.venv-kfp/bin/pip install -r labs/ml/requirements-kfp.txt
```

The two are separate because the KFP SDK and Feast pin conflicting packages.

## 1. Train and register a model (MLflow)

Open `$JUPYTER_URL`, then `work/mlflow/data_exploration_and_model_training.ipynb`, and run it. Or run it headless inside the pod:

```bash
labs/ml/mlflow/train.sh
```

The notebook is the upstream example fetched at a pinned commit and rewritten by `assets/gitops/platform-ml/jupyter/manifests/patch_notebook.py`, which:
- reads MLflow and Garage settings from the environment;
- signs with region `garage`;
- logs models as skops with trusted types;
- registers the best non-XGBoost run as `income-classifier-best`.

## 2. Choose the serving version

MLflow registry stages are deprecated, so the pipeline asks for the alias `champion`:

```bash
labs/ml/mlflow/set_champion.sh       # newest version
labs/ml/mlflow/set_champion.sh 2     # or a specific one
```

## 3. Read features (Feast)

Garage and Valkey stay ClusterIP, so the Mac reaches them through two tunnels:

```bash
labs/ml/feast/pf.sh
export AWS_ACCESS_KEY_ID=$(kubectl --context $BAKERY_CONTEXT -n feast get secret feast-s3 -o jsonpath='{.data.AWS_ACCESS_KEY_ID}' | base64 -d)
export AWS_SECRET_ACCESS_KEY=$(kubectl --context $BAKERY_CONTEXT -n feast get secret feast-s3 -o jsonpath='{.data.AWS_SECRET_ACCESS_KEY}' | base64 -d)
labs/ml/.venv/bin/python labs/ml/feast/retrieve.py
```

The online server answers without any tunnel:

```bash
curl -s "$FEAST_URL/get-online-features" -H 'Content-Type: application/json' \
  -d '{"features": ["demographic:Sex"], "entities": {"user_id": ["74b0638a-5742-4d1a-a03f-483794d7aa7c"]}}'
```

## 4. Run the steps on the Mac first

`kfp/run_local.sh` runs the upstream step code one step at a time (`1` to `4`, or all). It fetches that code with `kfp/upstream/fetch.sh` and applies `kfp/upstream/lab.patch`, which adds the Garage region and switches the model lookup from stage to alias. It needs the Garage tunnel from `pf.sh`.

```bash
labs/ml/kfp/run_local.sh        # out/3_predictions.parquet has 30,162 rows
```

## 5. Run the pipeline (KFP)

```bash
cd labs/ml/kfp/pipeline
../../.venv-kfp/bin/python pipeline.py          # compiles income_batch_inference.yaml with $KFP_IMAGE
../../.venv-kfp/bin/python run.py               # one run, waits for it
../../.venv-kfp/bin/python publish_and_run.py   # upload, experiment, run: the UI flow through the SDK
```

The predictions land in `s3://inference-datasets/predictions_kfp.parquet`, and the run is visible at `$KFP_URL`. `kfp/smoke/` has two tiny pipelines that check scheduling and artifact passing on their own.

## Rebuilding the pipeline image

The installer builds `kfp/pipeline/src` for the host architecture and pushes it. To rebuild it after editing `steps.py`:

```bash
docker build --platform linux/$(uname -m | sed 's/x86_64/amd64/') -t localhost:30001/kfp/income-pipeline:0.1.0 labs/ml/kfp/pipeline/src
docker push localhost:30001/kfp/income-pipeline:0.1.0     # after docker login localhost:30001 -u admin
```

`kfp component build` always targets amd64, which is why the Dockerfile it generated is built directly.
