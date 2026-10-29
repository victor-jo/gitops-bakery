#!/usr/bin/env bash
# Runs the four upstream pipeline steps on the Mac (Garage through its tunnel, MLflow through its domain), one step at a time
set -euo pipefail
cd "$(dirname "$0")"
source ../env.sh
CTX=$BAKERY_CONTEXT
upstream/fetch.sh >/dev/null
UP="$PWD/upstream/chapter-5/src"
key() { kubectl --context $CTX -n kubeflow get secret kfp-s3 -o jsonpath="{.data.$1}" | base64 -d; }
AK=$(key AWS_ACCESS_KEY_ID); SK=$(key AWS_SECRET_ACCESS_KEY)
HOST=localhost:3900
PY="$PWD/../.venv/bin/python"
export MLFLOW_DISABLE_AGENT_HINT=1
export S3_REGION=garage AWS_DEFAULT_REGION=garage
FEATURES="demographic:Sex,demographic:Race,demographic:Native_country,relationship:Relationship,relationship:Marital-Status,occupation:Workclass,occupation:Education,occupation:Occupation"
mkdir -p out
S="${1:-all}"
run() { [ "$S" = all ] || [ "$S" = "$1" ]; }
if run 1; then
  "$PY" "$UP/read_data/read_data.py" --minio_host $HOST --access_key "$AK" --secret_key "$SK" \
    --bucket_name inference-datasets --file_name entity_df.parquet --data_output_path out/1_entity.parquet
fi
if run 2; then
  mkdir -p out/step2
  (cd out/step2 && "$PY" "$UP/retrieve_features/retrieve_features.py" --minio_host $HOST --access_key "$AK" --secret_key "$SK" \
    --bucket_name feature-registry --file_name feature_store_local.yaml --entity_df ../1_entity.parquet \
    --feature_list "$FEATURES" --data_output ../2_features.parquet)
fi
if run 3; then
  # MLflow is reached through its cloud-provider-kind Ingress domain, so no tunnel is needed
  export MLFLOW_HTTP_REQUEST_TIMEOUT=60 MLFLOW_HTTP_REQUEST_MAX_RETRIES=2
  # The server hands out presigned Garage URLs with an in-cluster host the Mac cannot resolve; download through the server instead
  export MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false
  "$PY" "$UP/run_inference/run_inference.py" --minio_host $HOST --access_key "$AK" --secret_key "$SK" \
    --model_name income-classifier-best --model_type sklearn --model_alias "${MODEL_ALIAS:-champion}" \
    --mlflow_host "$MLFLOW_URL" --input_data out/2_features.parquet --data_output out/3_predictions.parquet
fi
if run 4; then
  (cd out && "$PY" "$UP/write_data/write_data.py" --minio_host $HOST --access_key "$AK" --secret_key "$SK" \
    --bucket_name inference-datasets --file_name predictions.parquet --input_data_path 3_predictions.parquet)
fi
