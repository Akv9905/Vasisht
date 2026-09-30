"""Tests for Evaluation Framework (P21).

Verifies:
- 35 evaluation items across 10 categories
- EvaluationRunner calculations (retrieval, evidence, entity, relationship correctness, grounding, hallucination rate)
- Hallucination rate is 0.0% in deterministic local mode
- Evidence and grounding are high (>= 85%)
- Markdown and JSON report exports
- Repeatable execution without external or paid APIs
"""

from __future__ import annotations

from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.evaluation.dataset import EVALUATION_DATASET, EvaluationItem
from app.evaluation.evaluator import EvaluationReport, EvaluationResult, EvaluationRunner
from app.graph.extractor import extract_dependencies
from app.graph.models import DependencyGraph
from app.ingestion.scanner import scan_path
from app.models import Base, Project, Repository
from app.parser import parse_java_files
from app.persistence import persist_analysis

SAMPLE_ROOT = Path(__file__).resolve().parents[2] / "sample-projects" / "payment-service"


@pytest.fixture(scope="module")
def sample_analysis():
    """Scan and parse payment-service once."""
    scan = scan_path(SAMPLE_ROOT)
    parse_result = parse_java_files(scan.root, scan.java_files)
    graph = extract_dependencies(parse_result)
    return scan, parse_result, graph


@pytest.fixture
def db_session(sample_analysis) -> tuple[Session, int]:
    """In-memory DB with persisted payment-service project."""
    scan, parse_result, graph = sample_analysis
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    session = SessionLocal()

    persisted = persist_analysis(session, scan, parse_result, graph, project_name="eval-payment-service")

    yield session, persisted.project_id
    session.close()


def test_evaluation_dataset_completeness():
    """Verify dataset contains 35 items spanning all 10 required categories."""
    assert len(EVALUATION_DATASET) >= 30
    assert len(EVALUATION_DATASET) <= 50

    categories = {item.category for item in EVALUATION_DATASET}
    expected_categories = {
        "architecture",
        "request_flow",
        "dependencies",
        "classes",
        "methods",
        "apis",
        "database_interaction",
        "impact",
        "risk",
        "modernization",
    }
    assert expected_categories.issubset(categories)

    for item in EVALUATION_DATASET:
        assert item.id
        assert item.question
        assert len(item.expected_entities) > 0
        assert len(item.expected_relationships) > 0
        assert len(item.evidence_requirements) > 0
        assert len(item.acceptable_answer_characteristics) > 0


def test_evaluator_single_item(sample_analysis, db_session):
    """Test evaluating a single benchmark item."""
    scan, parse_result, graph = sample_analysis
    session, project_id = db_session

    runner = EvaluationRunner(
        session=session,
        project_id=project_id,
        graph=graph,
        scan=scan,
        parse_result=parse_result,
    )

    first_item = EVALUATION_DATASET[0]  # arch-01
    result = runner.evaluate_item(first_item)

    assert result.item_id == "arch-01"
    assert result.category == "architecture"
    assert result.hallucination_rate == 0.0
    assert result.evidence_correctness == 1.0
    assert result.entity_correctness > 0.5
    assert result.answer_grounding == 1.0


def test_evaluator_impact_item(sample_analysis, db_session):
    """Test evaluating an impact benchmark item."""
    scan, parse_result, graph = sample_analysis
    session, project_id = db_session

    runner = EvaluationRunner(
        session=session,
        project_id=project_id,
        graph=graph,
        scan=scan,
        parse_result=parse_result,
    )

    impact_items = [i for i in EVALUATION_DATASET if i.category == "impact"]
    assert len(impact_items) >= 3

    result = runner.evaluate_item(impact_items[0])
    assert result.category == "impact"
    assert result.impact_correctness is not None
    assert result.impact_correctness > 0.0
    assert result.hallucination_rate == 0.0


def test_evaluator_run_all_metrics(sample_analysis, db_session):
    """Run full benchmark dataset and verify high grounding and zero hallucination."""
    scan, parse_result, graph = sample_analysis
    session, project_id = db_session

    runner = EvaluationRunner(
        session=session,
        project_id=project_id,
        graph=graph,
        scan=scan,
        parse_result=parse_result,
    )

    report = runner.run_all()

    assert report.total_items == len(EVALUATION_DATASET)
    assert report.passed_items >= int(len(EVALUATION_DATASET) * 0.70)
    assert report.mean_hallucination_rate == 0.0  # Zero hallucination rate
    assert report.mean_evidence_correctness >= 0.85
    assert report.mean_answer_grounding >= 0.85
    assert report.mean_entity_correctness >= 0.60

    # Ensure all 10 categories are in results_by_category
    assert len(report.results_by_category) == 10

    # Test export functions
    rep_dict = report.to_dict()
    assert "summary" in rep_dict
    assert rep_dict["summary"]["mean_hallucination_rate"] == 0.0

    markdown = report.to_markdown()
    assert "# Evaluation Benchmark Report" in markdown
    assert "## Category Breakdown" in markdown
