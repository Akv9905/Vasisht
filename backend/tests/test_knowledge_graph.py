"""Knowledge Graph (P5) unit and integration tests.

Tests cover:
- Direct neighbors (incoming, outgoing, both; with relationship filters)
- Upstream and downstream dependency discovery
- Bounded depth-limited traversal and cycle protection
- Shortest paths between codebase entities
- Request-flow tracing from HTTP endpoint through Controller, Service, and Repository to Database
- Change-impact analysis for affected controllers, services, repositories, and tests
- Architecture relationship verification: Controller -> Service -> Repository -> Table
- PostgresKnowledgeGraph integration with database sessions
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.graph.extractor import extract_dependencies
from app.graph.models import DependencyGraph, GraphEdge, GraphNode, RelationshipType
from app.graph.postgres import PostgresKnowledgeGraph
from app.graph.traversal import (
    ArchitectureChain,
    ImpactResult,
    RequestFlowResult,
    ShortestPathResult,
    TraversalResult,
    bounded_traversal,
    find_shortest_path,
    get_direct_neighbors,
    get_downstream_dependencies,
    get_upstream_dependencies,
    impact_traversal,
    trace_request_flow,
    verify_controller_service_repository,
)
from app.ingestion.scanner import scan_path
from app.models import Base
from app.parser import parse_java_files
from app.persistence import persist_analysis

SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample-projects" / "payment-service"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def sample_graph() -> DependencyGraph:
    """Extract in-memory dependency graph from the sample payment-service."""
    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    return extract_dependencies(parse_result)


@pytest.fixture
def db_session(sample_graph: DependencyGraph) -> Session:
    """Create an SQLite in-memory database with persisted sample analysis."""
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    persist_analysis(session, scan, parse_result, sample_graph, project_name="test-project")
    session.commit()

    yield session
    session.close()
    engine.dispose()


# ---------------------------------------------------------------------------
# Direct Neighbors Tests
# ---------------------------------------------------------------------------


class TestDirectNeighbors:
    def test_get_outgoing_neighbors(self, sample_graph: DependencyGraph):
        ctrl = sample_graph.find_nodes(name="PaymentController", kind="class")[0]
        neighbors = get_direct_neighbors(sample_graph, ctrl.id, direction="outgoing")
        assert len(neighbors) > 0
        assert all(n.direction == "outgoing" for n in neighbors)
        names = {n.node.name for n in neighbors}
        assert "PaymentService" in names

    def test_get_incoming_neighbors(self, sample_graph: DependencyGraph):
        svc = sample_graph.find_nodes(name="PaymentService", kind="class")[0]
        neighbors = get_direct_neighbors(sample_graph, svc.id, direction="incoming")
        assert len(neighbors) > 0
        assert all(n.direction == "incoming" for n in neighbors)
        names = {n.node.name for n in neighbors}
        assert "PaymentController" in names

    def test_get_neighbors_filtered_by_relationship(self, sample_graph: DependencyGraph):
        ctrl = sample_graph.find_nodes(name="PaymentController", kind="class")[0]
        dep_neighbors = get_direct_neighbors(
            sample_graph, ctrl.id, direction="outgoing", relationship=RelationshipType.DEPENDS_ON
        )
        assert len(dep_neighbors) >= 1
        assert all(n.edge.relationship == RelationshipType.DEPENDS_ON for n in dep_neighbors)
        assert any(n.node.name == "PaymentService" for n in dep_neighbors)

    def test_nonexistent_node_neighbors(self, sample_graph: DependencyGraph):
        neighbors = get_direct_neighbors(sample_graph, "nonexistent_node_id")
        assert neighbors == []


# ---------------------------------------------------------------------------
# Bounded Traversal Tests
# ---------------------------------------------------------------------------


class TestBoundedTraversal:
    def test_bounded_traversal_depth_1(self, sample_graph: DependencyGraph):
        ctrl = sample_graph.find_nodes(name="PaymentController", kind="class")[0]
        result: TraversalResult = bounded_traversal(
            sample_graph, ctrl.id, max_depth=1, direction="outgoing"
        )
        assert result.start_node_id == ctrl.id
        assert result.max_depth_reached <= 1
        assert all(d <= 1 for d in result.depth_map.values())
        assert len(result.visited_nodes) > 1

    def test_bounded_traversal_cycle_protection(self, sample_graph: DependencyGraph):
        # NotificationService and PaymentService have deliberate circular dependencies
        svc = sample_graph.find_nodes(name="PaymentService", kind="class")[0]
        result = bounded_traversal(sample_graph, svc.id, max_depth=5, direction="outgoing")
        # Should terminate cleanly without infinite loop
        assert result.max_depth_reached <= 5
        assert len(result.visited_nodes) < 200

    def test_bounded_traversal_kind_filter(self, sample_graph: DependencyGraph):
        ctrl = sample_graph.find_nodes(name="PaymentController", kind="class")[0]
        result = bounded_traversal(
            sample_graph,
            ctrl.id,
            max_depth=2,
            direction="outgoing",
            filter_kinds=["endpoint"],
        )
        assert all(n.kind == "endpoint" or n.id == ctrl.id for n in result.visited_nodes)

    def test_upstream_dependencies(self, sample_graph: DependencyGraph):
        repo = sample_graph.find_nodes(name="PaymentRepository", kind="interface")[0]
        upstream = get_upstream_dependencies(sample_graph, repo.id, max_depth=2)
        names = {n.name for n in upstream.visited_nodes}
        assert "PaymentService" in names

    def test_downstream_dependencies(self, sample_graph: DependencyGraph):
        ctrl = sample_graph.find_nodes(name="PaymentController", kind="class")[0]
        downstream = get_downstream_dependencies(sample_graph, ctrl.id, max_depth=2)
        names = {n.name for n in downstream.visited_nodes}
        assert "PaymentService" in names


# ---------------------------------------------------------------------------
# Shortest Path Tests
# ---------------------------------------------------------------------------


class TestShortestPath:
    def test_shortest_path_controller_to_table(self, sample_graph: DependencyGraph):
        ctrl = sample_graph.find_nodes(name="PaymentController", kind="class")[0]
        table = sample_graph.find_nodes(name="payments", kind="database_table")[0]
        path: ShortestPathResult | None = find_shortest_path(sample_graph, ctrl.id, table.id)
        assert path is not None
        assert path.source_id == ctrl.id
        assert path.target_id == table.id
        assert path.length > 0
        assert path.nodes[0].id == ctrl.id
        assert path.nodes[-1].id == table.id

    def test_shortest_path_controller_to_service(self, sample_graph: DependencyGraph):
        ctrl = sample_graph.find_nodes(name="PaymentController", kind="class")[0]
        svc = sample_graph.find_nodes(name="PaymentService", kind="class")[0]
        path = find_shortest_path(
            sample_graph,
            ctrl.id,
            svc.id,
            relationships=["DEPENDS_ON"],
        )
        assert path is not None
        assert path.length == 1
        assert path.edges[0].relationship == RelationshipType.DEPENDS_ON

    def test_shortest_path_nonexistent_target(self, sample_graph: DependencyGraph):
        ctrl = sample_graph.find_nodes(name="PaymentController", kind="class")[0]
        path = find_shortest_path(sample_graph, ctrl.id, "nonexistent:target")
        assert path is None


# ---------------------------------------------------------------------------
# Request Flow Tracing Tests
# ---------------------------------------------------------------------------


class TestRequestFlowTracing:
    def test_trace_request_flow_from_endpoint(self, sample_graph: DependencyGraph):
        flow: RequestFlowResult = trace_request_flow(
            sample_graph, "endpoint:POST:/api/payment"
        )
        assert flow.endpoint == "endpoint:POST:/api/payment"
        assert len(flow.steps) >= 3
        step_names = [s.node_name for s in flow.steps]
        assert "POST /api/payment" in step_names
        assert "create" in step_names or "PaymentController" in step_names
        assert "processPayment" in step_names or "PaymentService" in step_names
        assert flow.reaches_database is True
        assert flow.database_table == "payments"

    def test_trace_request_flow_summary_lines(self, sample_graph: DependencyGraph):
        flow = trace_request_flow(sample_graph, "endpoint:POST:/api/payment")
        lines = flow.summary_lines()
        assert len(lines) >= 4
        assert any("Request Flow for" in line for line in lines)
        assert any("Reaches database table: payments" in line for line in lines)

    def test_trace_request_flow_nonexistent(self, sample_graph: DependencyGraph):
        flow = trace_request_flow(sample_graph, "/api/doesnotexist")
        assert flow.reaches_database is False
        assert len(flow.steps) == 0
        assert len(flow.unresolved_steps) >= 1


# ---------------------------------------------------------------------------
# Change Impact Traversal Tests
# ---------------------------------------------------------------------------


class TestImpactTraversal:
    def test_impact_payment_service(self, sample_graph: DependencyGraph):
        svc = sample_graph.find_nodes(name="PaymentService", kind="class")[0]
        impact: ImpactResult = impact_traversal(sample_graph, svc.id)
        assert impact.target_id == svc.id
        assert len(impact.affected_nodes) > 0
        # Controllers that call or depend on PaymentService
        ctrl_names = {n.name for n in impact.affected_controllers}
        assert "PaymentController" in ctrl_names
        # Tests that exercise PaymentService
        test_names = {n.name for n in impact.affected_tests}
        assert "PaymentServiceTest" in test_names

    def test_impact_summary_lines(self, sample_graph: DependencyGraph):
        svc = sample_graph.find_nodes(name="PaymentService", kind="class")[0]
        impact = impact_traversal(sample_graph, svc.id)
        lines = impact.summary_lines()
        assert any("Impact Analysis for: PaymentService" in line for line in lines)
        assert any("Affected Controllers" in line for line in lines)
        assert any("Affected Tests" in line for line in lines)

    def test_impact_nonexistent_symbol(self, sample_graph: DependencyGraph):
        impact = impact_traversal(sample_graph, "NonexistentClass")
        assert impact.target_kind == "unknown"
        assert impact.affected_nodes == []


# ---------------------------------------------------------------------------
# Controller → Service → Repository Architecture Verification Tests
# ---------------------------------------------------------------------------


class TestArchitectureVerification:
    def test_verify_controller_service_repository_chain(self, sample_graph: DependencyGraph):
        chains: list[ArchitectureChain] = verify_controller_service_repository(sample_graph)
        assert len(chains) >= 1

        payment_chain = next(
            (c for c in chains if c.controller_node.name == "PaymentController"), None
        )
        assert payment_chain is not None
        assert payment_chain.controller_node.name == "PaymentController"
        assert payment_chain.service_node.name == "PaymentService"
        assert payment_chain.repository_node.name == "PaymentRepository"
        assert payment_chain.table_node is not None
        assert payment_chain.table_node.name == "payments"
        assert payment_chain.endpoint_node is not None
        assert "/api/payment" in payment_chain.endpoint_node.name
        assert payment_chain.verified is True
        assert len(payment_chain.type_chain_edges) >= 3
        assert len(payment_chain.call_chain_edges) >= 1

    def test_chain_summary_line(self, sample_graph: DependencyGraph):
        chains = verify_controller_service_repository(sample_graph)
        assert len(chains) >= 1
        summary = chains[0].summary_line()
        assert "PaymentController" in summary or "RefundController" in summary
        assert "PaymentService" in summary
        assert "PaymentRepository" in summary


# ---------------------------------------------------------------------------
# PostgresKnowledgeGraph Service Integration Tests
# ---------------------------------------------------------------------------


class TestPostgresKnowledgeGraphIntegration:
    def test_load_graph_from_session(self, db_session: Session):
        pkg = PostgresKnowledgeGraph(db_session)
        assert pkg.analysis_run_id > 0
        graph = pkg.load_graph()
        assert len(graph.nodes) > 50
        assert len(graph.edges) > 50

    def test_get_node_from_db(self, db_session: Session):
        pkg = PostgresKnowledgeGraph(db_session)
        node = pkg.get_node("type:com.example.payment.controller.PaymentController")
        assert node is not None
        assert node.name == "PaymentController"
        assert node.kind == "class"

    def test_find_nodes_by_kind_and_name(self, db_session: Session):
        pkg = PostgresKnowledgeGraph(db_session)
        nodes = pkg.find_nodes(kind="database_table", name="payments")
        assert len(nodes) == 1
        assert nodes[0].name == "payments"

    def test_postgres_neighbors_query(self, db_session: Session):
        pkg = PostgresKnowledgeGraph(db_session)
        ctrl = pkg.find_nodes(name="PaymentController", kind="class")[0]
        neighbors = pkg.get_neighbors(ctrl.id, direction="outgoing")
        assert len(neighbors) > 0
        names = {n.node.name for n in neighbors}
        assert "PaymentService" in names

    def test_postgres_architecture_verification(self, db_session: Session):
        pkg = PostgresKnowledgeGraph(db_session)
        chains = pkg.verify_controller_service_repository()
        assert len(chains) >= 1
        match = next((c for c in chains if c.controller_node.name == "PaymentController"), None)
        assert match is not None
        assert match.service_node.name == "PaymentService"
        assert match.repository_node.name == "PaymentRepository"
        assert match.table_node is not None
        assert match.table_node.name == "payments"

    def test_postgres_request_flow(self, db_session: Session):
        pkg = PostgresKnowledgeGraph(db_session)
        flow = pkg.trace_request_flow("endpoint:POST:/api/payment")
        assert flow.reaches_database is True
        assert flow.database_table == "payments"
        assert len(flow.steps) >= 4

    def test_postgres_impact_traversal(self, db_session: Session):
        pkg = PostgresKnowledgeGraph(db_session)
        svc = pkg.find_nodes(name="PaymentService", kind="class")[0]
        impact = pkg.impact_traversal(svc.id)
        assert len(impact.affected_controllers) >= 1
        assert any(c.name == "PaymentController" for c in impact.affected_controllers)
