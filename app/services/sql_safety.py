"""Safety checks for SQL generated from natural-language requests."""

from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class SqlValidationResult:
    """Result of validating a generated SQL statement."""

    allowed: bool
    operation_type: str
    reason: str = ""


class SqlSafetyPolicy:
    """Validate generated SQL before it can touch the target database."""

    def __init__(self, allow_writes: bool = False, allow_deletes: bool = False) -> None:
        """Store the configured target database write policy."""
        self._allow_writes = allow_writes
        self._allow_deletes = allow_deletes

    def validate(self, sql_query: str) -> SqlValidationResult:
        """Return whether a SQL statement is allowed to execute."""
        stripped_query = sql_query.strip()
        operation_type = detect_operation_type(stripped_query)

        if not stripped_query:
            return SqlValidationResult(False, operation_type, "No SQL query was generated.")

        if has_multiple_statements(stripped_query):
            return SqlValidationResult(
                False,
                operation_type,
                "Generated SQL contains multiple statements, which is not allowed.",
            )

        if operation_type == "select":
            return SqlValidationResult(True, operation_type)

        if operation_type in {"insert", "update"}:
            if self._allow_writes:
                return SqlValidationResult(True, operation_type)
            return SqlValidationResult(
                False,
                operation_type,
                "Target database writes are disabled by configuration.",
            )

        if operation_type == "delete":
            if self._allow_writes and self._allow_deletes:
                return SqlValidationResult(True, operation_type)
            return SqlValidationResult(
                False,
                operation_type,
                "Target database deletes are disabled by configuration.",
            )

        return SqlValidationResult(
            False,
            operation_type,
            f"SQL operation '{operation_type}' is not allowed.",
        )


def detect_operation_type(sql_query: str) -> str:
    """Classify the leading SQL operation."""
    match = re.match(r"^\s*([a-zA-Z]+)", sql_query)
    return match.group(1).lower() if match else "unknown"


def has_multiple_statements(sql_query: str) -> bool:
    """Return whether a query contains more than one semicolon-delimited statement."""
    statements = [part.strip() for part in sql_query.split(";") if part.strip()]
    return len(statements) > 1
