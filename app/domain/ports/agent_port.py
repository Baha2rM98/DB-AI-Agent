"""Abstraction for the query agent used by the application layer."""

from typing import Any, Dict, Protocol


class AgentPort(Protocol):
    """Define the behavior required from a query-capable agent."""

    def execute_query(self, query: str, thread_id: str) -> Dict[str, Any]:
        """Run a natural-language query for a given thread."""

    def get_thread_info(self, thread_id: str) -> Dict[str, Any]:
        """Return metadata about a conversation thread."""

    def get_active_threads(self) -> list[str]:
        """List active conversation thread identifiers."""

    def clear_thread(self, thread_id: str) -> bool:
        """Delete a conversation thread if it exists."""
