"""Thread metadata storage for the temporary compatibility API surface.

LangGraph owns durable conversational state. This registry only keeps the
small amount of API-facing metadata we still expose while thread management is
being finalized.

Note: this store is in-process, so metadata is not shared across multiple
workers/replicas. A future revision should back it with a shared store (e.g.
Redis) or derive the metadata from the LangGraph checkpoint store directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Optional


def _now() -> datetime:
    """Return the current time as a timezone-aware UTC datetime."""
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ThreadRecord:
    """Store lightweight metadata for a single thread."""

    thread_id: str
    created_at: datetime = field(default_factory=_now)
    last_activity: datetime = field(default_factory=_now)
    query_count: int = 0
    last_operation: Optional[str] = None


class ThreadRegistry:
    """Track API-facing metadata for active conversation threads."""

    def __init__(self) -> None:
        """Initialize an empty in-memory registry."""
        self._threads: Dict[str, ThreadRecord] = {}

    def record_activity(self, thread_id: str, last_operation: Optional[str]) -> None:
        """Create or update metadata for a thread after a query attempt."""
        record = self._threads.setdefault(thread_id, ThreadRecord(thread_id=thread_id))
        record.last_activity = _now()
        record.query_count += 1
        record.last_operation = last_operation

    def get(self, thread_id: str) -> Optional[ThreadRecord]:
        """Return a thread record when the thread is known."""
        return self._threads.get(thread_id)

    def list_ids(self) -> list[str]:
        """Return active thread identifiers in deterministic order."""
        return sorted(self._threads.keys())

    def clear(self, thread_id: str) -> bool:
        """Remove a thread record if it exists."""
        if thread_id not in self._threads:
            return False
        del self._threads[thread_id]
        return True
