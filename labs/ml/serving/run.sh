#!/usr/bin/env bash
# Starts the latest income-classifier-drift image on port 3001; needs the Garage and Valkey tunnels from feast/pf.sh
set -euo pipefail
cd "$(dirname "$0")/.."
source ./env.sh
key() { kubectl --context "$BAKERY_CONTEXT" -n kubeflow get secret kfp-s3 -o jsonpath="{.data.$1}" | base64 -d; }
TAG=$(sed 's/^__tag__://' serving/.bento-tag)
docker rm -f income-clf-drift >/dev/null 2>&1 || true
# The kind network reaches the gateways behind the sslip.io names; the tunnels are on the Mac, i.e. host.docker.internal.
# Credentials are passed at run time, never baked into the image as the book's bentofile does.
docker run -d --name income-clf-drift --network kind -p 3001:3000 \
  --add-host host.docker.internal:host-gateway \
  -e AWS_ACCESS_KEY_ID="$(key AWS_ACCESS_KEY_ID)" -e AWS_SECRET_ACCESS_KEY="$(key AWS_SECRET_ACCESS_KEY)" \
  -e S3_ENDPOINT=host.docker.internal:3900 -e S3_REGION=garage -e AWS_DEFAULT_REGION=garage \
  -e FEAST_S3_ENDPOINT_URL=http://host.docker.internal:3900 -e VALKEY_ADDRESS=host.docker.internal:16379 \
  -e MLFLOW_TRACKING_URI="$MLFLOW_URL" -e MLFLOW_DISABLE_AGENT_HINT=1 -e EVIDENTLY_URL="$EVIDENTLY_URL" \
  -e DRIFT_STRENGTH="${DRIFT_STRENGTH:-0}" -e DRIFT_WINDOW_SIZE="${DRIFT_WINDOW_SIZE:-100}" \
  "income-classifier-drift:${TAG#*:}" >/dev/null
echo "started income-clf-drift (DRIFT_STRENGTH=${DRIFT_STRENGTH:-0}); waiting for http://127.0.0.1:3001/readyz"
# OrbStack routes the Mac to container IPs, so the kind-network address also gets an sslip.io name, like the ML UIs.
# Docker may hand out another address after a restart, so the name is printed each time.
IP=$(docker inspect income-clf-drift -f '{{.NetworkSettings.Networks.kind.IPAddress}}')
for _ in $(seq 1 90); do
  curl -fs -m 2 127.0.0.1:3001/readyz >/dev/null 2>&1 && { echo "ready: http://bentoml.${IP//./-}.sslip.io:3000 (or http://127.0.0.1:3001)"; exit 0; }
  sleep 2
done
echo "not ready; see: docker logs income-clf-drift" >&2; exit 1
