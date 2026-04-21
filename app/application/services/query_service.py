"""Main orchestration service for database queries."""

from typing import Any, Dict

from app.application.dto.query_result import QueryResultDTO
from app.application.services.schema_service import SchemaService
from app.domain.ports.agent_port import AgentPort
from app.domain.ports.database_port import DatabasePort


class QueryService:
    """Coordinate agent execution, schema access, and response shaping."""

    def __init__(
        self,
        agent: AgentPort,
        database_gateway: DatabasePort,
        schema_service: SchemaService,
    ) -> None:
        """Store the dependencies required to serve query requests."""
        self._agent = agent
        self._database_gateway = database_gateway
        self._schema_service = schema_service

    def execute_query(self, query: str, thread_id: str) -> QueryResultDTO:
        """Execute a natural-language query and normalize the result payload."""
        result = self._agent.execute_query(query=query, thread_id=thread_id)
        context_info = self._build_context_info(thread_id)
        agent_response = result.get("agent_response") or result.get("response", "")
        message = result.get("message") or agent_response

        return QueryResultDTO(
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
        return thread_info if thread_info.get("thread_id") or thread_info.get("session_id") else {}
