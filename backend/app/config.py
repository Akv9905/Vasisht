"""Application configuration. Local/free mode by default — no paid APIs required."""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "Enterprise AI"
    app_env: str = "development"
    debug: bool = True

    # Optional PostgreSQL — scanner (P0/P1) works without a database.
    database_url: str = "postgresql+psycopg://enterprise_ai:enterprise_ai@localhost:5432/enterprise_ai"

    # Optional local LLM — never required.
    llm_enabled: bool = False
    llm_provider: str = "none"  # none | local | optional_api
    llm_base_url: str = ""
    llm_model: str = ""
    llm_api_key: str = ""

    # Ingestion
    max_upload_bytes: int = 100 * 1024 * 1024  # 100 MiB
    extract_dir: Path = Path("data/extracts")
    ignore_dirs: str = ".git,node_modules,target,build,dist,.idea,.vscode,__pycache__,.gradle"

    @property
    def ignore_dir_names(self) -> set[str]:
        return {name.strip() for name in self.ignore_dirs.split(",") if name.strip()}


@lru_cache
def get_settings() -> Settings:
    return Settings()
