"""Dependency providers for the FastAPI application."""

from functools import lru_cache

from app.application.services.query_service import QueryService
from app.application.services.schema_service import SchemaService
from app.infrastructure.config.settings import Settings
from app.infrastructure.database.sqlalchemy_database import SQLAlchemyDatabaseGateway
from app.infrastructure.langgraph.persistent_agent import PersistentLangGraphAgent


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
def get_query_service() -> QueryService:
    """Create the main query orchestration service."""
    settings = get_settings()
    schema_service = get_schema_service()
    return QueryService(
        agent=PersistentLangGraphAgent(settings=settings, schema_service=schema_service),
        database_gateway=get_database_gateway(),
        schema_service=schema_service,
    )
