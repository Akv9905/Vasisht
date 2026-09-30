"""Comprehensive FastAPI integration tests covering all P17 endpoints.

Verifies:
- GET  /health
- GET  /
- POST /projects
- GET  /projects
- GET  /projects/{id}
- POST /projects/{id}/repositories
- POST /projects/{id}/analyze
- GET  /projects/{id}/files
- GET  /projects/{id}/classes
- GET  /projects/{id}/methods
- GET  /projects/{id}/architecture
- GET  /projects/{id}/graph
- POST /projects/{id}/questions
- POST /projects/{id}/impact
- GET  /projects/{id}/risks
- GET  /projects/{id}/modernization
- POST /projects/{id}/reports
- GET  /projects/{id}/analysis-runs
- Ownership and access validation (404 on nonexistent projects)
- Pydantic schema validation
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_db
from app.main import app
from app.models import Base

SAMPLE_ROOT = Path(__file__).resolve().parent.parent.parent / "sample-projects" / "payment-service"


@pytest.fixture
def api_client():
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = TestingSessionLocal()

    def override_get_db():
        yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()
    session.close()
    engine.dispose()


class TestFastAPIIntegration:
    def test_health_and_root(self, api_client):
        h = api_client.get("/health")
        assert h.status_code == 200
        assert h.json()["status"] == "ok"

        r = api_client.get("/")
        assert r.status_code == 200
        assert r.json()["mode"] == "local/free"

    def test_full_project_lifecycle(self, api_client):
        # 1. POST /projects
        p_res = api_client.post("/projects", json={"name": "PaymentApp", "description": "Payment microservice"})
        assert p_res.status_code == 201
        p_data = p_res.json()
        assert p_data["id"] == 1
        assert p_data["name"] == "PaymentApp"

        # 2. GET /projects
        list_res = api_client.get("/projects")
        assert list_res.status_code == 200
        assert len(list_res.json()) == 1

        # 3. GET /projects/{id}
        get_res = api_client.get("/projects/1")
        assert get_res.status_code == 200
        assert get_res.json()["name"] == "PaymentApp"

        # 4. POST /projects/{id}/repositories
        repo_res = api_client.post(
            "/projects/1/repositories",
            json={"source": str(SAMPLE_ROOT)},
        )
        assert repo_res.status_code == 201
        repo_data = repo_res.json()
        assert repo_data["project_id"] == 1
        assert repo_data["from_zip"] is False

        # 5. POST /projects/{id}/analyze
        an_res = api_client.post("/projects/1/analyze")
        assert an_res.status_code == 200
        an_data = an_res.json()
        assert an_data["status"] == "completed"
        assert an_data["java_file_count"] >= 5
        assert an_data["graph_node_count"] >= 10
        assert an_data["graph_edge_count"] >= 10

        # 6. GET /projects/{id}/files
        files_res = api_client.get("/projects/1/files")
        assert files_res.status_code == 200
        files = files_res.json()
        assert len(files) >= 5
        assert any("PaymentService.java" in f["relative_path"] for f in files)

        # 7. GET /projects/{id}/classes
        classes_res = api_client.get("/projects/1/classes")
        assert classes_res.status_code == 200
        classes = classes_res.json()
        assert len(classes) >= 3
        cls_names = {c["name"] for c in classes}
        assert "PaymentService" in cls_names
        assert "PaymentController" in cls_names

        # 8. GET /projects/{id}/methods
        methods_res = api_client.get("/projects/1/methods")
        assert methods_res.status_code == 200
        methods = methods_res.json()
        assert len(methods) >= 5
        m_names = {m["name"] for m in methods}
        assert "processPayment" in m_names or "create" in m_names

        # 9. GET /projects/{id}/analysis-runs
        runs_res = api_client.get("/projects/1/analysis-runs")
        assert runs_res.status_code == 200
        runs = runs_res.json()
        assert len(runs) >= 1
        assert runs[0]["status"] == "completed"

        # 10. GET /projects/{id}/architecture
        arch_res = api_client.get("/projects/1/architecture")
        assert arch_res.status_code == 200
        arch = arch_res.json()
        assert len(arch["controllers"]) >= 2
        assert len(arch["services"]) >= 2
        assert len(arch["repositories"]) >= 1

        # 11. GET /projects/{id}/graph
        graph_res = api_client.get("/projects/1/graph")
        assert graph_res.status_code == 200
        g_data = graph_res.json()
        assert g_data["total_nodes"] > 0
        assert g_data["total_edges"] > 0

        # 12. POST /projects/{id}/questions
        qa_res = api_client.post(
            "/projects/1/questions",
            json={"question": "How does /api/payment reach the database?"},
        )
        assert qa_res.status_code == 200
        qa_data = qa_res.json()
        assert "answer" in qa_data
        assert len(qa_data["evidence"]) >= 1

        # 13. POST /projects/{id}/impact
        imp_res = api_client.post(
            "/projects/1/impact",
            json={"target": "PaymentService.processPayment"},
        )
        assert imp_res.status_code == 200
        imp_data = imp_res.json()
        assert imp_data["target"] == "processPayment"
        assert len(imp_data["direct_impact"]) > 0

        # 14. GET /projects/{id}/risks
        risks_res = api_client.get("/projects/1/risks")
        assert risks_res.status_code == 200
        risks_data = risks_res.json()
        assert risks_data["total_findings"] >= 1

        # 15. GET /projects/{id}/modernization
        mod_res = api_client.get("/projects/1/modernization")
        assert mod_res.status_code == 200
        mod_data = mod_res.json()
        assert mod_data["total_findings"] >= 1

        # 16. POST /projects/{id}/reports (markdown & json)
        rep_md = api_client.post("/projects/1/reports", json={"format": "markdown"})
        assert rep_md.status_code == 200
        assert "## 1. Executive Summary" in rep_md.json()["content"]

        rep_json = api_client.post("/projects/1/reports", json={"format": "json"})
        assert rep_json.status_code == 200
        assert "executive_summary" in rep_json.json()["content"]

    def test_project_isolation_and_404(self, api_client):
        # All endpoints must safely reject non-existent projects with 404
        assert api_client.get("/projects/999").status_code == 404
        assert api_client.post("/projects/999/repositories", json={"source": "foo"}).status_code == 404
        assert api_client.post("/projects/999/analyze").status_code == 404
        assert api_client.get("/projects/999/files").status_code == 404
        assert api_client.get("/projects/999/classes").status_code == 404
        assert api_client.get("/projects/999/methods").status_code == 404
        assert api_client.get("/projects/999/architecture").status_code == 404
        assert api_client.get("/projects/999/graph").status_code == 404
        assert api_client.get("/projects/999/risks").status_code == 404
        assert api_client.get("/projects/999/modernization").status_code == 404
        assert api_client.post("/projects/999/reports", json={"format": "markdown"}).status_code == 404
        assert api_client.get("/projects/999/analysis-runs").status_code == 404
