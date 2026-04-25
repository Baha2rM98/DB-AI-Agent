"""LangGraph-backed agent implementation with persistent thread support."""

from __future__ import annotations

import asyncio
from typing import Any, Dict

from app.agent.langgraph_agent import query_database
from app.integrations.checkpoint_factory import create_checkpointer
from app.integrations.settings import Settings
from app.integrations.thread_registry import ThreadRegistry
from app.services.schema_service import SchemaService


class PersistentLangGraphAgent:
    """Run database requests through a LangGraph workflow with persistence."""

    def __init__(self, settings: Settings, schema_service: SchemaService) -> None:
        """Create the configured persistent agent and its compatibility state."""
        self._settings = settings
        self._schema_service = schema_service
        self._checkpointer: Any | None = None
        self._checkpointer_context: Any | None = None
        self._checkpointer_lock = asyncio.Lock()
        self._thread_registry = ThreadRegistry()

    async def execute_query(self, query: str, thread_id: str) -> Dict[str, Any]:
        """Execute a natural-language query using a persisted LangGraph thread."""
        schema = await self._schema_service.get_database_schema()
        checkpointer = await self._get_checkpointer()
        result = await query_database(
            query=query,
            context_schema=schema,
            thread_id=thread_id,
            checkpointer=checkpointer,
            model_name=self._settings.llm_model,
        )
        await self.record_thread_activity(thread_id, self._extract_operation(result))
        return result

    async def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return metadata for a persisted thread."""
        record = self._thread_registry.get(thread_id)
        if record is None:
            return {"error": f"Thread {thread_id} not found"}

        return {
            "thread_id": record.thread_id,
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

    async def get_active_threads(self) -> list[str]:
        """Return the known thread identifiers seen by this app instance."""
        return self._thread_registry.list_ids()

    async def clear_thread(self, thread_id: str) -> bool:
        """Forget metadata for a thread.

        This does not currently delete checkpoints from the backing saver. That
        will be handled in a later cleanup round once we add saver-specific
        thread management utilities.
        """
        return self._thread_registry.clear(thread_id)

    async def record_thread_activity(self, thread_id: str, operation: str | None) -> None:
        """Record deterministic service-side activity for a thread."""
        self._thread_registry.record_activity(thread_id, operation)

    async def aclose(self) -> None:
        """Close async checkpoint resources when the app shuts down."""
        if self._checkpointer_context is not None:
            await self._checkpointer_context.__aexit__(None, None, None)
            self._checkpointer_context = None
            self._checkpointer = None

    async def _get_checkpointer(self) -> Any:
        """Initialize the async checkpointer lazily for the app lifetime."""
        if self._checkpointer is not None:
            return self._checkpointer

        async with self._checkpointer_lock:
            if self._checkpointer is None:
                self._checkpointer, self._checkpointer_context = await create_checkpointer(
                    self._settings
                )
        return self._checkpointer

    @staticmethod
    def _extract_operation(result: Dict[str, Any]) -> str | None:
        """Infer the SQL operation from the result payload."""
        sql_query = result.get("sql_query", "")
        if not sql_query and isinstance(result.get("context"), dict):
            sql_query = result["context"].get("sql_query", "")
        if not sql_query and isinstance(result.get("execution_details"), dict):
            sql_query = result["execution_details"].get("sql_query", "")
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
