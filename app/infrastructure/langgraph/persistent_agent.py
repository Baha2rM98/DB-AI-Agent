"""LangGraph-backed agent implementation with persistent thread support."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict

from app.agent.langgraph_agent import query_database
from app.application.services.schema_service import SchemaService
from app.infrastructure.config.settings import Settings
from app.infrastructure.langgraph.checkpoint_factory import create_checkpointer


@dataclass(slots=True)
class ThreadMetadata:
    """Compatibility metadata for legacy session-style endpoints.

    LangGraph persistence owns the actual conversational state. This metadata
    exists only to keep the current `/sessions` endpoints usable while the API
    transitions toward thread-first contracts.
    """

    thread_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    last_activity: datetime = field(default_factory=datetime.utcnow)
    query_count: int = 0
    last_operation: str | None = None


class PersistentLangGraphAgent:
    """Run database requests through a LangGraph workflow with persistence."""

    def __init__(self, settings: Settings, schema_service: SchemaService) -> None:
        """Create the configured persistent agent and its compatibility state."""
        self._settings = settings
        self._schema_service = schema_service
        self._checkpointer = create_checkpointer(settings)
        self._thread_metadata: dict[str, ThreadMetadata] = {}

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
        self._record_thread_activity(thread_id, result)
        return result

    def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return compatibility metadata for a persisted thread."""
        metadata = self._thread_metadata.get(thread_id)
        if metadata is None:
            return {"error": f"Session {thread_id} not found"}

        return {
            "session_id": metadata.thread_id,
            "created_at": metadata.created_at.isoformat(),
            "last_activity": metadata.last_activity.isoformat(),
            "query_count": metadata.query_count,
            "last_table": None,
            "last_operation": metadata.last_operation,
            "context_summary": (
                f"Persistent LangGraph thread: {metadata.thread_id} | "
                f"Queries handled: {metadata.query_count}"
            ),
        }

    def get_active_threads(self) -> list[str]:
        """Return the known thread identifiers seen by this app instance."""
        return sorted(self._thread_metadata.keys())

    def clear_thread(self, thread_id: str) -> bool:
        """Forget compatibility metadata for a thread.

        This does not currently delete checkpoints from the backing saver. That
        will be handled in a later cleanup round once we add saver-specific
        thread management utilities.
        """
        if thread_id not in self._thread_metadata:
            return False

        del self._thread_metadata[thread_id]
        return True

    def _record_thread_activity(self, thread_id: str, result: Dict[str, Any]) -> None:
        """Track minimal metadata needed by the temporary compatibility endpoints."""
        metadata = self._thread_metadata.setdefault(thread_id, ThreadMetadata(thread_id=thread_id))
        metadata.last_activity = datetime.utcnow()
        metadata.query_count += 1
        metadata.last_operation = self._extract_operation(result)

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
