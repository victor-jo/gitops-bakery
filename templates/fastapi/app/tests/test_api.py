# API tests for the generated service
from fastapi.testclient import TestClient

from app.main import APP_NAME, app

client = TestClient(app)


def test_root_returns_name_and_version():
    assert client.get("/").json() == {"app": APP_NAME, "version": "dev"}


def test_healthz():
    assert client.get("/healthz").json() == {"status": "ok"}


def test_metrics_excludes_probe_and_scrape():
    client.get("/")
    client.get("/healthz")
    res = client.get("/metrics")
    assert res.status_code == 200
    assert 'handler="/"' in res.text
    assert 'handler="/healthz"' not in res.text
    assert 'handler="/metrics"' not in res.text
