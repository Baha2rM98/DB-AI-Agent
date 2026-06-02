"""Application bootstrap and FastAPI app factory."""

from contextlib import asynccontextmanager

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.gzip import GZipMiddleware

from app.api.dependencies import get_query_service
from app.api.routes import router as api_router
from app.integrations.settings import Settings
from app.logging_config import configure_logging

load_dotenv()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Manage long-lived async resources for the application."""
    yield
    await get_query_service().aclose()
    log_listener = getattr(app.state, "log_listener", None)
    if log_listener is not None:
        log_listener.stop()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application instance."""
    settings = Settings.from_env()

    log_listener = configure_logging(level=settings.log_level)

    app = FastAPI(
        title=settings.app_name,
        description="API for natural language database interactions using LangGraph.",
        version=settings.app_version,
        lifespan=lifespan,
    )
    app.state.log_listener = log_listener
    app.add_middleware(GZipMiddleware, minimum_size=1024)
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
