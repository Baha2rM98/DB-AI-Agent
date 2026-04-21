"""Compatibility adapter that wraps the current legacy agent connector."""

from typing import Any, Dict

from app.agent.db_agent_connector import DBAgentConnector


class LegacyDBAgent:
    """Expose the legacy connector through the new agent port shape."""

    def __init__(self, connection_string: str) -> None:
        """Create the wrapped legacy connector."""
        self._connector = DBAgentConnector(connection_string)

    def execute_query(self, query: str, thread_id: str) -> Dict[str, Any]:
        """Run a query through the legacy connector."""
        return self._connector.execute_natural_language_query(
            query,
            session_id=thread_id,
        )

    def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return thread metadata from the legacy session store."""
        return self._connector.get_session_info(thread_id)

    def get_active_threads(self) -> list[str]:
        """Return the active thread identifiers tracked by the legacy connector."""
        return self._connector.get_active_sessions()

    def clear_thread(self, thread_id: str) -> bool:
        """Delete a thread from the legacy connector."""
        return self._connector.clear_session(thread_id)
