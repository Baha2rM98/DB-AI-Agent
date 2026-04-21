"""Query endpoints for the database agent."""

from typing import List

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_query_service
from app.api.schemas.query import QueryRequest, QueryResponse
from app.application.services.query_service import QueryService

router = APIRouter(tags=["query"])


@router.post("/query", response_model=QueryResponse)
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


@router.get("/sessions", response_model=List[str])
def get_active_sessions(
    query_service: QueryService = Depends(get_query_service),
) -> List[str]:
    """Return the active thread identifiers during the compatibility period."""
    return query_service.get_active_threads()


@router.get("/sessions/{session_id}")
def get_session_info(
    session_id: str,
    query_service: QueryService = Depends(get_query_service),
) -> dict:
    """Return session metadata while legacy session endpoints still exist."""
    session_info = query_service.get_thread_info(session_id)
    if "error" in session_info:
        raise HTTPException(status_code=404, detail=session_info["error"])
    return session_info


@router.delete("/sessions/{session_id}")
def clear_session(
    session_id: str,
    query_service: QueryService = Depends(get_query_service),
) -> dict:
    """Delete a legacy session by identifier."""
    if not query_service.clear_thread(session_id):
        raise HTTPException(status_code=404, detail=f"Session {session_id} not found")
    return {"message": f"Session {session_id} cleared successfully"}
