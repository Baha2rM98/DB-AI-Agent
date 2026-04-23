"""Schema access helpers for the simplified service layer."""

from typing import Any, Dict, Protocol


class SchemaDatabaseClient(Protocol):
    """Describe the schema access needed by the service layer."""

    def get_database_schema(self) -> Dict[str, Any]:
        """Return schema information for the full database."""


class SchemaService:
    """Provide database schema information to the rest of the app."""

    def __init__(self, database_gateway: SchemaDatabaseClient) -> None:
        """Store the database gateway dependency."""
        self._database_gateway = database_gateway

    def get_database_schema(self) -> Dict[str, Any]:
        """Return the raw database schema from the configured gateway."""
        return self._database_gateway.get_database_schema()
