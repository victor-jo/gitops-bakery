#!/usr/bin/env bash
# End-to-end check on a clean Docker: install, idempotent reinstall, MCP app lifecycle, timings, no-sudo GitLab, uninstall.
# WITH_ML=1 installs with --with-ml and also checks the ML names, the seeded online store and the pipeline image.
set -euo pipefail
cd "$(dirname "$0")/../.."
CLI="node dist/cli.js"
MCP="node test/e2e/mcp-client.mjs"
APP=e2e-hello
phase() { echo; echo "=== $1 ($(date +%H:%M:%S))"; }
fail() { echo "E2E FAILED: $1"; exit 1; }

phase "build"
npm run build >/dev/null

phase "install from scratch"
t0=$(date +%s)
$CLI install ${WITH_ML:+--with-ml}
echo "install took $(( $(date +%s) - t0 ))s"
CLUSTER=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.gitops-bakery/state.json')))['clusterName'])")
CTX="kind-$CLUSTER"

phase "every pod is Running or Completed, every Application Synced/Healthy"
bad=$(kubectl --context "$CTX" get pods -A --no-headers | awk '$4 != "Running" && $4 != "Completed"' || true)
[ -z "$bad" ] || fail "pods not ready: $bad"
apps=$(kubectl --context "$CTX" -n argocd get applications -o jsonpath='{range .items[*]}{.metadata.name}={.status.sync.status}/{.status.health.status} {end}')
echo "$apps"
echo "$apps" | tr ' ' '\n' | grep -v '^$' | grep -v 'Synced/Healthy' && fail "applications not healthy" || true

if [ -n "${WITH_ML:-}" ]; then
  phase "ML: every name answers, the online store is seeded, the pipeline image is in Harbor"
  for h in $(python3 -c "import json,os;print(' '.join(json.load(open(os.path.expanduser('~/.gitops-bakery/state.json')))['ml']['hosts'].values()))"); do
    code=$(curl -s -o /dev/null -w '%{http_code}' "http://$h/")
    echo "$h $code"
    case "$code" in 200|302|404) ;; *) fail "$h answered $code" ;; esac
  done
  kubectl --context "$CTX" -n feast logs job/ml-seed-features | grep -q "online store keys in Valkey db 1: 30162" || fail "online store not seeded"
  curl -fsS http://localhost:30001/api/v2.0/projects/kfp/repositories/income-pipeline/artifacts | grep -q '"0.1.0"' || fail "pipeline image missing"
fi

phase "second install skips every step"
out=$($CLI install)
echo "$out" | grep -E '^(✓|…)' | grep -v '(skipped)' && fail "a step ran again" || echo "all steps skipped"

phase "MCP: create an app and wait until it serves"
t0=$(date +%s)
$MCP create "$APP"
$MCP wait "$APP"
echo "create -> serving took $(( $(date +%s) - t0 ))s"

phase "push a change and time both clocks"
PAT=$(python3 -c "import json,os;print(json.load(open(os.path.expanduser('~/.gitops-bakery/secrets.json')))['gitlabPat'])")
SHA=$(curl -fsS -X POST -H "PRIVATE-TOKEN: $PAT" -H 'content-type: application/json' \
  "http://localhost/api/v4/projects/apps%2F$APP/repository/commits" \
  -d '{"branch":"main","commit_message":"E2E change","actions":[{"action":"create","file_path":"E2E.md","content":"e2e\n"}]}' \
  | python3 -c "import sys,json;print(json.load(sys.stdin)['short_id'])")
t0=$(date +%s)
URL=$($MCP app-status "$APP" | python3 -c "import sys,json;print(json.load(sys.stdin)['url'])")
until curl -fsS "$URL" 2>/dev/null | grep -q "\"version\":\"$SHA"; do
  [ $(( $(date +%s) - t0 )) -lt 600 ] || fail "new version never appeared"
  sleep 1
done
t_live=$(date +%s)
TAG_AT=$(curl -fsS -H "PRIVATE-TOKEN: $PAT" "http://localhost/api/v4/projects/apps%2F$APP-manifests/repository/commits?per_page=1" \
  | python3 -c "import sys,json,datetime;print(int(datetime.datetime.fromisoformat(json.load(sys.stdin)[0]['created_at']).timestamp()))")
echo "source commit -> live: $(( t_live - t0 ))s"
echo "tag commit -> live: $(( t_live - TAG_AT ))s"
[ $(( t_live - TAG_AT )) -lt 60 ] || fail "tag commit took 60s or more to go live"

phase "GitLab on http://localhost without sudo"
code=$(curl -s -o /dev/null -w '%{http_code}' http://localhost/users/sign_in)
[ "$code" = "200" ] || fail "GitLab sign-in page returned $code"
echo "sign_in 200"

phase "memory per node"
docker stats --no-stream --format '{{.Name}} {{.MemUsage}}' | grep "$CLUSTER" || true

phase "MCP: delete the app"
$MCP delete "$APP"

phase "uninstall"
$CLI uninstall --yes
kind get clusters 2>/dev/null | grep -qx "$CLUSTER" && fail "cluster still exists"
claude mcp list 2>/dev/null | grep -q '^gitops-bakery:' && fail "MCP entry still registered"
[ ! -e "${CLAUDE_CONFIG_DIR:-$HOME/.claude}/skills/gitops-bakery" ] || fail "skill folder still present"
[ ! -e "$HOME/.gitops-bakery" ] || fail "~/.gitops-bakery still present"
echo
echo "E2E PASSED"
