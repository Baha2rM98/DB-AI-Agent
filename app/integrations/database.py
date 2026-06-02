"""SQLAlchemy-backed database integration.

This module is the single place where the application talks directly to
SQLAlchemy for connectivity, raw query execution, and schema inspection.
It exposes both sync and async methods so the app can use native async
database access while the test suite still exercises deterministic sync paths.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import create_async_engine

logger = logging.getLogger(__name__)


class SQLAlchemyDatabaseGateway:
    """Execute SQL queries and inspect schemas through SQLAlchemy."""

    def __init__(
        self,
        connection_string: str,
        *,
        pool_size: int = 10,
        max_overflow: int = 20,
        pool_recycle: int = 1800,
        pool_pre_ping: bool = True,
        max_result_rows: int = 10000,
    ) -> None:
        """Create the async SQLAlchemy engine for the configured database.

        The connection pool is tuned for concurrent request load:
        ``pool_pre_ping`` discards connections the server has dropped, and
        ``pool_recycle`` retires long-lived ones. The synchronous engine backs
        only inspection helpers and the test suite, so it is created lazily
        (see the ``engine`` property) to avoid a second idle pool in production.
        ``max_result_rows`` caps how many rows are materialized into memory.
        """
        self.connection_string = connection_string
        self.async_connection_string = self._build_async_connection_string(connection_string)
        self._engine_kwargs: Dict[str, Any] = {
            "pool_size": pool_size,
            "max_overflow": max_overflow,
            "pool_recycle": pool_recycle,
            "pool_pre_ping": pool_pre_ping,
        }
        self._max_result_rows = max_result_rows
        self._sync_engine = None
        self.async_engine = create_async_engine(
            self.async_connection_string, **self._engine_kwargs
        )
        self._pk_cache: Dict[str, List[str]] = {}

    @property
    def engine(self):
        """Return the synchronous engine, creating it on first use."""
        if self._sync_engine is None:
            self._sync_engine = create_engine(self.connection_string, **self._engine_kwargs)
        return self._sync_engine

    def _build_rows(self, result: Any) -> List[Dict[str, Any]]:
        """Materialize result rows into dicts, capped at ``max_result_rows``.

        Bounds Python-side memory for unexpectedly large result sets. When the
        cap is reached the truncation is logged rather than silently hidden.
        """
        columns = result.keys()
        cap = self._max_result_rows
        raw_rows = result.fetchmany(cap) if cap and cap > 0 else result.fetchall()
        rows = [dict(zip(columns, row)) for row in raw_rows]
        if cap and cap > 0 and len(rows) >= cap:
            logger.warning(
                "Result truncated to the %d-row cap; additional rows may exist.", cap
            )
        return rows

    def test_connection(self) -> bool:
        """Return whether the database accepts a simple probe query."""
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
                return True
        except SQLAlchemyError:
            return False

    async def atest_connection(self) -> bool:
        """Return whether the database accepts a simple probe query asynchronously."""
        try:
            async with self.async_engine.connect() as connection:
                await connection.execute(text("SELECT 1"))
                return True
        except SQLAlchemyError:
            return False

    def execute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute raw SQL and normalize the result shape for the app."""
        try:
            operation_type = self._detect_operation_type(query)

            if operation_type in ["insert", "update"]:
                query = self._add_returning_clause(query, operation_type)

            with self.engine.connect() as connection:
                if operation_type in ["insert", "update", "delete"]:
                    transaction = connection.begin()
                    try:
                        result = (
                            connection.execute(text(query), params)
                            if params
                            else connection.execute(text(query))
                        )
                        transaction.commit()
                    except Exception:
                        transaction.rollback()
                        raise
                else:
                    result = (
                        connection.execute(text(query), params)
                        if params
                        else connection.execute(text(query))
                    )

                if operation_type == "select" or result.returns_rows:
                    rows = self._build_rows(result)
                    affected_rows = (
                        len(rows)
                        if operation_type in ["insert", "update"] and rows
                        else result.rowcount if result.rowcount >= 0 else len(rows)
                    )
                    return {
                        "success": True,
                        "data": rows,
                        "affected_rows": affected_rows,
                        "operation_type": operation_type,
                    }

                affected_rows = result.rowcount if result.rowcount >= 0 else 0
                if operation_type == "insert" and result.rowcount == -1:
                    affected_rows = 1

                return {
                    "success": True,
                    "data": [],
                    "affected_rows": affected_rows,
                    "operation_type": operation_type,
                }
        except SQLAlchemyError as exc:
            error_message = self._normalize_sql_error(str(exc))
            logger.error("SQL execution failed: %s", error_message)
            return {
                "success": False,
                "error": error_message,
                "operation_type": self._detect_operation_type(query),
            }

    async def aexecute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute raw SQL using the native async SQLAlchemy engine."""
        try:
            operation_type = self._detect_operation_type(query)

            if operation_type in ["insert", "update"]:
                query = await self._aadd_returning_clause(query, operation_type)

            async with self.async_engine.connect() as connection:
                if operation_type in ["insert", "update", "delete"]:
                    transaction = await connection.begin()
                    try:
                        result = (
                            await connection.execute(text(query), params)
                            if params
                            else await connection.execute(text(query))
                        )
                        await transaction.commit()
                    except Exception:
                        await transaction.rollback()
                        raise
                else:
                    result = (
                        await connection.execute(text(query), params)
                        if params
                        else await connection.execute(text(query))
                    )

                if operation_type == "select" or result.returns_rows:
                    rows = self._build_rows(result)
                    affected_rows = (
                        len(rows)
                        if operation_type in ["insert", "update"] and rows
                        else result.rowcount if result.rowcount >= 0 else len(rows)
                    )
                    return {
                        "success": True,
                        "data": rows,
                        "affected_rows": affected_rows,
                        "operation_type": operation_type,
                    }

                affected_rows = result.rowcount if result.rowcount >= 0 else 0
                if operation_type == "insert" and result.rowcount == -1:
                    affected_rows = 1

                return {
                    "success": True,
                    "data": [],
                    "affected_rows": affected_rows,
                    "operation_type": operation_type,
                }
        except SQLAlchemyError as exc:
            error_message = self._normalize_sql_error(str(exc))
            logger.error("Async SQL execution failed: %s", error_message)
            return {
                "success": False,
                "error": error_message,
                "operation_type": self._detect_operation_type(query),
            }

    def get_table_names(self, schema: Optional[str] = None) -> List[str]:
        """List the table names for an optional schema."""
        inspector = inspect(self.engine)
        return sorted(inspector.get_table_names(schema=schema))

    async def aget_table_names(self, schema: Optional[str] = None) -> List[str]:
        """List table names through the native async SQLAlchemy engine."""
        async with self.async_engine.connect() as connection:
            return await connection.run_sync(
                lambda sync_connection: sorted(
                    inspect(sync_connection).get_table_names(schema=schema)
                )
            )

    def get_table_schema(
        self,
        table_name: str,
        schema: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return schema metadata for a single table."""
        return self._inspect_table_schema(self.engine, table_name, schema)

    def get_database_schema(self) -> Dict[str, Any]:
        """Return schema metadata for all non-system schemas."""
        inspector = inspect(self.engine)
        schemas = [
            schema_name
            for schema_name in inspector.get_schema_names()
            if schema_name not in {"information_schema", "pg_catalog"}
        ]
        database_schema = {"database_name": self.engine.url.database, "tables": {}}

        for schema_name in sorted(schemas):
            for table_name in self.get_table_names(schema=schema_name):
                qualified_name = f"{schema_name}.{table_name}"
                database_schema["tables"][qualified_name] = self.get_table_schema(
                    table_name,
                    schema=schema_name,
                )

        return database_schema

    async def aget_database_schema(self) -> Dict[str, Any]:
        """Return database schema through the native async SQLAlchemy engine."""
        async with self.async_engine.connect() as connection:
            return await connection.run_sync(self._inspect_database_schema)

    async def aclose(self) -> None:
        """Dispose of the engines cleanly during app shutdown."""
        await self.async_engine.dispose()
        if self._sync_engine is not None:
            self._sync_engine.dispose()

    def _detect_operation_type(self, query: str) -> str:
        """Classify the SQL statement type from the raw query text."""
        query_lower = query.strip().lower()
        if query_lower.startswith("select"):
            return "select"
        if query_lower.startswith("insert"):
            return "insert"
        if query_lower.startswith("update"):
            return "update"
        if query_lower.startswith("delete"):
            return "delete"
        return "other"

    def _add_returning_clause(self, query: str, operation_type: str) -> str:
        """Append a PostgreSQL RETURNING clause when writes omit one."""
        if "returning" in query.lower():
            return query

        table_name = None
        if operation_type == "insert":
            match = re.search(r"insert\s+into\s+(\w+)", query.lower())
            if match:
                table_name = match.group(1)
        elif operation_type == "update":
            match = re.search(r"update\s+(\w+)", query.lower())
            if match:
                table_name = match.group(1)

        if not table_name:
            return query

        try:
            inspector = inspect(self.engine)
            primary_keys = inspector.get_pk_constraint(table_name).get(
                "constrained_columns",
                [],
            )
            returning_columns = ", ".join(primary_keys) if primary_keys else "*"
            return f"{query.rstrip(';')} RETURNING {returning_columns}"
        except Exception as exc:
            logger.warning(
                "Could not determine RETURNING clause for table %s: %s",
                table_name,
                exc,
            )
            return f"{query.rstrip(';')} RETURNING *"

    async def _aadd_returning_clause(self, query: str, operation_type: str) -> str:
        """Append a RETURNING clause, resolving primary keys from a cache."""
        if "returning" in query.lower():
            return query

        table_name = self._extract_write_table(query, operation_type)
        if not table_name:
            return query

        primary_keys = await self._aget_primary_keys(table_name)
        returning_columns = ", ".join(primary_keys) if primary_keys else "*"
        return f"{query.rstrip(';')} RETURNING {returning_columns}"

    async def _aget_primary_keys(self, table_name: str) -> List[str]:
        """Return a table's primary-key columns, caching successful lookups.

        Without the cache every INSERT/UPDATE would open a fresh connection to
        re-inspect the same table. Transient failures are not cached so a later
        write can retry; an empty list maps to ``RETURNING *`` at the call site.
        """
        cached = self._pk_cache.get(table_name)
        if cached is not None:
            return cached

        try:
            async with self.async_engine.connect() as connection:
                primary_keys = await connection.run_sync(
                    lambda sync_connection: inspect(sync_connection)
                    .get_pk_constraint(table_name)
                    .get("constrained_columns", [])
                )
        except Exception as exc:
            logger.warning(
                "Could not determine async RETURNING clause for table %s: %s",
                table_name,
                exc,
            )
            return []

        self._pk_cache[table_name] = primary_keys
        return primary_keys

    @staticmethod
    def _extract_write_table(query: str, operation_type: str) -> Optional[str]:
        """Extract the target table name from an INSERT or UPDATE statement."""
        if operation_type == "insert":
            match = re.search(r"insert\s+into\s+(\w+)", query.lower())
        elif operation_type == "update":
            match = re.search(r"update\s+(\w+)", query.lower())
        else:
            match = None
        return match.group(1) if match else None

    def _normalize_sql_error(self, error_message: str) -> str:
        """Map low-level SQL errors to friendlier application messages."""
        lowered = error_message.lower()
        if "duplicate key" in lowered:
            return "Cannot insert duplicate record - this entry already exists."
        if "foreign key" in lowered:
            return "Cannot complete operation - referenced record does not exist."
        if "not null" in lowered:
            return "Missing required field(s) - please provide all necessary information."
        return error_message

    @staticmethod
    def _build_async_connection_string(connection_string: str) -> str:
        """Normalize PostgreSQL URLs so SQLAlchemy can create an async engine."""
        if connection_string.startswith("postgresql+psycopg://"):
            return connection_string
        if connection_string.startswith("postgresql://"):
            return connection_string.replace("postgresql://", "postgresql+psycopg://", 1)
        return connection_string

    @staticmethod
    def _inspect_table_schema(
        sync_connection: Any,
        table_name: str,
        schema: Optional[str],
    ) -> Dict[str, Any]:
        """Build table schema details from a synchronous connection context."""
        inspector = inspect(sync_connection)
        columns = inspector.get_columns(table_name, schema=schema)
        primary_keys = inspector.get_pk_constraint(table_name, schema=schema)
        foreign_keys = inspector.get_foreign_keys(table_name, schema=schema)
        indexes = inspector.get_indexes(table_name, schema=schema)

        return {
            "schema": schema or inspector.default_schema_name,
            "table_name": table_name,
            "columns": [
                {
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": column.get("nullable", True),
                    "default": str(column.get("default", "")),
                }
                for column in columns
            ],
            "primary_keys": primary_keys.get("constrained_columns", []),
            "foreign_keys": [
                {
                    "constrained_columns": foreign_key["constrained_columns"],
                    "referred_schema": foreign_key.get("referred_schema"),
                    "referred_table": foreign_key["referred_table"],
                    "referred_columns": foreign_key["referred_columns"],
                }
                for foreign_key in foreign_keys
            ],
            "indices": indexes,
        }

    def _inspect_database_schema(self, sync_connection: Any) -> Dict[str, Any]:
        """Build database schema details from a synchronous connection context.

        Uses SQLAlchemy 2.0 bulk reflection (``get_multi_*``) so each metadata
        kind costs one round-trip per schema instead of one per table. For a
        large database this turns O(tables) round-trips into O(schemas).
        """
        inspector = inspect(sync_connection)
        schemas = [
            schema_name
            for schema_name in inspector.get_schema_names()
            if schema_name not in {"information_schema", "pg_catalog"}
        ]
        database_schema = {"database_name": sync_connection.engine.url.database, "tables": {}}

        for schema_name in sorted(schemas):
            columns_by_table = inspector.get_multi_columns(schema=schema_name)
            pk_by_table = inspector.get_multi_pk_constraint(schema=schema_name)
            fks_by_table = inspector.get_multi_foreign_keys(schema=schema_name)
            indexes_by_table = inspector.get_multi_indexes(schema=schema_name)

            for table_key in sorted(columns_by_table.keys()):
                table_name = table_key[1]
                qualified_name = f"{schema_name}.{table_name}"
                database_schema["tables"][qualified_name] = self._assemble_table_schema(
                    schema_name,
                    table_name,
                    columns_by_table.get(table_key, []),
                    pk_by_table.get(table_key, {}),
                    fks_by_table.get(table_key, []),
                    indexes_by_table.get(table_key, []),
                )

        return database_schema

    @staticmethod
    def _assemble_table_schema(
        schema_name: str,
        table_name: str,
        columns: List[Dict[str, Any]],
        pk_constraint: Dict[str, Any],
        foreign_keys: List[Dict[str, Any]],
        indexes: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
        """Shape pre-fetched bulk-reflection data like ``_inspect_table_schema``."""
        return {
            "schema": schema_name,
            "table_name": table_name,
            "columns": [
                {
                    "name": column["name"],
                    "type": str(column["type"]),
                    "nullable": column.get("nullable", True),
                    "default": str(column.get("default", "")),
                }
                for column in columns
            ],
            "primary_keys": pk_constraint.get("constrained_columns", []) if pk_constraint else [],
            "foreign_keys": [
                {
                    "constrained_columns": foreign_key["constrained_columns"],
                    "referred_schema": foreign_key.get("referred_schema"),
                    "referred_table": foreign_key["referred_table"],
                    "referred_columns": foreign_key["referred_columns"],
                }
                for foreign_key in foreign_keys
            ],
            "indices": indexes,
        }
