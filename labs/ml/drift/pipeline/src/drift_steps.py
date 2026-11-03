# Drift check of the income classifier: the champion's training features versus today's Feast features, sent to Evidently
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PANELS = ("Share of drifted columns", "Drifted columns (last run)")


def _minio_client():
    from minio import Minio

    # Garage signs with its own region, so it is passed explicitly instead of the client's us-east-1 default
    return Minio(
        os.environ["S3_ENDPOINT"],
        access_key=os.environ["AWS_ACCESS_KEY_ID"],
        secret_key=os.environ["AWS_SECRET_ACCESS_KEY"],
        secure=False,
        region=os.environ.get("S3_REGION"),
    )


def reference_uri(model_name: str, model_alias: str, reference_context: str) -> str:
    """Follows MLflow lineage from the alias to the dataset the champion's run logged under reference_context."""
    from mlflow import MlflowClient

    client = MlflowClient()
    version = client.get_model_version_by_alias(model_name, model_alias)
    run = client.get_run(version.run_id)
    for item in run.inputs.dataset_inputs:
        if any(t.key == "mlflow.data.context" and t.value == reference_context for t in item.tags):
            return json.loads(item.dataset.source)["uri"]
    raise ValueError(f"run {version.run_id} of {model_name}@{model_alias} logged no dataset with context {reference_context}")


def load_reference(uri: str) -> pd.DataFrame:
    # The notebook records the source as "<bucket>/<key>", without a scheme
    bucket, key = uri.removeprefix("s3://").split("/", 1)
    local = Path("/tmp") / Path(key).name
    _minio_client().fget_object(bucket, key, str(local))
    return pd.read_csv(local)


def ensure_project(ws, name: str):
    from evidently.sdk.models import PanelMetric
    from evidently.sdk.panels import counter_panel, line_plot_panel

    found = ws.search_project(name)
    project = found[0] if found else ws.create_project(name, description="Data drift of the income classifier's input features")
    # Panels are added only when missing, so every run can call this
    existing = {p.title for p in ws.get_dashboard(project.id).panels}
    share = PanelMetric(legend="share", metric="DriftedColumnsCount", metric_labels={"value_type": "share"})
    count = PanelMetric(legend="columns", metric="DriftedColumnsCount", metric_labels={"value_type": "count"})
    if PANELS[0] not in existing:
        project.dashboard.add_panel(line_plot_panel(title=PANELS[0], values=[share]))
    if PANELS[1] not in existing:
        project.dashboard.add_panel(counter_panel(title=PANELS[1], values=[count], aggregation="last", size="half"))
    return project


def detect_drift(features_path: str, model_name: str, model_alias: str, reference_context: str,
                 evidently_url: str, project_name: str) -> float:
    from evidently import DataDefinition, Dataset, Report
    from evidently.presets import DataDriftPreset
    from evidently.ui.workspace import RemoteWorkspace

    uri = reference_uri(model_name, model_alias, reference_context)
    reference = load_reference(uri)
    current = pd.read_parquet(features_path).drop(columns=["user_id", "event_timestamp"], errors="ignore")
    # Only the columns Feast serves are compared; every one of them is categorical in this dataset
    columns = [c for c in current.columns if c in reference.columns]
    definition = DataDefinition(categorical_columns=columns)
    snapshot = Report([DataDriftPreset()]).run(
        Dataset.from_pandas(current[columns], data_definition=definition),
        Dataset.from_pandas(reference[columns], data_definition=definition),
        # Evidently stores a naive time; UTC keeps Mac runs and pod runs in order on the same graph
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        tags=[model_alias],
        metadata={"model": model_name, "reference": uri},
    )

    ws = RemoteWorkspace(evidently_url)
    project = ensure_project(ws, project_name)
    ws.add_run(project.id, snapshot, include_data=False)

    drifted = next(m["value"] for m in snapshot.dict()["metrics"] if m["metric_name"].startswith("DriftedColumnsCount"))
    print(f"reference {uri}: {len(reference)} rows; current: {len(current)} rows; columns: {len(columns)}")
    print(f"drifted columns: {int(drifted['count'])} of {len(columns)} (share {drifted['share']:.2f}); project {project.id}")
    return float(drifted["share"])
