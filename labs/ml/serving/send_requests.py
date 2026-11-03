# Sends N prediction requests to the BentoML service, one per user from the scoring input in Garage
import json
import os
import sys
import urllib.request
from collections import Counter

import boto3
import pandas as pd

n = int(sys.argv[1]) if len(sys.argv) > 1 else 100
# 127.0.0.1, not localhost: OrbStack also listens on ::1 for the mapped port but never answers there
url = os.environ.get("SERVICE_URL", "http://127.0.0.1:3001")
local = "/tmp/entity_df.parquet"
boto3.client("s3", endpoint_url="http://localhost:3900", region_name="garage").download_file(
    "inference-datasets", "entity_df.parquet", local)
users = pd.read_parquet(local)["user_id"].sample(n, random_state=int(os.environ.get("SEED", "0"))).tolist()
answers = Counter()
for user in users:
    req = urllib.request.Request(f"{url}/predict", json.dumps({"user_id": user}).encode(), {"Content-Type": "application/json"})
    answers[json.load(urllib.request.urlopen(req))["income_category"]] += 1
print(f"{n} requests: {dict(answers)}")
