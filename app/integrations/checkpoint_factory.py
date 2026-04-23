"""Factories for creating LangGraph checkpoint savers."""

from __future__ import annotations

from typing import Any

from app.integrations.settings import Settings


async def create_checkpointer(settings: Settings) -> tuple[Any, Any | None]:
    """Create the configured LangGraph checkpointer implementation.

    The factory keeps imports local so optional checkpoint backends only need
    to be installed when they are actually selected by configuration.
    """
    backend = settings.checkpointer_backend.lower()

    if backend == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver(), None

    if backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver
        except ImportError as exc:  # pragma: no cover - depends on optional deps.
            raise RuntimeError(
                "SQLite checkpointing requires the 'langgraph-checkpoint-sqlite' and 'aiosqlite' packages."
            ) from exc

        sqlite_path = settings.checkpointer_sqlite_path
        return await _materialize_async_saver(AsyncSqliteSaver.from_conn_string(sqlite_path))

    if backend == "postgres":
        try:
            from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
        except ImportError as exc:  # pragma: no cover - depends on optional deps.
            raise RuntimeError(
                "Postgres checkpointing requires the 'langgraph-checkpoint-postgres' package."
            ) from exc

        if not settings.checkpointer_database_url:
            raise RuntimeError(
                "CHECKPOINTER_DATABASE_URL must be set when CHECKPOINTER_BACKEND=postgres."
            )

        return await _materialize_async_saver(
            AsyncPostgresSaver.from_conn_string(settings.checkpointer_database_url)
        )

    raise RuntimeError(f"Unsupported checkpointer backend: {settings.checkpointer_backend}")


async def _materialize_async_saver(candidate: Any) -> tuple[Any, Any | None]:
    """Enter async saver context managers and keep them alive for app lifetime.

    LangGraph async saver factories return async context managers in current
    versions. The API layer needs a concrete saver instance, so this helper
    enters the context and returns both the saver and the manager so the caller
    can close it cleanly at shutdown.
    """
    if hasattr(candidate, "__aenter__") and hasattr(candidate, "__aexit__"):
        context_manager = candidate
        saver = await context_manager.__aenter__()
        if hasattr(saver, "setup"):
            await saver.setup()
        return saver, context_manager

    if hasattr(candidate, "setup"):
        await candidate.setup()
    return candidate, None
