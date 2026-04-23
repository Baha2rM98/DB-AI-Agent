"""API routes for the simplified application structure."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_database_gateway, get_query_service
from app.api.schemas import (
    HealthResponse,
    QueryRequest,
    QueryResponse,
    RootResponse,
    ThreadInfoResponse,
)
from app.integrations.database import SQLAlchemyDatabaseGateway
from app.services.query_service import QueryService

router = APIRouter()


@router.get("/", response_model=RootResponse, tags=["health"])
def read_root() -> RootResponse:
    """Return basic application metadata."""
    return RootResponse(
        name="LangGraph Database Agent API",
        version="1.0.0",
        description="Natural language interface for database operations.",
    )


@router.get("/db_connection", response_model=HealthResponse, tags=["health"])
def health_check(
    database_gateway: SQLAlchemyDatabaseGateway = Depends(get_database_gateway),
    query_service: QueryService = Depends(get_query_service),
) -> HealthResponse:
    """Verify database connectivity for the running application."""
    if not database_gateway.test_connection():
        raise HTTPException(status_code=503, detail="Database connection failed")

    return HealthResponse(
        status="connected",
        database_connection="ok",
        active_sessions=len(query_service.get_active_threads()),
    )


@router.post("/query", response_model=QueryResponse, tags=["query"])
def process_query(
    request: QueryRequest,
    query_service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    """Process a natural-language query through the application service."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    result = query_service.execute_query(
        query=request.query,
        thread_id=request.effective_thread_id,
    )

    return QueryResponse(
        success=result.success,
        message=result.message,
        agent_response=result.agent_response,
        data=result.data,
        affected_rows=result.affected_rows,
        thread_id=result.thread_id,
        session_id=result.thread_id,
        context_info=result.context_info,
    )


@router.get("/sessions", response_model=List[str], tags=["query"])
def get_active_sessions(
    query_service: QueryService = Depends(get_query_service),
) -> List[str]:
    """Return active legacy session identifiers.

    This endpoint is kept for backward compatibility and mirrors `/threads`.
    """
    return query_service.get_active_threads()


@router.get("/sessions/{session_id}", response_model=ThreadInfoResponse, tags=["query"])
def get_session_info(
    session_id: str,
    query_service: QueryService = Depends(get_query_service),
) -> ThreadInfoResponse:
    """Return legacy session metadata.

    This endpoint is kept for backward compatibility and mirrors `/threads/{thread_id}`.
    """
    session_info = query_service.get_thread_info(session_id)
    if "error" in session_info:
        raise HTTPException(status_code=404, detail=session_info["error"])
    return _build_thread_response(session_info)


@router.delete("/sessions/{session_id}", tags=["query"])
def clear_session(
    session_id: str,
    query_service: QueryService = Depends(get_query_service),
) -> dict:
    """Delete a legacy session by identifier."""
    if not query_service.clear_thread(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"message": f"Session {session_id} cleared successfully"}


@router.get("/threads", response_model=List[str], tags=["query"])
def get_active_threads(
    query_service: QueryService = Depends(get_query_service),
) -> List[str]:
    """Return the active conversation thread identifiers."""
    return query_service.get_active_threads()


@router.get("/threads/{thread_id}", response_model=ThreadInfoResponse, tags=["query"])
def get_thread_info(
    thread_id: str,
    query_service: QueryService = Depends(get_query_service),
) -> ThreadInfoResponse:
    """Return metadata for a persisted conversation thread."""
    thread_info = query_service.get_thread_info(thread_id)
    if "error" in thread_info:
        raise HTTPException(status_code=404, detail=thread_info["error"])
    return _build_thread_response(thread_info)


@router.delete("/threads/{thread_id}", tags=["query"])
def clear_thread(
    thread_id: str,
    query_service: QueryService = Depends(get_query_service),
) -> dict:
    """Delete metadata for a conversation thread."""
    if not query_service.clear_thread(thread_id):
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return {"message": f"Thread {thread_id} cleared successfully"}


def _build_thread_response(thread_info: dict) -> ThreadInfoResponse:
    """Normalize thread metadata for both thread and session endpoints."""
    return ThreadInfoResponse(
        thread_id=thread_info.get("thread_id", thread_info["session_id"]),
        session_id=thread_info.get("session_id", thread_info.get("thread_id")),
        created_at=thread_info["created_at"],
        last_activity=thread_info["last_activity"],
        query_count=thread_info["query_count"],
        last_table=thread_info.get("last_table"),
        last_operation=thread_info.get("last_operation"),
        context_summary=thread_info["context_summary"],
    )
