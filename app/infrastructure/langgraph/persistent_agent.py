"""LangGraph-backed agent implementation with persistent thread support."""

from __future__ import annotations

from typing import Any, Dict

from app.agent.langgraph_agent import query_database
from app.application.services.schema_service import SchemaService
from app.infrastructure.config.settings import Settings
from app.infrastructure.langgraph.checkpoint_factory import create_checkpointer
from app.infrastructure.langgraph.thread_registry import ThreadRegistry


class PersistentLangGraphAgent:
    """Run database requests through a LangGraph workflow with persistence."""

    def __init__(self, settings: Settings, schema_service: SchemaService) -> None:
        """Create the configured persistent agent and its compatibility state."""
        self._settings = settings
        self._schema_service = schema_service
        self._checkpointer = create_checkpointer(settings)
        self._thread_registry = ThreadRegistry()

    def execute_query(self, query: str, thread_id: str) -> Dict[str, Any]:
        """Execute a natural-language query using a persisted LangGraph thread."""
        schema = self._schema_service.get_database_schema()
        result = query_database(
            query=query,
            context_schema=schema,
            thread_id=thread_id,
            checkpointer=self._checkpointer,
            model_name=self._settings.llm_model,
        )
        self._thread_registry.record_activity(thread_id, self._extract_operation(result))
        return result

    def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return compatibility metadata for a persisted thread."""
        record = self._thread_registry.get(thread_id)
        if record is None:
            return {"error": f"Session {thread_id} not found"}

        return {
            "thread_id": record.thread_id,
            "session_id": record.thread_id,
            "created_at": record.created_at.isoformat(),
            "last_activity": record.last_activity.isoformat(),
            "query_count": record.query_count,
            "last_table": None,
            "last_operation": record.last_operation,
            "context_summary": (
                f"Persistent LangGraph thread: {record.thread_id} | "
                f"Queries handled: {record.query_count}"
            ),
        }

    def get_active_threads(self) -> list[str]:
        """Return the known thread identifiers seen by this app instance."""
        return self._thread_registry.list_ids()

    def clear_thread(self, thread_id: str) -> bool:
        """Forget compatibility metadata for a thread.

        This does not currently delete checkpoints from the backing saver. That
        will be handled in a later cleanup round once we add saver-specific
        thread management utilities.
        """
        return self._thread_registry.clear(thread_id)

    @staticmethod
    def _extract_operation(result: Dict[str, Any]) -> str | None:
        """Infer the SQL operation from the result payload."""
        sql_query = result.get("sql_query", "")
        if not sql_query:
            return None

        lowered = sql_query.strip().lower()
        if lowered.startswith("select"):
            return "select"
        if lowered.startswith("insert"):
            return "insert"
        if lowered.startswith("update"):
            return "update"
        if lowered.startswith("delete"):
            return "delete"
        return None
