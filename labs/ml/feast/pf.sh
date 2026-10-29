#!/usr/bin/env bash
# Opens tunnels to Garage (S3) and Valkey for Mac-side Feast and AWS CLI work; both stay ClusterIP, so this is the one place a tunnel is needed
set -euo pipefail
source "$(dirname "$0")/../env.sh"
up() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
# 16379 keeps clear of a local Redis on 6379 and of the 30010-30019 app range
up 3900 || nohup kubectl --context "$BAKERY_CONTEXT" -n gitlab port-forward svc/garage 3900:3900 >/dev/null 2>&1 &
up 16379 || nohup kubectl --context "$BAKERY_CONTEXT" -n gitlab port-forward svc/valkey 16379:6379 >/dev/null 2>&1 &
sleep 2
for p in 3900 16379; do up $p && echo "port $p ready" || echo "port $p NOT listening"; done
