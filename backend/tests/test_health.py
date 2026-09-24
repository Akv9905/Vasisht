"""Health endpoint tests."""

from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_ok():
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["paid_apis_required"] is False
    assert body["llm_enabled"] is False


def test_root():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["mode"] == "local/free"
