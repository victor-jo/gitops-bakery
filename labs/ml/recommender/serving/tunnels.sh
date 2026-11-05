#!/usr/bin/env bash
# Keeps the Garage (3900) and Valkey (16379) tunnels for movie-rec up, restarting each port-forward when it dies
set -euo pipefail
source "$(dirname "$0")/../../env.sh"
up() { lsof -nP -iTCP:"$1" -sTCP:LISTEN >/dev/null 2>&1; }

# port service target: a supervised loop per port, logged to /tmp, its pid kept so a rerun does not start a second one
tunnel() {
  local port=$1 svc=$2 target=$3 pidfile=/tmp/movie-rec-tunnel-$1.pid log=/tmp/movie-rec-tunnel-$1.log
  if [ -f "$pidfile" ] && kill -0 "$(cat "$pidfile")" 2>/dev/null; then
    echo "port $port: supervisor $(cat "$pidfile") already running"; return
  fi
  if up "$port"; then
    echo "port $port: already listening (not supervised here)"; return
  fi
  nohup bash -c 'while true; do kubectl --context "$1" -n gitlab port-forward "svc/$2" "$3"; sleep 2; done' \
    _ "$BAKERY_CONTEXT" "$svc" "$port:$target" >>"$log" 2>&1 &
  echo $! >"$pidfile"
  echo "port $port: started supervisor $! (log $log)"
}

tunnel 3900 garage 3900
# 16379 keeps clear of a local Redis on 6379 and of the 30010-30019 app range
tunnel 16379 valkey 6379

for p in 3900 16379; do
  for _ in $(seq 1 15); do up "$p" && break; sleep 1; done
  up "$p" || { echo "port $p NOT listening; see /tmp/movie-rec-tunnel-$p.log" >&2; exit 1; }
done
echo "tunnels ready (stop: for f in /tmp/movie-rec-tunnel-*.pid; do pkill -P \$(cat \$f); kill \$(cat \$f); done)"
