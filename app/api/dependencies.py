"""Dependency providers for the simplified FastAPI application."""

from functools import lru_cache

from app.integrations.database import SQLAlchemyDatabaseGateway
from app.integrations.persistent_agent import PersistentLangGraphAgent
from app.integrations.settings import Settings
from app.services.query_service import QueryService
from app.services.schema_service import SchemaService


@lru_cache
def get_settings() -> Settings:
    """Load and cache typed application settings."""
    return Settings.from_env()


@lru_cache
def get_target_database_gateway() -> SQLAlchemyDatabaseGateway:
    """Create the gateway for the external database users ask about."""
    settings = get_settings()
    return SQLAlchemyDatabaseGateway(settings.target_database_url)


def get_database_gateway() -> SQLAlchemyDatabaseGateway:
    """Backward-compatible dependency alias for the target database gateway."""
    return get_target_database_gateway()


@lru_cache
def get_schema_service() -> SchemaService:
    """Create the schema service for the external target database."""
    return SchemaService(get_target_database_gateway())


@lru_cache
def get_query_service() -> QueryService:
    """Create the main query orchestration service."""
    settings = get_settings()
    schema_service = get_schema_service()
    return QueryService(
        agent=PersistentLangGraphAgent(settings=settings, schema_service=schema_service),
        database_gateway=get_target_database_gateway(),
        schema_service=schema_service,
        allow_writes=settings.allow_target_writes,
        allow_deletes=settings.allow_target_deletes,
    )
