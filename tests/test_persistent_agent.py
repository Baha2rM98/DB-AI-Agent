from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.integrations.persistent_agent import PersistentLangGraphAgent


@pytest.mark.anyio
@patch("app.integrations.persistent_agent.create_checkpointer")
@patch("app.agent.sql_agent.SqlAgent")
async def test_agent_is_built_once_and_reused(mock_sql_agent_cls, mock_create_checkpointer):
    """The SqlAgent should be built lazily once and shared across queries."""
    mock_create_checkpointer.return_value = (Mock(), None)

    mock_agent = Mock()
    mock_agent.run = AsyncMock(
        return_value={"sql_query": "SELECT 1", "response": "ok", "error": ""}
    )
    mock_sql_agent_cls.return_value = mock_agent

    mock_schema_service = Mock()
    mock_schema_service.get_database_schema = AsyncMock(return_value={"tables": {}})

    settings = Mock(llm_model="gemini-1.5-flash")
    agent = PersistentLangGraphAgent(settings=settings, schema_service=mock_schema_service)

    first = await agent.execute_query("show actors", "thread-1")
    second = await agent.execute_query("show films", "thread-2")

    assert first["sql_query"] == "SELECT 1"
    assert second["sql_query"] == "SELECT 1"
    # Agent + checkpointer built exactly once; only run repeats.
    mock_sql_agent_cls.assert_called_once()
    mock_create_checkpointer.assert_awaited_once()
    assert mock_agent.run.await_count == 2


@pytest.mark.anyio
@patch("app.integrations.persistent_agent.create_checkpointer")
@patch("app.agent.sql_agent.SqlAgent")
async def test_thread_activity_is_recorded(mock_sql_agent_cls, mock_create_checkpointer):
    """Executing a query should register the thread and infer its operation."""
    mock_create_checkpointer.return_value = (Mock(), None)
    mock_agent = Mock()
    mock_agent.run = AsyncMock(
        return_value={"sql_query": "SELECT * FROM actor", "response": "ok"}
    )
    mock_sql_agent_cls.return_value = mock_agent

    mock_schema_service = Mock()
    mock_schema_service.get_database_schema = AsyncMock(return_value={"tables": {}})

    settings = Mock(llm_model="gemini-1.5-flash")
    agent = PersistentLangGraphAgent(settings=settings, schema_service=mock_schema_service)

    await agent.execute_query("show actors", "thread-1")
    info = await agent.get_thread_info("thread-1")

    assert info["thread_id"] == "thread-1"
    assert info["query_count"] == 1
    assert info["last_operation"] == "select"
