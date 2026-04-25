"""Main query orchestration service and normalized result model.

This module keeps the application's central use case in one place: accept a
natural-language request, hand it to the agent, and normalize the response for
the API layer.
"""

from inspect import isawaitable
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol

from app.services.schema_service import SchemaService
from app.services.sql_safety import SqlSafetyPolicy


class AgentClient(Protocol):
    """Describe the agent behavior required by the service layer."""

    async def execute_query(self, query: str, thread_id: str) -> Dict[str, Any]:
        """Run a natural-language query for a given thread."""

    async def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return metadata about a conversation thread."""

    async def get_active_threads(self) -> list[str]:
        """List active conversation thread identifiers."""

    async def clear_thread(self, thread_id: str) -> bool:
        """Delete a conversation thread if it exists."""

    async def record_thread_activity(self, thread_id: str, operation: str | None) -> None:
        """Record non-agent thread activity for deterministic service responses."""


class TargetDatabaseClient(Protocol):
    """Describe target database operations used by the query service."""

    async def aexecute_query(
        self,
        query: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Execute a SQL query asynchronously and return a normalized result."""


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
    sql_query: Optional[str] = None
    operation_type: Optional[str] = None
    error: Optional[str] = None


class QueryService:
    """Coordinate agent execution, schema access, and response shaping."""

    def __init__(
        self,
        agent: AgentClient,
        database_gateway: TargetDatabaseClient,
        schema_service: SchemaService,
        allow_writes: bool = False,
        allow_deletes: bool = False,
    ) -> None:
        """Store the dependencies required to serve query requests."""
        self._agent = agent
        self._target_database_gateway = database_gateway
        self._schema_service = schema_service
        self._sql_safety = SqlSafetyPolicy(
            allow_writes=allow_writes,
            allow_deletes=allow_deletes,
        )

    async def execute_query(self, query: str, thread_id: str) -> QueryResult:
        """Execute a natural-language query and normalize the result payload."""
        schema_result = await self._try_handle_schema_query(query=query, thread_id=thread_id)
        if schema_result is not None:
            return schema_result

        agent_result = await self._agent.execute_query(query=query, thread_id=thread_id)
        context_info = await self._build_context_info(thread_id)
        agent_response = self._extract_agent_response(agent_result)
        sql_query = self._extract_sql_query(agent_result)

        if not sql_query:
            message = agent_response or "The agent did not generate an executable SQL query."
            return QueryResult(
                success=False,
                message=message,
                agent_response=agent_response,
                thread_id=thread_id,
                context_info=context_info,
                error="No executable SQL query was generated.",
            )

        validation = self._sql_safety.validate(sql_query)
        if not validation.allowed:
            return QueryResult(
                success=False,
                message=validation.reason,
                agent_response=agent_response,
                thread_id=thread_id,
                context_info=context_info,
                sql_query=sql_query,
                operation_type=validation.operation_type,
                error=validation.reason,
            )

        execution_result = await self._target_database_gateway.aexecute_query(sql_query)
        execution_success = execution_result.get("success", False)
        message = (
            agent_response
            if execution_success and agent_response
            else execution_result.get("error", "Query executed successfully.")
        )

        return QueryResult(
            success=execution_success,
            message=message,
            agent_response=agent_response,
            data=execution_result.get("data"),
            affected_rows=execution_result.get("affected_rows"),
            thread_id=thread_id,
            context_info=context_info,
            sql_query=sql_query,
            operation_type=execution_result.get("operation_type", validation.operation_type),
            error=execution_result.get("error"),
        )

    async def get_active_threads(self) -> list[str]:
        """Return the active conversation threads known by the agent."""
        return await self._agent.get_active_threads()

    async def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return metadata for a single conversation thread."""
        return await self._agent.get_thread_info(thread_id)

    async def clear_thread(self, thread_id: str) -> bool:
        """Delete a conversation thread through the backing agent."""
        return await self._agent.clear_thread(thread_id)

    async def _build_context_info(self, thread_id: str) -> Dict[str, Any]:
        """Fetch contextual information for the current conversation thread."""
        thread_info = await self._agent.get_thread_info(thread_id)
        return thread_info if thread_info.get("thread_id") else {}

    @staticmethod
    def _extract_agent_response(result: Dict[str, Any]) -> str:
        """Extract the natural-language agent response from known result shapes."""
        response = result.get("agent_response") or result.get("response")
        if response:
            return response

        execution_details = result.get("execution_details")
        if isinstance(execution_details, dict) and execution_details.get("response"):
            return execution_details["response"]

        return ""

    @staticmethod
    def _extract_sql_query(result: Dict[str, Any]) -> Optional[str]:
        """Extract SQL from top-level, context, or execution detail payloads."""
        sql_query = result.get("sql_query")
        if sql_query:
            return sql_query

        context = result.get("context")
        if isinstance(context, dict) and context.get("sql_query"):
            return context["sql_query"]

        execution_details = result.get("execution_details")
        if isinstance(execution_details, dict) and execution_details.get("sql_query"):
            return execution_details["sql_query"]

        return None

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
                context_info=await self._build_context_info(thread_id),
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
                context_info=await self._build_context_info(thread_id),
            )

        return None

    async def aclose(self) -> None:
        """Close async resources held by downstream integrations when available."""
        database_close_hook = getattr(self._target_database_gateway, "aclose", None)
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
        await self._agent.record_thread_activity(thread_id, operation)
