# Rewrites the upstream MLflow training notebook for this lab: settings from the environment, Garage region, skops types, a registered "best" model
import json
import sys

# Each entry swaps one exact line of a code cell; a missing line means the upstream notebook moved, so the script stops
LINE_SWAPS = [
    (
        "# Set environment variables for mlflow to access the artifact store",
        "# Artifacts go through the MLflow server; dataset uploads use Garage credentials from the environment",
    ),
    ('os.environ["AWS_ACCESS_KEY_ID"] = "minio"', None),
    ('os.environ["AWS_SECRET_ACCESS_KEY"] = "minio123"', None),
    ('os.environ["AWS_ENDPOINT_URL"] = "http://localhost:9000"', None),
    ('mlflow.set_tracking_uri("http://localhost:5000")', 'mlflow.set_tracking_uri(os.environ["MLFLOW_TRACKING_URI"])'),
    (
        'minioClient = Minio("localhost:9000", access_key="minio", secret_key="minio123", secure=False)',
        'minioClient = Minio(os.environ["GARAGE_ENDPOINT"], access_key=os.environ["GARAGE_ACCESS_KEY"], '
        'secret_key=os.environ["GARAGE_SECRET_KEY"], secure=False, region="garage")',
    ),
    ('    print("PLEASE CREATE BUCKET IN MINIO BEFORE PROCEEDING")', '    print("PLEASE CREATE BUCKET IN GARAGE BEFORE PROCEEDING")'),
    (
        '    mlflow.sklearn.log_model(tree,"income-classifier")    #G',
        '    mlflow.sklearn.log_model(tree,"income-classifier", skops_trusted_types=["sklearn.tree._tree.Tree"])    #G',
    ),
    (
        '    mlflow.sklearn.log_model(forest,"income-classifier")',
        '    mlflow.sklearn.log_model(forest,"income-classifier", skops_trusted_types=["sklearn.tree._tree.Tree"])',
    ),
]

# The upstream cell registers the single top run; this lab skips XGBoost runs and tags the model family it picked
REGISTER_MARKER = "run_object = mlflow_client.search_runs("
REGISTER_CELL_TAIL = '''
def model_family(params):
    # Each model type logs a different set of params, so the params tell us which model a run trained
    if "n_estimators" in params and "criterion" in params:
        return "random-forest"
    if "learning_rate" in params:
        return "xgboost"
    return "decision-tree"

# XGBoost is left out: its AUC is computed from hard 0/1 predictions (binary:hinge), so it is not comparable,
# and autolog stores its model under a different artifact path than the sklearn runs
candidates = [
    r for r in mlflow_client.search_runs(
        experiment_ids=[experiment.experiment_id],
        filter_string="metrics.roc_auc_score_test > 0.8",
        order_by=["metrics.roc_auc_score_test DESC"],
    )
    if model_family(r.data.params) != "xgboost"
]
for r in candidates:
    print(f"{r.info.run_name:25} {model_family(r.data.params):15} auc_test={r.data.metrics['roc_auc_score_test']:.4f}")

best_run = candidates[0]
best_family = model_family(best_run.data.params)
model_uri = f"runs:/{best_run.info.run_id}/{experiment_name}"
version = mlflow.register_model(model_uri, f"{experiment_name}-best")
mlflow_client.set_model_version_tag(version.name, version.version, "model_family", best_family)
print(f"Registered {version.name} v{version.version}: {best_family} from run {best_run.info.run_id}")'''


def patch(nb: dict) -> dict:
    pending = {old for old, _ in LINE_SWAPS} | {REGISTER_MARKER}
    for cell in nb["cells"]:
        if cell["cell_type"] != "code":
            continue
        out = []
        for line in "".join(cell["source"]).split("\n"):
            if line.startswith(REGISTER_MARKER):
                # The marker and the two lines after it end the upstream cell, so the lab version replaces all three
                out.append(REGISTER_CELL_TAIL)
                pending.discard(REGISTER_MARKER)
                break
            swaps = [new for old, new in LINE_SWAPS if line == old]
            if not swaps:
                out.append(line)
                continue
            pending.discard(line)
            if swaps[0] is not None:
                out.append(swaps[0])
        text = "\n".join(out)
        cell["source"] = text.splitlines(keepends=True)
    if pending:
        sys.exit(f"upstream notebook changed; lines not found: {sorted(pending)}")
    return nb


if __name__ == "__main__":
    src, dst = sys.argv[1], sys.argv[2]
    with open(src) as f:
        nb = json.load(f)
    with open(dst, "w") as f:
        json.dump(patch(nb), f, indent=1)
