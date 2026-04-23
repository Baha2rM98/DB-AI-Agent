"""Main query orchestration service and normalized result model.

This module keeps the application's central use case in one place: accept a
natural-language request, hand it to the agent, and normalize the response for
the API layer.
"""

from inspect import isawaitable
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from app.services.schema_service import SchemaService


class AgentClient(Protocol):
    """Describe the agent behavior required by the service layer."""

    async def execute_query(self, query: str, thread_id: str) -> Dict[str, Any]:
        """Run a natural-language query for a given thread."""

    def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return metadata about a conversation thread."""

    def get_active_threads(self) -> list[str]:
        """List active conversation thread identifiers."""

    def clear_thread(self, thread_id: str) -> bool:
        """Delete a conversation thread if it exists."""

    def record_thread_activity(self, thread_id: str, operation: str | None) -> None:
        """Record non-agent thread activity for deterministic service responses."""


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

    async def atest_connection(self) -> bool:
        """Verify that the configured database is reachable asynchronously."""


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

    async def execute_query(self, query: str, thread_id: str) -> QueryResult:
        """Execute a natural-language query and normalize the result payload."""
        schema_result = await self._try_handle_schema_query(query=query, thread_id=thread_id)
        if schema_result is not None:
            return schema_result

        result = await self._agent.execute_query(query=query, thread_id=thread_id)
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

    async def get_health_snapshot(self) -> Dict[str, Any]:
        """Expose a small application snapshot useful for diagnostics."""
        schema = await self._schema_service.get_database_schema()
        return {
            "database_connection": await self._database_gateway.atest_connection(),
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

    async def _try_handle_schema_query(self, query: str, thread_id: str) -> QueryResult | None:
        """Answer simple schema questions directly without invoking the LLM."""
        schema_query = await self._schema_service.detect_schema_query(query)
        if schema_query is None:
            return None

        if schema_query.operation == "list_tables":
            tables = await self._schema_service.list_tables()
            await self._record_thread_activity(thread_id, "schema_list")
            message = f"I found {len(tables)} tables in the database."
            return QueryResult(
                success=True,
                message=message,
                agent_response=message,
                data=[{"table_name": table_name} for table_name in tables],
                affected_rows=len(tables),
                thread_id=thread_id,
                context_info=self._build_context_info(thread_id),
            )

        if schema_query.operation == "describe_table" and schema_query.table_name:
            table_details = await self._schema_service.get_table_details(schema_query.table_name)
            if table_details is None:
                return None

            await self._record_thread_activity(thread_id, "schema_describe")
            columns = table_details.get("columns", [])
            message = (
                f"I found the schema for table '{schema_query.table_name}' "
                f"with {len(columns)} columns."
            )
            return QueryResult(
                success=True,
                message=message,
                agent_response=message,
                data=[table_details],
                affected_rows=len(columns),
                thread_id=thread_id,
                context_info=self._build_context_info(thread_id),
            )

        return None

    async def aclose(self) -> None:
        """Close async resources held by downstream integrations when available."""
        database_close_hook = getattr(self._database_gateway, "aclose", None)
        if database_close_hook is not None:
            result = database_close_hook()
            if isawaitable(result):
                await result

        close_hook = getattr(self._agent, "aclose", None)
        if close_hook is None:
            return

        result = close_hook()
        if isawaitable(result):
            await result

    async def _record_thread_activity(self, thread_id: str, operation: str | None) -> None:
        """Record deterministic service activity for the current thread."""
        result = self._agent.record_thread_activity(thread_id, operation)
        if isawaitable(result):
            await result
