# Two-step pipeline that passes a file artifact, to prove the launcher reads and writes artifacts in Garage
import os
from kfp import dsl, compiler, Client
from kfp.dsl import Dataset, Input, Output


@dsl.component(base_image="python:3.12-slim")
def write_rows(rows: int, data: Output[Dataset]):
    with open(data.path, "w") as f:
        for i in range(rows):
            f.write(f"{i}\n")


@dsl.component(base_image="python:3.12-slim")
def count_rows(data: Input[Dataset]) -> int:
    with open(data.path) as f:
        n = sum(1 for _ in f)
    print(f"rows read back: {n} from {data.uri}")
    return n


@dsl.pipeline(name="smoke-artifact")
def smoke(rows: int = 7):
    count_rows(data=write_rows(rows=rows).outputs["data"])


if __name__ == "__main__":
    compiler.Compiler().compile(smoke, "smoke/artifact_pipeline.yaml")
    client = Client(host=os.environ["KFP_URL"])
    run = client.create_run_from_pipeline_package("smoke/artifact_pipeline.yaml", arguments={"rows": 7}, run_name="smoke-artifact")
    print("run id:", run.run_id)
    print("state:", client.wait_for_run_completion(run.run_id, timeout=900).state)
