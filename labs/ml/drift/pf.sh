#!/usr/bin/env bash
# Opens the book's Evidently address, localhost:8000, as a tunnel; the sslip.io name in $EVIDENTLY_URL works without it
set -euo pipefail
source "$(dirname "$0")/../env.sh"
up() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }
up 8000 || nohup kubectl --context "$BAKERY_CONTEXT" -n evidently port-forward svc/evidently-service-internal 8000:8000 >/dev/null 2>&1 &
sleep 2
up 8000 && echo "port 8000 ready: export EVIDENTLY_URL=http://localhost:8000" || echo "port 8000 NOT listening"
