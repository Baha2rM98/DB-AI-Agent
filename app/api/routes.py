"""API routes for the simplified application structure."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_query_service
from app.api.schemas import (
    HealthzResponse,
    QueryRequest,
    QueryResponse,
    RootResponse,
    ThreadInfoResponse,
)
from app.services.query_service import QueryService

router = APIRouter()


@router.get("/", response_model=RootResponse, tags=["health"])
async def read_root() -> RootResponse:
    """Return basic application metadata."""
    return RootResponse(
        name="LangGraph Database Agent API",
        version="1.0.0",
        description="Natural language interface for database operations.",
    )


@router.get("/healthz", response_model=HealthzResponse, tags=["health"])
async def healthz() -> HealthzResponse:
    """Return a lightweight liveness signal for container health checks."""
    return HealthzResponse(status="ok")


@router.post("/query", response_model=QueryResponse, tags=["query"])
async def process_query(
    request: QueryRequest,
    query_service: QueryService = Depends(get_query_service),
) -> QueryResponse:
    """Process a natural-language query through the application service."""
    if not request.query.strip():
        raise HTTPException(status_code=400, detail="Query cannot be empty")

    result = await query_service.execute_query(
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
        context_info=result.context_info,
        sql_query=result.sql_query,
        operation_type=result.operation_type,
        error=result.error,
    )


@router.get("/threads", response_model=list[str], tags=["query"])
async def get_active_threads(
    query_service: QueryService = Depends(get_query_service),
) -> list[str]:
    """Return the active conversation thread identifiers."""
    return await query_service.get_active_threads()


@router.get("/threads/{thread_id}", response_model=ThreadInfoResponse, tags=["query"])
async def get_thread_info(
    thread_id: str,
    query_service: QueryService = Depends(get_query_service),
) -> ThreadInfoResponse:
    """Return metadata for a persisted conversation thread."""
    thread_info = await query_service.get_thread_info(thread_id)
    if "error" in thread_info:
        raise HTTPException(status_code=404, detail=thread_info["error"])
    return _build_thread_response(thread_info)


@router.delete("/threads/{thread_id}", tags=["query"])
async def clear_thread(
    thread_id: str,
    query_service: QueryService = Depends(get_query_service),
) -> dict:
    """Delete metadata for a conversation thread."""
    if not await query_service.clear_thread(thread_id):
        raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
    return {"message": f"Thread {thread_id} cleared successfully"}


def _build_thread_response(thread_info: dict) -> ThreadInfoResponse:
    """Normalize thread metadata for the API response."""
    return ThreadInfoResponse(
        thread_id=thread_info["thread_id"],
        created_at=thread_info["created_at"],
        last_activity=thread_info["last_activity"],
        query_count=thread_info["query_count"],
        last_table=thread_info.get("last_table"),
        last_operation=thread_info.get("last_operation"),
        context_summary=thread_info["context_summary"],
    )
