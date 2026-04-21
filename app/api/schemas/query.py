"""Request and response models for query endpoints."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class QueryRequest(BaseModel):
    """HTTP request body for natural-language database queries."""

    query: str
    thread_id: Optional[str] = None
    session_id: Optional[str] = None

    @property
    def effective_thread_id(self) -> str:
        """Resolve the canonical thread identifier from supported inputs."""
        return self.thread_id or self.session_id or "default"


class QueryResponse(BaseModel):
    """HTTP response body for query execution results."""

    success: bool
    message: str
    agent_response: str
    data: Optional[List[Dict[str, Any]]] = None
    affected_rows: Optional[int] = None
    thread_id: Optional[str] = None
    session_id: Optional[str] = None
    context_info: Optional[Dict[str, Any]] = None


class ThreadInfoResponse(BaseModel):
    """Compatibility response model for thread and legacy session metadata."""

    thread_id: str
    session_id: Optional[str] = None
    created_at: str
    last_activity: str
    query_count: int
    last_table: Optional[str] = None
    last_operation: Optional[str] = None
    context_summary: str
