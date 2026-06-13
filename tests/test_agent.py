import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.agent.langgraph_agent import (
    AgentState,
    initialize_agent,
    query_database,
    summarize_schema,
)


class TestAgentState:
    """Test cases for the AgentState model."""

    def test_agent_state_defaults(self):
        """AgentState should default every field but the query."""
        state = AgentState(query="test query")

        assert state.query == "test query"
        assert state.database_info == {}
        assert state.sql_query == ""
        assert state.response == ""
        assert state.error == ""

    def test_agent_state_with_values(self):
        """AgentState should accept explicit values."""
        state = AgentState(
            query="test query",
            database_info={"tables": {"actor": {}}},
            sql_query="SELECT 1",
            response="done",
        )

        assert state.database_info == {"tables": {"actor": {}}}
        assert state.sql_query == "SELECT 1"
        assert state.response == "done"


class TestSummarizeSchema:
    """The prompt schema summary should be compact but informative."""

    def test_summary_includes_columns_pks_and_fks(self):
        info = {
            "tables": {
                "public.rental": {
                    "columns": [
                        {"name": "rental_id", "type": "INTEGER"},
                        {"name": "customer_id", "type": "INTEGER"},
                    ],
                    "primary_keys": ["rental_id"],
                    "foreign_keys": [
                        {
                            "constrained_columns": ["customer_id"],
                            "referred_table": "customer",
                            "referred_columns": ["customer_id"],
                        }
                    ],
                }
            }
        }

        summary = summarize_schema(info)

        assert "public.rental" in summary
        assert "rental_id INTEGER" in summary
        assert "PK(rental_id)" in summary
        assert "customer_id->customer(customer_id)" in summary

    def test_summary_handles_empty_schema(self):
        assert summarize_schema({"tables": {}}) == "(no tables found)"


class TestInitializeAgent:
    """The agent should compile from a single SQL-generation node."""

    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    def test_initialize_agent_builds_structured_single_call(self, mock_gemini):
        mock_llm = Mock()
        mock_gemini.return_value = mock_llm

        agent = initialize_agent(model_name="gemini-1.5-flash")

        assert agent is not None
        mock_gemini.assert_called_once_with(model="gemini-1.5-flash", temperature=0)
        mock_llm.with_structured_output.assert_called_once()


class TestQueryDatabase:
    """query_database normalizes graph output for the service layer."""

    @pytest.mark.anyio
    async def test_uses_provided_graph_without_compiling(self):
        graph = Mock()
        graph.ainvoke = AsyncMock(
            return_value={"sql_query": "SELECT 1", "response": "ok", "error": ""}
        )

        result = await query_database("q", {"tables": {}}, thread_id="t", graph=graph)

        assert result["sql_query"] == "SELECT 1"
        assert result["agent_response"] == "ok"
        assert result["response"] == "ok"
        graph.ainvoke.assert_awaited_once()

    @pytest.mark.anyio
    @patch("app.agent.langgraph_agent.initialize_agent")
    async def test_compiles_a_graph_when_none_provided(self, mock_init):
        graph = Mock()
        graph.ainvoke = AsyncMock(return_value={"sql_query": "SELECT 2", "response": "ok"})
        mock_init.return_value = graph

        result = await query_database("q", {"tables": {}})

        mock_init.assert_called_once()
        assert result["sql_query"] == "SELECT 2"

    @pytest.mark.anyio
    async def test_normalizes_agent_state_object(self):
        graph = Mock()
        graph.ainvoke = AsyncMock(
            return_value=AgentState(query="q", sql_query="SELECT 3", response="done")
        )

        result = await query_database("q", {"tables": {}}, graph=graph)

        assert result["sql_query"] == "SELECT 3"
        assert result["agent_response"] == "done"

    @pytest.mark.anyio
    async def test_handles_unexpected_result_type_gracefully(self):
        graph = Mock()
        graph.ainvoke = AsyncMock(return_value="unexpected string")

        result = await query_database("q", {"tables": {}}, graph=graph)

        assert isinstance(result, dict)
        assert result["sql_query"] == ""
        assert result["agent_response"] == ""

    @pytest.mark.anyio
    async def test_exception_is_reported_without_sql(self):
        graph = Mock()
        graph.ainvoke = AsyncMock(side_effect=Exception("boom"))

        result = await query_database("q", {"tables": {}}, graph=graph)

        assert result["sql_query"] == ""
        assert "boom" in result["agent_response"]
        assert result["context"]["error"] == "boom"


@pytest.mark.slow
class TestAgentPerformance:
    """Lightweight repeated-invocation checks against a mocked graph."""

    @pytest.mark.anyio
    async def test_repeated_invocation(self):
        graph = Mock()
        graph.ainvoke = AsyncMock(return_value={"sql_query": "SELECT 1", "response": "ok"})

        start_time = time.time()
        for index in range(10):
            result = await query_database(f"query {index}", {"tables": {}}, graph=graph)
            assert result["sql_query"] == "SELECT 1"
        assert (time.time() - start_time) < 5.0
