# BentoML service: scores a user's income band from Feast online features and reports input drift to Evidently
import os
import sys
from pathlib import Path

import bentoml
import pandas as pd

# The batch drift step's helpers (MLflow lineage, Garage, Evidently project) are reused as they are
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "drift" / "pipeline" / "src"))

FEATURES = [
    "demographic:Sex", "demographic:Race", "demographic:Native_country",
    "relationship:Relationship", "relationship:Marital-Status",
    "occupation:Workclass", "occupation:Education", "occupation:Occupation",
]
LABELS = {0: "<=50K", 1: ">50K"}


def feature_store():
    """Loads the Mac-side Feast config and points its Valkey address at the tunnel the container can reach."""
    from drift_steps import _minio_client
    from feast import FeatureStore

    repo = Path("/tmp/feature_repo")
    repo.mkdir(parents=True, exist_ok=True)
    config = repo / "feature_store.yaml"
    _minio_client().fget_object("feature-registry", "feature_store_local.yaml", str(config))
    # The config was written for the Mac (localhost:16379); inside Docker the tunnel is on host.docker.internal
    config.write_text(config.read_text().replace("localhost:16379", os.environ.get("VALKEY_ADDRESS", "localhost:16379")))
    return FeatureStore(repo_path=str(repo))


# One worker keeps one window; with several, each would hold its own partial window, as the book warns
@bentoml.service(name="income_classifier_service", workers=1)
class IncomeClassifier:
    model_ref = bentoml.models.BentoModel("income-classifier:latest")

    def __init__(self) -> None:
        from drift_steps import ensure_project, load_reference, reference_uri_for_run
        from evidently.ui.workspace import RemoteWorkspace
        from serving.monitoring import SCORE_TITLE, DriftWindow

        info = bentoml.models.get(self.model_ref.tag)
        self.model = bentoml.mlflow.load_model(info)
        self.columns = info.custom_objects["column_list"]
        self.store = feature_store()
        feature_columns = [f.split(":")[1] for f in FEATURES]
        # The reference is the training data of the model baked into this image, not of whatever is champion now
        reference = load_reference(reference_uri_for_run(info.info.metadata["run_id"], "reference_features"))
        workspace = RemoteWorkspace(os.environ["EVIDENTLY_URL"])
        project = ensure_project(workspace, os.environ.get("EVIDENTLY_PROJECT", "income-classifier-realtime"), feature_columns,
                                 score_title=SCORE_TITLE)
        self.window = DriftWindow(reference, feature_columns, workspace, project,
                                  window_size=int(os.environ.get("DRIFT_WINDOW_SIZE", "100")),
                                  drift_strength=float(os.environ.get("DRIFT_STRENGTH", "0")),
                                  model_tag=str(info.tag))

    @bentoml.api(route="/predict")
    def predict(self, user_id: str) -> dict:
        features = self.store.get_online_features(features=FEATURES, entity_rows=[{"user_id": user_id}]).to_df()
        features = features.drop(columns=["user_id"])
        self.window.add(features)
        # One row holds one category per column, so drop_first=True (the book's InputMapper) would drop all of them
        # and score every user as all zeros. Encoding every category and then keeping the training columns gives the
        # training encoding, because the categories training dropped are simply not among those columns.
        encoded = pd.get_dummies(features, sparse=False, dtype=float).reindex(columns=self.columns, fill_value=0)
        return {"income_category": LABELS.get(int(self.model.predict(encoded)[0])), "user_id": user_id}
