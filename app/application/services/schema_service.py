"""Services responsible for schema access and formatting."""

from typing import Any, Dict

from app.domain.ports.database_port import DatabasePort


class SchemaService:
    """Provide database schema information to the application layer."""

    def __init__(self, database_gateway: DatabasePort) -> None:
        """Store the database gateway dependency."""
        self._database_gateway = database_gateway

    def get_database_schema(self) -> Dict[str, Any]:
        """Return the raw database schema from the configured gateway."""
        return self._database_gateway.get_database_schema()
