"""Application bootstrap and FastAPI app factory."""

import logging
from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI

from app.api.dependencies import get_query_service
from app.api.routes import router as api_router
from app.integrations.settings import Settings

load_dotenv()


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Manage long-lived async resources for the application."""
    yield
    await get_query_service().aclose()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = Settings.from_env()

    logging.basicConfig(
        filename="app.log",
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    app = FastAPI(
        title=settings.app_name,
        description="API for natural language database interactions using LangGraph.",
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.include_router(api_router)
    return app


app = create_app()

if __name__ == "__main__":
    import uvicorn

    settings = Settings.from_env()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=True,
    )
