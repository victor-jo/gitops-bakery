# Minimal two-step pipeline to prove KFP can schedule, run and pass data between steps on this cluster
import os
from kfp import dsl, compiler, Client


@dsl.component(base_image="python:3.12-slim")
def add(a: int, b: int) -> int:
    return a + b


@dsl.component(base_image="python:3.12-slim")
def report(total: int) -> str:
    message = f"total is {total}"
    print(message)
    return message


@dsl.pipeline(name="smoke-hello")
def smoke(a: int = 2, b: int = 3):
    report(total=add(a=a, b=b).output)


if __name__ == "__main__":
    compiler.Compiler().compile(smoke, "smoke/hello_pipeline.yaml")
    client = Client(host=os.environ["KFP_URL"])
    run = client.create_run_from_pipeline_package("smoke/hello_pipeline.yaml", arguments={"a": 2, "b": 3}, run_name="smoke-hello")
    print("run id:", run.run_id)
    result = client.wait_for_run_completion(run.run_id, timeout=900)
    print("state:", result.state)
