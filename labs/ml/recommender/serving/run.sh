#!/usr/bin/env bash
# Starts the latest movie-recommender image on 0.0.0.0:3100 for the phone, after bringing up the supervised Garage and Valkey tunnels
set -euo pipefail
cd "$(dirname "$0")/.."
source ../env.sh
# Without the tunnels the service never finishes starting; tunnels.sh starts them (or finds them running) and fails fast
bash serving/tunnels.sh
key() { kubectl --context "$BAKERY_CONTEXT" -n kubeflow get secret kfp-s3 -o jsonpath="{.data.$1}" | base64 -d; }
TAG=$(sed 's/^__tag__://' serving/.bento-tag)
docker rm -f movie-rec >/dev/null 2>&1 || true
# The kind network reaches the gateways behind the sslip.io names; the tunnels are on the Mac, i.e. host.docker.internal.
# Credentials are passed at run time, never baked into the image. MLflow artifacts come through the server, because
# the presigned Garage URLs it would hand out do not resolve outside the cluster.
# 0.0.0.0 publishes the port on the Mac's LAN address too, so a phone on the home Wi-Fi can open it.
docker run -d --name movie-rec --network kind -p 0.0.0.0:3100:3000 \
  --add-host host.docker.internal:host-gateway \
  -e AWS_ACCESS_KEY_ID="$(key AWS_ACCESS_KEY_ID)" -e AWS_SECRET_ACCESS_KEY="$(key AWS_SECRET_ACCESS_KEY)" \
  -e S3_ENDPOINT=host.docker.internal:3900 -e S3_REGION=garage -e AWS_DEFAULT_REGION=garage \
  -e FEAST_S3_ENDPOINT_URL=http://host.docker.internal:3900 -e VALKEY_ADDRESS=host.docker.internal:16379 \
  -e MLFLOW_TRACKING_URI="$MLFLOW_URL" -e MLFLOW_DISABLE_AGENT_HINT=1 -e MLFLOW_ENABLE_PROXY_MULTIPART_DOWNLOAD=false \
  -e EVIDENTLY_URL="$EVIDENTLY_URL" \
  "movie-recommender:${TAG#*:}" >/dev/null
echo "started movie-rec; waiting for http://127.0.0.1:3100/readyz"
# 127.0.0.1, not localhost: OrbStack also listens on ::1 for the mapped port but never answers there
for _ in $(seq 1 120); do
  if curl -fs -m 2 127.0.0.1:3100/readyz >/dev/null 2>&1; then
    IP=$(ipconfig getifaddr en0 || true)
    if [ -n "$IP" ]; then
      echo "ready: http://$IP:3100 (open on the phone, same Wi-Fi)"
    else
      echo "ready: http://127.0.0.1:3100 (en0 has no address, so there is no LAN URL for the phone; join the Wi-Fi and run: ipconfig getifaddr en0)"
    fi
    exit 0
  fi
  if [ "$(docker inspect -f '{{.State.Running}}' movie-rec 2>/dev/null)" != "true" ]; then
    echo "movie-rec stopped while starting; last log lines:" >&2; docker logs --tail 20 movie-rec >&2 2>&1; exit 1
  fi
  sleep 2
done
echo "not ready; see: docker logs movie-rec" >&2; exit 1
