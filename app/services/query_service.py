"""Main query orchestration service and normalized result model.

This module keeps the application's central use case in one place: accept a
natural-language request, hand it to the agent, and normalize the response for
the API layer.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from app.services.schema_service import SchemaService


class AgentClient(Protocol):
    """Describe the agent behavior required by the service layer."""

    def execute_query(self, query: str, thread_id: str) -> Dict[str, Any]:
        """Run a natural-language query for a given thread."""

    def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return metadata about a conversation thread."""

    def get_active_threads(self) -> list[str]:
        """List active conversation thread identifiers."""

    def clear_thread(self, thread_id: str) -> bool:
        """Delete a conversation thread if it exists."""


class DatabaseClient(Protocol):
    """Describe the database operations required by the service layer."""

    def test_connection(self) -> bool:
        """Verify that the configured database is reachable."""

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
        """Return schema information for a single table."""

    def get_database_schema(self) -> Dict[str, Any]:
        """Return schema information for the full database."""


@dataclass(slots=True)
class QueryResult:
    """Normalized query result returned by the service layer."""

    success: bool
    message: str
    agent_response: str
    thread_id: str
    data: Optional[List[Dict[str, Any]]] = None
    affected_rows: Optional[int] = None
    context_info: Dict[str, Any] = field(default_factory=dict)


class QueryService:
    """Coordinate agent execution, schema access, and response shaping."""

    def __init__(
        self,
        agent: AgentClient,
        database_gateway: DatabaseClient,
        schema_service: SchemaService,
    ) -> None:
        """Store the dependencies required to serve query requests."""
        self._agent = agent
        self._database_gateway = database_gateway
        self._schema_service = schema_service

    def execute_query(self, query: str, thread_id: str) -> QueryResult:
        """Execute a natural-language query and normalize the result payload."""
        result = self._agent.execute_query(query=query, thread_id=thread_id)
        context_info = self._build_context_info(thread_id)
        agent_response = result.get("agent_response") or result.get("response", "")
        message = result.get("message") or agent_response

        return QueryResult(
            success=result.get("success", False),
            message=message,
            agent_response=agent_response,
            data=result.get("data"),
            affected_rows=result.get("affected_rows"),
            thread_id=thread_id,
            context_info=context_info,
        )

    def get_health_snapshot(self) -> Dict[str, Any]:
        """Expose a small application snapshot useful for diagnostics."""
        schema = self._schema_service.get_database_schema()
        return {
            "database_connection": self._database_gateway.test_connection(),
            "table_count": len(schema.get("tables", {})),
        }

    def get_active_threads(self) -> list[str]:
        """Return the active conversation threads known by the agent."""
        return self._agent.get_active_threads()

    def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return metadata for a single conversation thread."""
        return self._agent.get_thread_info(thread_id)

    def clear_thread(self, thread_id: str) -> bool:
        """Delete a conversation thread through the backing agent."""
        return self._agent.clear_thread(thread_id)

    def _build_context_info(self, thread_id: str) -> Dict[str, Any]:
        """Fetch contextual information for the current conversation thread."""
        thread_info = self._agent.get_thread_info(thread_id)
        return thread_info if thread_info.get("thread_id") else {}
