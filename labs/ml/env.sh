# Source before the ML lab scripts: kube context, sslip.io URLs and the pipeline image names, read from the bakery's state.json
_bakery_state="${GITOPS_BAKERY_HOME:-$HOME/.gitops-bakery}/state.json"
eval "$(python3 - "$_bakery_state" <<'PY'
import json, sys
s = json.load(open(sys.argv[1]))
hosts = (s.get("ml") or {}).get("hosts")
if not hosts:
    sys.exit("echo 'ML hosts are missing; run: npx github:victor-jo/gitops-bakery install --with-ml' >&2; return 1")
name = s["clusterName"]
print(f"export BAKERY_CONTEXT=kind-{name}")
# evidently is absent on a lab installed before it, until install --force
for key in ("mlflow", "jupyter", "feast", "kfp", "evidently"):
    if key in hosts:
        print(f"export {key.upper()}_URL=http://{hosts[key]}")
print(f"export KFP_IMAGE={name}-control-plane:30001/kfp/income-pipeline:0.1.0")
print(f"export DRIFT_IMAGE={name}-control-plane:30001/kfp/drift-pipeline:0.1.0")
PY
)"
unset _bakery_state
