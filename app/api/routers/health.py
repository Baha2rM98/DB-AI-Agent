"""Health and metadata endpoints."""

from fastapi import APIRouter, Depends, HTTPException

from app.api.dependencies import get_database_gateway, get_query_service
from app.api.schemas.health import HealthResponse, RootResponse
from app.application.services.query_service import QueryService
from app.domain.ports.database_port import DatabasePort

router = APIRouter(tags=["health"])


@router.get("/", response_model=RootResponse)
def read_root() -> RootResponse:
    """Return basic application metadata."""
    return RootResponse(
        name="LangGraph Database Agent API",
        version="1.0.0",
        description="Natural language interface for database operations.",
    )


@router.get("/db_connection", response_model=HealthResponse)
def health_check(
    database_gateway: DatabasePort = Depends(get_database_gateway),
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
