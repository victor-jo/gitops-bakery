# Shared KFP task wiring of the recommender pipelines: Garage credentials from a Secret, lab env, no cache
from kfp import kubernetes

GARAGE = "garage.gitlab.svc.cluster.local:3900"
ENV = {
    "S3_ENDPOINT": GARAGE,
    "S3_REGION": "garage",
    "AWS_DEFAULT_REGION": "garage",
    "AWS_ENDPOINT_URL": f"http://{GARAGE}",
    "MLFLOW_TRACKING_URI": "http://mlflow.mlflow.svc.cluster.local",
}


def wire(task, cpu: str | None = None, memory: str | None = None):
    # Credentials come from a Kubernetes Secret instead of pipeline parameters, so they never appear in the KFP UI
    kubernetes.use_secret_as_env(task, secret_name="kfp-s3", secret_key_to_env={
        "AWS_ACCESS_KEY_ID": "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY": "AWS_SECRET_ACCESS_KEY"})
    for name, value in ENV.items():
        task.set_env_variable(name, value)
    # The lab rebuilds its images under the same tag, so nodes must not run a cached copy
    kubernetes.set_image_pull_policy(task, "Always")
    # Every run must see today's catalog and feedback; KFP would otherwise replay an earlier result
    task.set_caching_options(False)
    if cpu:
        task.set_cpu_request(cpu).set_cpu_limit(cpu)
    if memory:
        task.set_memory_request(memory).set_memory_limit(memory)
    return task
