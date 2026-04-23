"""Schema access helpers for the simplified service layer."""

from dataclasses import dataclass
import re
from typing import Any, Dict, Optional, Protocol


class SchemaDatabaseClient(Protocol):
    """Describe the schema access needed by the service layer."""

    def get_database_schema(self) -> Dict[str, Any]:
        """Return schema information for the full database."""

    def get_table_names(self, schema: Optional[str] = None) -> list[str]:
        """List table names in the configured database."""

    def get_table_schema(
        self,
        table_name: str,
        schema: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return schema information for a single table."""


@dataclass(frozen=True, slots=True)
class SchemaQuery:
    """Describe a deterministic schema request detected from user text."""

    operation: str
    table_name: Optional[str] = None


class SchemaService:
    """Provide database schema information to the rest of the app."""

    def __init__(self, database_gateway: SchemaDatabaseClient) -> None:
        """Store the database gateway dependency."""
        self._database_gateway = database_gateway

    def get_database_schema(self) -> Dict[str, Any]:
        """Return the raw database schema from the configured gateway."""
        return self._database_gateway.get_database_schema()

    def list_tables(self) -> list[str]:
        """Return the available table names in deterministic order."""
        schema = self.get_database_schema()
        table_map = self._get_table_map(schema)
        if table_map:
            return sorted(table_map.keys())
        return self._database_gateway.get_table_names()

    def get_table_details(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Return a table schema when the requested table can be resolved."""
        schema = self.get_database_schema()
        table_map = self._get_table_map(schema)
        normalized_name = table_name.lower()

        if normalized_name in table_map:
            return table_map[normalized_name]

        for qualified_name, details in table_map.items():
            short_name = qualified_name.split(".")[-1]
            if normalized_name == short_name:
                return details

        return None

    def detect_schema_query(self, query: str) -> Optional[SchemaQuery]:
        """Detect table-listing or table-description requests from user text."""
        normalized = query.strip().lower()

        if self._is_table_listing_query(normalized):
            return SchemaQuery(operation="list_tables")

        if not self._is_table_description_query(normalized):
            return None

        table_name = self._extract_table_name(normalized)
        if not table_name:
            return None

        resolved_table = self._resolve_table_name(table_name)
        if not resolved_table:
            return None

        return SchemaQuery(operation="describe_table", table_name=resolved_table)

    @staticmethod
    def _is_table_listing_query(query: str) -> bool:
        """Return whether the user asked to see available tables."""
        phrases = (
            "show me all tables",
            "show all tables",
            "list all tables",
            "list tables",
            "show tables",
            "what tables",
            "which tables",
            "available tables",
        )
        return any(phrase in query for phrase in phrases)

    @staticmethod
    def _is_table_description_query(query: str) -> bool:
        """Return whether the user asked for the schema of a single table."""
        phrases = (
            "describe table",
            "describe the table",
            "schema for",
            "show schema for",
            "table schema for",
            "columns in",
            "columns of",
            "structure of",
        )
        return any(phrase in query for phrase in phrases)

    def _extract_table_name(self, query: str) -> Optional[str]:
        """Extract the most likely table name fragment from a schema query."""
        patterns = (
            r"(?:describe(?: the)? table)\s+([a-zA-Z_][\w\.]*)",
            r"(?:show\s+schema\s+for|schema\s+for|table\s+schema\s+for)\s+([a-zA-Z_][\w\.]*)",
            r"(?:columns\s+in|columns\s+of|structure\s+of)\s+([a-zA-Z_][\w\.]*)",
        )

        for pattern in patterns:
            match = re.search(pattern, query)
            if match:
                return match.group(1).rstrip("?.!,")
        return None

    def _resolve_table_name(self, table_name: str) -> Optional[str]:
        """Resolve a user-supplied table token to a known table name."""
        normalized_name = table_name.lower()
        for known_name in self.list_tables():
            lowered_name = known_name.lower()
            if normalized_name == lowered_name:
                return known_name
            if normalized_name == lowered_name.split(".")[-1]:
                return known_name
        return None

    @staticmethod
    def _get_table_map(schema: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
        """Normalize schema payloads from either full or simplified shapes."""
        tables = schema.get("tables")
        if isinstance(tables, dict):
            return tables

        if all(isinstance(value, dict) for value in schema.values()):
            return schema

        return {}
