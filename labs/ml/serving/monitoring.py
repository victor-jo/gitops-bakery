# Sliding window of served feature rows that sends an Evidently drift report every window_size requests
import logging
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger("bentoml")

# 100 rows against 30,162: Jensen-Shannon distance exceeds 0.1 by chance on columns with many values (41 countries),
# so the window uses the chi-square test, which Evidently itself picks for samples of up to 1,000 rows
CAT_METHOD = "chisquare"
SCORE_TITLE = "Drift p-value per column (chi-square; below 0.05 is drift)"


class DriftWindow:
    """Keeps the last window_size rows and reports once per window_size new rows.

    The book's MonitoringService reports on every request once the window is full, which runs the whole
    report for each call; reporting once per window keeps the same window with one report per batch of traffic.
    """

    def __init__(self, reference: pd.DataFrame, columns: list, workspace, project, window_size: int = 100,
                 drift_strength: float = 0.0, model_tag: str = ""):
        self.reference = reference[columns]
        self.columns = columns
        self.workspace = workspace
        self.project = project
        self.window_size = window_size
        self.drift_strength = drift_strength
        self.model_tag = model_tag
        self.current = pd.DataFrame(columns=columns)
        self.since_report = 0

    def add(self, rows: pd.DataFrame) -> bool:
        self.current = pd.concat([self.current, rows[self.columns]], ignore_index=True).tail(self.window_size)
        self.since_report += len(rows)
        if len(self.current) < self.window_size:
            log.info("drift window %d of %d rows; waiting for more", len(self.current), self.window_size)
            return False
        if self.since_report < self.window_size:
            return False
        self.since_report = 0
        self._report()
        return True

    def _report(self) -> None:
        from drift_steps import DRIFT_SHARE, simulate_drift
        from evidently import DataDefinition, Dataset, Report
        from evidently.metrics import DatasetMissingValueCount
        from evidently.presets import DataDriftPreset

        current = simulate_drift(self.current, self.columns, self.drift_strength)
        definition = DataDefinition(categorical_columns=self.columns)
        snapshot = Report([DataDriftPreset(drift_share=DRIFT_SHARE, cat_method=CAT_METHOD), DatasetMissingValueCount()]).run(
            Dataset.from_pandas(current, data_definition=definition),
            Dataset.from_pandas(self.reference, data_definition=definition),
            timestamp=datetime.now(timezone.utc).replace(tzinfo=None),
            tags=["realtime", f"drift-strength-{self.drift_strength:g}"],
            metadata={"model": self.model_tag, "window_size": str(self.window_size)},
        )
        self.workspace.add_run(self.project.id, snapshot, include_data=False)
        drifted = next(m["value"] for m in snapshot.dict()["metrics"] if m["metric_name"].startswith("DriftedColumnsCount"))
        log.info("drift report: %d of %d columns drifted over the last %d requests",
                 int(drifted["count"]), len(self.columns), self.window_size)
