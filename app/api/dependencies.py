"""Dependency providers for the FastAPI application."""

from functools import lru_cache

from app.application.services.query_service import QueryService
from app.application.services.schema_service import SchemaService
from app.infrastructure.agent.legacy_db_agent import LegacyDBAgent
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.sqlalchemy_database import SQLAlchemyDatabaseGateway


@lru_cache
def get_settings() -> Settings:
    """Load and cache typed application settings."""
    return Settings.from_env()


@lru_cache
def get_database_gateway() -> SQLAlchemyDatabaseGateway:
    """Create the shared database gateway used by application services."""
    settings = get_settings()
    return SQLAlchemyDatabaseGateway(settings.database_url)


@lru_cache
def get_schema_service() -> SchemaService:
    """Create the schema formatting service."""
    return SchemaService(get_database_gateway())


@lru_cache
def get_agent() -> LegacyDBAgent:
    """Create the current query agent adapter."""
    settings = get_settings()
    return LegacyDBAgent(settings.database_url)


@lru_cache
def get_query_service() -> QueryService:
    """Create the main query orchestration service."""
    return QueryService(
        agent=get_agent(),
        database_gateway=get_database_gateway(),
        schema_service=get_schema_service(),
    )
