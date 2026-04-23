"""SQLAlchemy-backed database integration.

This module is the single place where the application talks directly to
SQLAlchemy for connectivity, raw query execution, and schema inspection.
"""

import logging
import re
from typing import Any, Dict, List, Optional

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.exc import SQLAlchemyError

logger = logging.getLogger(__name__)


class SQLAlchemyDatabaseGateway:
    """Execute SQL queries and inspect schemas through SQLAlchemy."""

    def __init__(self, connection_string: str) -> None:
        """Create a SQLAlchemy engine for the configured database."""
        self.connection_string = connection_string
        self.engine = create_engine(self.connection_string)

    def test_connection(self) -> bool:
        """Return whether the database accepts a simple probe query."""
        try:
            with self.engine.connect() as connection:
                connection.execute(text("SELECT 1"))
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
                    columns = result.keys()
                    rows = [dict(zip(columns, row)) for row in result.fetchall()]
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

    def get_table_names(self, schema: Optional[str] = None) -> List[str]:
        """List the table names for an optional schema."""
        inspector = inspect(self.engine)
        return sorted(inspector.get_table_names(schema=schema))

    def get_table_schema(
        self,
        table_name: str,
        schema: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Return schema metadata for a single table."""
        inspector = inspect(self.engine)
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
