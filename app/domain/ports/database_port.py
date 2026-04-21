"""Abstraction for database access used by application services."""

from typing import Any, Dict, List, Optional, Protocol


class DatabasePort(Protocol):
    """Define the database operations required by the application layer."""

    def test_connection(self) -> bool:
        """Verify that the backing database is reachable."""

    def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a SQL query and return a normalized result."""

    def get_table_names(self, schema: Optional[str] = None) -> List[str]:
        """List tables in the configured database."""

    def get_table_schema(
        self,
        table_name: str,
        schema: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return schema information for a specific table."""

    def get_database_schema(self) -> Dict[str, Any]:
        """Return schema information for the full database."""
