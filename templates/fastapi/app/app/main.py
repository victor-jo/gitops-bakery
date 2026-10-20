# FastAPI service created by gitops-bakery: one JSON endpoint, a health check and Prometheus metrics
import os

from fastapi import FastAPI
from prometheus_fastapi_instrumentator import Instrumentator

APP_NAME = "{{name}}"
VERSION = os.getenv("APP_VERSION", "dev")

app = FastAPI(title=APP_NAME, version=VERSION)
# Probes and scrapes are not visitors, so keep them out of the request count
Instrumentator(excluded_handlers=["/healthz", "/metrics"]).instrument(app).expose(app, include_in_schema=False)


@app.get("/")
def root() -> dict[str, str]:
    return {"app": APP_NAME, "version": VERSION}


@app.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}
