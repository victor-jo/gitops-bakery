# Drift check of the income classifier: the champion's training features versus today's Feast features, sent to Evidently
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PANELS = ("Share of drifted columns", "Drift score per column (Jensen-Shannon)", "Drifted columns (last run)",
          "Missing values")
# Evidently calls it dataset drift when at least this share of columns drifted (DataDriftPreset's default)
DRIFT_SHARE = 0.5


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


def reference_uri_for_run(run_id: str, reference_context: str) -> str:
    """Returns the source of the dataset a training run logged under reference_context."""
    from mlflow import MlflowClient

    run = MlflowClient().get_run(run_id)
    for item in run.inputs.dataset_inputs:
        if any(t.key == "mlflow.data.context" and t.value == reference_context for t in item.tags):
            return json.loads(item.dataset.source)["uri"]
    raise ValueError(f"run {run_id} logged no dataset with context {reference_context}")


def reference_uri(model_name: str, model_alias: str, reference_context: str) -> str:
    """Follows MLflow lineage from the alias to the dataset the champion's run logged under reference_context."""
    from mlflow import MlflowClient

    version = MlflowClient().get_model_version_by_alias(model_name, model_alias)
    return reference_uri_for_run(version.run_id, reference_context)


def load_reference(uri: str) -> pd.DataFrame:
    # The notebook records the source as "<bucket>/<key>", without a scheme
    bucket, key = uri.removeprefix("s3://").split("/", 1)
    local = Path("/tmp") / Path(key).name
    _minio_client().fget_object(bucket, key, str(local))
    return pd.read_csv(local)


def ensure_project(ws, name: str, columns: list, score_title: str = "Drift score per column (Jensen-Shannon)"):
    from evidently.sdk.models import PanelMetric
    from evidently.sdk.panels import bar_plot_panel, counter_panel, line_plot_panel

    found = ws.search_project(name)
    project = found[0] if found else ws.create_project(name, description="Data drift of the income classifier's input features")
    # Panels are added only when missing, so every run can call this
    existing = {p.title for p in ws.get_dashboard(project.id).panels}
    share = PanelMetric(legend="share", metric="DriftedColumnsCount", metric_labels={"value_type": "share"})
    count = PanelMetric(legend="columns", metric="DriftedColumnsCount", metric_labels={"value_type": "count"})
    missing = PanelMetric(legend="missing cells", metric="DatasetMissingValueCount", metric_labels={"value_type": "count"})
    if PANELS[0] not in existing:
        project.dashboard.add_panel(line_plot_panel(title=PANELS[0], values=[share]))
    if score_title not in existing:
        # The share above only counts columns past the 0.1 threshold; the raw scores show drift growing before that
        scores = [PanelMetric(legend=c, metric="ValueDrift", metric_labels={"column": c}) for c in columns]
        project.dashboard.add_panel(line_plot_panel(title=score_title, values=scores))
    if PANELS[2] not in existing:
        project.dashboard.add_panel(counter_panel(title=PANELS[2], values=[count], aggregation="last", size="half"))
    if PANELS[3] not in existing:
        # Data quality next to drift, like the book's missing-data panel
        project.dashboard.add_panel(bar_plot_panel(title=PANELS[3], values=[missing], size="half"))
    return project


def simulate_drift(df: pd.DataFrame, columns: list, strength: float, seed: int = 0) -> pd.DataFrame:
    """Moves part of each column to its second most common value, so a lab can watch drift appear.

    Feast serves the same users the model was trained on, so without this every score is exactly 0.
    Column k is moved for a share strength * 2 * (k + 1) / len(columns) of rows, so columns tip over
    one after another: on the Feast features 0.05 drifts none of 8 columns, 0.1 drifts 4, 0.3 drifts 7.
    """
    import numpy as np

    if strength <= 0:
        return df
    rng = np.random.default_rng(seed)
    out = df.copy()
    for k, column in enumerate(columns):
        share = min(1.0, strength * 2 * (k + 1) / len(columns))
        out.loc[rng.random(len(out)) < share, column] = out[column].value_counts().index[1]
    return out


def detect_drift(features_path: str, model_name: str, model_alias: str, reference_context: str,
                 evidently_url: str, project_name: str, drift_strength: float = 0.0, fail_on_drift: bool = True) -> float:
    from evidently import DataDefinition, Dataset, Report
    from evidently.metrics import DatasetMissingValueCount
    from evidently.presets import DataDriftPreset
    from evidently.ui.workspace import RemoteWorkspace

    uri = reference_uri(model_name, model_alias, reference_context)
    reference = load_reference(uri)
    current = pd.read_parquet(features_path).drop(columns=["user_id", "event_timestamp"], errors="ignore")
    # Only the columns Feast serves are compared; every one of them is categorical in this dataset
    columns = [c for c in current.columns if c in reference.columns]
    current = simulate_drift(current, columns, drift_strength)
    definition = DataDefinition(categorical_columns=columns)
    snapshot = Report([DataDriftPreset(drift_share=DRIFT_SHARE), DatasetMissingValueCount()]).run(
        Dataset.from_pandas(current[columns], data_definition=definition),
        Dataset.from_pandas(reference[columns], data_definition=definition),
        # Evidently stores a naive time; UTC keeps Mac runs and pod runs in order on the same graph
        timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
        tags=[model_alias, f"drift-strength-{drift_strength:g}"],
        metadata={"model": model_name, "reference": uri, "drift_strength": f"{drift_strength:g}"},
    )

    ws = RemoteWorkspace(evidently_url)
    project = ensure_project(ws, project_name, columns)
    ws.add_run(project.id, snapshot, include_data=False)

    drifted = next(m["value"] for m in snapshot.dict()["metrics"] if m["metric_name"].startswith("DriftedColumnsCount"))
    print(f"reference {uri}: {len(reference)} rows; current: {len(current)} rows; columns: {len(columns)}; drift_strength {drift_strength:g}")
    print(f"drifted columns: {int(drifted['count'])} of {len(columns)} (share {drifted['share']:.2f}); project {project.id}")
    # The book says the pipeline stops on drift, but its listing never does; the report is saved first so the
    # dashboard still shows the run that tripped the gate
    if fail_on_drift and drifted["share"] >= DRIFT_SHARE:
        raise RuntimeError(f"dataset drift: {drifted['share']:.2f} of columns drifted (threshold {DRIFT_SHARE}); stopping")
    return float(drifted["share"])
