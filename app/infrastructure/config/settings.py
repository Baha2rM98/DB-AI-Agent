"""Typed application settings loaded from the environment."""

import os
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """Runtime configuration for the API and infrastructure layer."""

    app_name: str
    app_version: str
    host: str
    port: int
    log_level: str
    database_url: str
    google_api_key: str

    @classmethod
    def from_env(cls) -> "Settings":
        """Build strongly typed settings from environment variables."""
        db_user = os.getenv("DB_USER", "")
        db_password = os.getenv("DB_PASSWORD", "")
        db_host = os.getenv("DB_HOST", "localhost")
        db_port = os.getenv("DB_PORT", "5432")
        db_name = os.getenv("DB_NAME", "")

        return cls(
            app_name="LangGraph Database Agent API",
            app_version="1.0.0",
            host=os.getenv("HOST", "0.0.0.0"),
            port=int(os.getenv("PORT", "8000")),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
            database_url=(
                f"postgresql://{db_user}:{db_password}@{db_host}:{db_port}/{db_name}"
            ),
            google_api_key=os.getenv("GOOGLE_API_KEY", ""),
        )
