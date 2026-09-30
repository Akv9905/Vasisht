"""Exercise the checked-in Alembic migration against a clean local database."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect, text


BACKEND_ROOT = Path(__file__).resolve().parents[1]
EXPECTED_TABLES = {
    "projects", "repositories", "files", "packages", "classes", "methods", "fields",
    "imports", "dependencies", "graph_nodes", "graph_edges", "api_endpoints",
    "database_references", "analysis_runs", "documents", "code_chunks", "questions",
    "answers", "evidence", "impact_analyses", "risk_findings", "modernization_findings",
    "users", "audit_logs",
}


def _alembic_config() -> Config:
    config = Config(str(BACKEND_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_ROOT / "migrations"))
    return config


def test_initial_migration_upgrade_and_downgrade():
    engine = create_engine("sqlite+pysqlite:///:memory:")
    config = _alembic_config()

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.upgrade(config, "head")

    assert EXPECTED_TABLES <= set(inspect(engine).get_table_names())
    with engine.connect() as connection:
        revision = connection.scalar(text("SELECT version_num FROM alembic_version"))
        assert revision == "9425eaf76796"

    with engine.begin() as connection:
        config.attributes["connection"] = connection
        command.downgrade(config, "base")
    assert set(inspect(engine).get_table_names()) == {"alembic_version"}
    with engine.connect() as connection:
        assert connection.scalar(text("SELECT COUNT(*) FROM alembic_version")) == 0
    engine.dispose()
