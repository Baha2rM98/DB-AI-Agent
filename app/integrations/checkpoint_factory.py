"""Factories for creating LangGraph checkpoint savers."""

from __future__ import annotations

from typing import Any

from app.integrations.settings import Settings


def create_checkpointer(settings: Settings) -> Any:
    """Create the configured LangGraph checkpointer implementation.

    The factory keeps imports local so optional checkpoint backends only need
    to be installed when they are actually selected by configuration.
    """
    backend = settings.checkpointer_backend.lower()

    if backend == "memory":
        from langgraph.checkpoint.memory import InMemorySaver

        return InMemorySaver()

    if backend == "sqlite":
        try:
            from langgraph.checkpoint.sqlite import SqliteSaver
        except ImportError as exc:  # pragma: no cover - depends on optional deps.
            raise RuntimeError(
                "SQLite checkpointing requires the 'langgraph-checkpoint-sqlite' package."
            ) from exc

        sqlite_path = settings.checkpointer_sqlite_path
        saver = _materialize_saver(SqliteSaver.from_conn_string(sqlite_path))
        if hasattr(saver, "setup"):
            saver.setup()
        return saver

    if backend == "postgres":
        try:
            from langgraph.checkpoint.postgres import PostgresSaver
        except ImportError as exc:  # pragma: no cover - depends on optional deps.
            raise RuntimeError(
                "Postgres checkpointing requires the 'langgraph-checkpoint-postgres' package."
            ) from exc

        if not settings.checkpointer_database_url:
            raise RuntimeError(
                "CHECKPOINTER_DATABASE_URL must be set when CHECKPOINTER_BACKEND=postgres."
            )

        saver = _materialize_saver(
            PostgresSaver.from_conn_string(settings.checkpointer_database_url)
        )
        if hasattr(saver, "setup"):
            saver.setup()
        return saver

    raise RuntimeError(f"Unsupported checkpointer backend: {settings.checkpointer_backend}")


def _materialize_saver(candidate: Any) -> Any:
    """Enter saver context managers and keep them alive for app lifetime.

    LangGraph saver factories such as `PostgresSaver.from_conn_string()` return
    generator-backed context managers in current versions. The API layer needs a
    concrete saver instance, so this helper enters the context and stores the
    manager on the resulting saver object to prevent premature cleanup.
    """
    if hasattr(candidate, "__enter__") and hasattr(candidate, "__exit__"):
        context_manager = candidate
        saver = context_manager.__enter__()
        setattr(saver, "_managed_context", context_manager)
        return saver
    return candidate
