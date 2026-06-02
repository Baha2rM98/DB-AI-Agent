"""Schema access helpers for the simplified service layer."""

import asyncio
from dataclasses import dataclass
import re
import time
from typing import Any, Dict, Optional, Protocol

# Patterns for pulling a table name out of a description-style request,
# compiled once at import time rather than on every query.
_TABLE_NAME_PATTERNS = tuple(
    re.compile(pattern)
    for pattern in (
        r"(?:describe(?: the)? table)\s+([a-zA-Z_][\w\.]*)",
        r"(?:show\s+schema\s+for|schema\s+for|table\s+schema\s+for)\s+([a-zA-Z_][\w\.]*)",
        r"(?:columns\s+in|columns\s+of|structure\s+of)\s+([a-zA-Z_][\w\.]*)",
    )
)


class SchemaDatabaseClient(Protocol):
    """Describe async schema access needed by the service layer."""

    async def aget_database_schema(self) -> Dict[str, Any]:
        """Return schema information for the full database asynchronously."""

    async def aget_table_names(self, schema: Optional[str] = None) -> list[str]:
        """List table names asynchronously."""


@dataclass(frozen=True, slots=True)
class SchemaQuery:
    """Describe a deterministic schema request detected from user text."""

    operation: str
    table_name: Optional[str] = None


class SchemaService:
    """Provide database schema information to the rest of the app."""

    def __init__(
        self,
        database_gateway: SchemaDatabaseClient,
        cache_ttl_seconds: float = 300.0,
    ) -> None:
        """Store the database gateway dependency and configure schema caching."""
        self._database_gateway = database_gateway
        self._cache_ttl_seconds = cache_ttl_seconds
        self._schema_cache: Optional[Dict[str, Any]] = None
        self._schema_cache_expiry: float = 0.0
        self._cache_lock = asyncio.Lock()

    async def get_database_schema(self) -> Dict[str, Any]:
        """Return the database schema, served from a TTL cache when fresh.

        Inspecting a full database schema is expensive, so the result is cached
        for ``cache_ttl_seconds`` and shared across requests. A lock guards the
        refresh so concurrent callers don't trigger a stampede of inspections.
        """
        if self._is_cache_fresh():
            return self._schema_cache  # type: ignore[return-value]

        async with self._cache_lock:
            # Re-check inside the lock: another coroutine may have refreshed
            # the cache while we were waiting to acquire it.
            if self._is_cache_fresh():
                return self._schema_cache  # type: ignore[return-value]
            return await self._refresh_locked()

    async def refresh(self) -> Dict[str, Any]:
        """Force a schema refresh, bypassing and replacing the cached value."""
        async with self._cache_lock:
            return await self._refresh_locked()

    def invalidate(self) -> None:
        """Drop the cached schema so the next read re-inspects the database."""
        self._schema_cache = None
        self._schema_cache_expiry = 0.0

    def _is_cache_fresh(self) -> bool:
        """Return whether a cached schema exists and has not yet expired."""
        return self._schema_cache is not None and time.monotonic() < self._schema_cache_expiry

    async def _refresh_locked(self) -> Dict[str, Any]:
        """Fetch and cache the schema. Caller must hold ``_cache_lock``."""
        schema = await self._database_gateway.aget_database_schema()
        self._schema_cache = schema
        self._schema_cache_expiry = time.monotonic() + self._cache_ttl_seconds
        return schema

    async def list_tables(self) -> list[str]:
        """Return the available table names in deterministic order."""
        schema = await self.get_database_schema()
        table_map = self._get_table_map(schema)
        if table_map:
            return sorted(table_map.keys())
        return await self._database_gateway.aget_table_names()

    async def get_table_details(self, table_name: str) -> Optional[Dict[str, Any]]:
        """Return a table schema when the requested table can be resolved."""
        schema = await self.get_database_schema()
        table_map = self._get_table_map(schema)
        normalized_name = table_name.lower()

        if normalized_name in table_map:
            return table_map[normalized_name]

        for qualified_name, details in table_map.items():
            short_name = qualified_name.split(".")[-1]
            if normalized_name == short_name:
                return details

        return None

    async def detect_schema_query(self, query: str) -> Optional[SchemaQuery]:
        """Detect table-listing or table-description requests from user text."""
        normalized = query.strip().lower()

        if self._is_table_listing_query(normalized):
            return SchemaQuery(operation="list_tables")

        if not self._is_table_description_query(normalized):
            return None

        table_name = self._extract_table_name(normalized)
        if not table_name:
            return None

        resolved_table = await self._resolve_table_name(table_name)
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

    @staticmethod
    def _extract_table_name(query: str) -> Optional[str]:
        """Extract the most likely table name fragment from a schema query."""
        for pattern in _TABLE_NAME_PATTERNS:
            match = pattern.search(query)
            if match:
                return match.group(1).rstrip("?.!,")
        return None

    async def _resolve_table_name(self, table_name: str) -> Optional[str]:
        """Resolve a user-supplied table token to a known table name."""
        normalized_name = table_name.lower()
        for known_name in await self.list_tables():
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
