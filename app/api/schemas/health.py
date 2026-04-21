"""Response models for health endpoints."""

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
    active_sessions: int = 0
