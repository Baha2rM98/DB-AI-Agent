"""HTTP request and response models for the simplified API layer."""

from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class RootResponse(BaseModel):
    """Root metadata returned by the service."""

    name: str
    version: str
    description: str


class HealthResponse(BaseModel):
    """Health-check response describing database connectivity."""

    status: str
    database_connection: str
    active_threads: int = 0


class QueryRequest(BaseModel):
    """HTTP request body for natural-language database queries."""

    query: str
    thread_id: Optional[str] = None

    @property
    def effective_thread_id(self) -> str:
        """Resolve the canonical thread identifier from supported inputs."""
        return self.thread_id or "default"


class QueryResponse(BaseModel):
    """HTTP response body for query execution results."""

    success: bool
    message: str
    agent_response: str
    data: Optional[List[Dict[str, Any]]] = None
    affected_rows: Optional[int] = None
    thread_id: Optional[str] = None
    context_info: Optional[Dict[str, Any]] = None
    sql_query: Optional[str] = None
    operation_type: Optional[str] = None
    error: Optional[str] = None


class ThreadInfoResponse(BaseModel):
    """Response model for persisted conversation thread metadata."""

    thread_id: str
    created_at: str
    last_activity: str
    query_count: int
    last_table: Optional[str] = None
    last_operation: Optional[str] = None
    context_summary: str
