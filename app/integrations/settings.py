"""Typed application settings loaded from environment variables."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration for the API and integration layer."""

    app_name: str
    app_version: str
    host: str
    port: int
    log_level: str
    target_database_url: str
    google_api_key: str
    llm_model: str
    allow_target_writes: bool
    allow_target_deletes: bool
    schema_cache_ttl_seconds: float
    max_select_rows: int
    max_result_rows: int
    db_pool_size: int
    db_max_overflow: int
    db_pool_recycle: int
    checkpointer_backend: str
    checkpointer_database_url: str
    checkpointer_sqlite_path: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Build strongly typed settings from environment variables."""
        target_database_url = os.getenv("TARGET_DATABASE_URL")
        if not target_database_url:
            db_user = os.getenv("TARGET_DB_USER", os.getenv("DB_USER", ""))
            db_password = os.getenv("TARGET_DB_PASSWORD", os.getenv("DB_PASSWORD", ""))
            db_host = os.getenv("TARGET_DB_HOST", os.getenv("DB_HOST", "localhost"))
            db_port = os.getenv("TARGET_DB_PORT", os.getenv("DB_PORT", "5432"))
            db_name = os.getenv("TARGET_DB_NAME", os.getenv("DB_NAME", ""))
            target_database_url = (
                f"postgresql+psycopg://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
            )

        return cls(
            app_name="LangGraph Database Agent API",
            app_version="1.0.0",
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            target_database_url=target_database_url,
            google_api_key=os.getenv("GOOGLE_API_KEY", ""),
            llm_model=os.getenv("LLM_MODEL", "gemini-1.5-flash"),
            allow_target_writes=_env_flag("ALLOW_TARGET_WRITES", default=False),
            allow_target_deletes=_env_flag("ALLOW_TARGET_DELETES", default=False),
            schema_cache_ttl_seconds=float(os.getenv("SCHEMA_CACHE_TTL_SECONDS", "300")),
            max_select_rows=int(os.getenv("MAX_SELECT_ROWS", "1000")),
            max_result_rows=int(os.getenv("MAX_RESULT_ROWS", "10000")),
            db_pool_size=int(os.getenv("DB_POOL_SIZE", "10")),
            db_max_overflow=int(os.getenv("DB_MAX_OVERFLOW", "20")),
            db_pool_recycle=int(os.getenv("DB_POOL_RECYCLE", "1800")),
            checkpointer_backend=os.getenv("CHECKPOINTER_BACKEND", "memory"),
            checkpointer_database_url=os.getenv("CHECKPOINTER_DATABASE_URL", ""),
            checkpointer_sqlite_path=os.getenv("CHECKPOINTER_SQLITE_PATH", "checkpoints.db"),
        )

def _env_flag(name: str, default: bool = False) -> bool:
    """Parse common truthy environment values into booleans."""
    raw_value = os.getenv(name)
    if raw_value is None:
        return default
    return raw_value.strip().lower() in {"1", "true", "yes", "on"}
