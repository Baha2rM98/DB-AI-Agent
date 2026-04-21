"""Application-layer DTOs for query execution."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass(slots=True)
class QueryResultDTO:
    """Normalized query result returned by the application service."""

    success: bool
    message: str
    agent_response: str
    thread_id: str
    data: Optional[List[Dict[str, Any]]] = None
    affected_rows: Optional[int] = None
    context_info: Dict[str, Any] = field(default_factory=dict)
