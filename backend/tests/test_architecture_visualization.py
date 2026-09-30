"""Tests for Architecture Visualization (P14).

Verifies:
- Representation of:
  - packages
  - modules
  - controllers
  - services
  - repositories
  - databases
  - APIs
  - external integrations
  - tests
- Graph data formatted for frontend visualization (nodes, edges, categories)
- FastAPI GET /projects/{id}/architecture
- FastAPI GET /projects/{id}/graph
- Regression checks for previous phases
"""

from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.analysis.architecture import build_architecture_view, build_graph_visualization
from app.database import get_db
from app.graph.extractor import extract_dependencies
from app.ingestion.scanner import scan_path
from app.main import app
from app.models import Base
from app.parser import parse_java_files
from app.persistence import persist_analysis

SAMPLE_ROOT = Path(__file__).resolve().parent.parent.parent / "sample-projects" / "payment-service"


@pytest.fixture(scope="module")
def sample_analysis():
    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parse_result)
    return scan, parse_result, graph


class TestArchitectureView:
    def test_architecture_representation_contains_all_components(self, sample_analysis):
        _, pr, graph = sample_analysis
        arch = build_architecture_view(graph, pr)

        # 1. Packages
        assert len(arch.packages) > 0
        pkg_names = {p["name"] for p in arch.packages}
        assert any("payment" in name for name in pkg_names)

        # 2. Modules
        assert len(arch.modules) > 0
        assert arch.modules[0]["name"] == "root-module"

        # 3. Controllers
        assert len(arch.controllers) >= 2
        ctrl_names = {c["name"] for c in arch.controllers}
        assert "PaymentController" in ctrl_names
        assert "RefundController" in ctrl_names

        # 4. Services
        assert len(arch.services) >= 2
        svc_names = {s["name"] for s in arch.services}
        assert "PaymentService" in svc_names

        # 5. Repositories
        assert len(arch.repositories) >= 1
        repo_names = {r["name"] for r in arch.repositories}
        assert "PaymentRepository" in repo_names

        # 6. Databases
        assert len(arch.databases) >= 1
        db_names = {d["name"] for d in arch.databases}
        assert "payments" in db_names

        # 7. APIs
        assert len(arch.apis) >= 2
        api_paths = {a["path"] for a in arch.apis}
        assert any("/api/payment" in p for p in api_paths)

        # 8. External integrations
        assert len(arch.external_integrations) >= 1
        ext_names = {e["name"] for e in arch.external_integrations}
        assert "MetricsFacade" in ext_names

        # 9. Tests
        assert len(arch.tests) >= 1
        test_names = {t["name"] for t in arch.tests}
        assert "PaymentServiceTest" in test_names

        # 10. Chains
        assert len(arch.chains) >= 1
        payment_chain = next(c for c in arch.chains if "/api/payment" in c["endpoint"])
        assert payment_chain["controller"] == "PaymentController"
        assert payment_chain["service"] == "PaymentService"
        assert payment_chain["repository"] == "PaymentRepository"
        assert payment_chain["database_table"] == "payments"

    def test_graph_visualization_data(self, sample_analysis):
        _, _, graph = sample_analysis
        viz = build_graph_visualization(graph)

        assert viz["total_nodes"] > 0
        assert viz["total_edges"] > 0
        assert len(viz["nodes"]) == viz["total_nodes"]
        assert len(viz["edges"]) == viz["total_edges"]

        # Check node structure
        first_node = viz["nodes"][0]
        assert "id" in first_node
        assert "label" in first_node
        assert "kind" in first_node
        assert "category" in first_node

        # Check edge structure
        first_edge = viz["edges"][0]
        assert "source" in first_edge
        assert "target" in first_edge
        assert "relationship" in first_edge

        # Check categories
        cats = viz["categories"]
        assert "controller" in cats
        assert "service" in cats
        assert "repository" in cats
        assert "database" in cats
        assert "api" in cats

    def test_graph_visualization_filtering(self, sample_analysis):
        _, _, graph = sample_analysis
        # Filter for only controllers and services
        viz = build_graph_visualization(graph, category_filter=["controller", "service"])
        categories_in_nodes = {n["category"] for n in viz["nodes"]}
        assert categories_in_nodes.issubset({"controller", "service"})


class TestFastAPIArchitectureEndpoints:
    @pytest.fixture
    def test_client(self, sample_analysis):
        scan, pr, graph = sample_analysis
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
        session = TestingSessionLocal()

        persist_analysis(
            session,
            scan,
            pr,
            graph,
            project_name="PaymentServiceArchTest",
        )

        def override_get_db():
            yield session

        app.dependency_overrides[get_db] = override_get_db
        client = TestClient(app)
        yield client
        app.dependency_overrides.clear()
        session.close()
        engine.dispose()

    def test_get_architecture_success(self, test_client):
        resp = test_client.get("/projects/1/architecture")
        assert resp.status_code == 200
        data = resp.json()

        assert "packages" in data
        assert "modules" in data
        assert "controllers" in data
        assert "services" in data
        assert "repositories" in data
        assert "databases" in data
        assert "apis" in data
        assert "external_integrations" in data
        assert "tests" in data
        assert "chains" in data

        assert len(data["controllers"]) >= 2
        assert len(data["services"]) >= 2
        assert len(data["repositories"]) >= 1

    def test_get_graph_success(self, test_client):
        resp = test_client.get("/projects/1/graph")
        assert resp.status_code == 200
        data = resp.json()

        assert "nodes" in data
        assert "edges" in data
        assert "categories" in data
        assert "total_nodes" in data
        assert "total_edges" in data
        assert data["total_nodes"] > 0
        assert data["total_edges"] > 0

    def test_get_graph_with_category_filtering(self, test_client):
        resp = test_client.get("/projects/1/graph?categories=controller&categories=service")
        assert resp.status_code == 200
        data = resp.json()

        for n in data["nodes"]:
            assert n["category"] in ("controller", "service")

    def test_get_architecture_nonexistent_project_returns_404(self, test_client):
        resp = test_client.get("/projects/9999/architecture")
        assert resp.status_code == 404

    def test_get_graph_nonexistent_project_returns_404(self, test_client):
        resp = test_client.get("/projects/9999/graph")
        assert resp.status_code == 404
