import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.agent.prompts import summarize_schema
from app.agent.sql_agent import SqlAgent
from app.agent.states import AgentState


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


class TestSqlAgentConstruction:
    """The agent should compile from a single SQL-generation node."""

    @patch("langchain_google_genai.ChatGoogleGenerativeAI")
    def test_constructor_builds_structured_single_call(self, mock_gemini):
        mock_llm = Mock()
        mock_gemini.return_value = mock_llm

        agent = SqlAgent(model_name="gemini-1.5-flash")

        assert agent is not None
        mock_gemini.assert_called_once_with(model="gemini-1.5-flash", temperature=0)
        mock_llm.with_structured_output.assert_called_once()


class TestSqlAgentRun:
    """SqlAgent.run normalizes graph output for the service layer."""

    @pytest.mark.anyio
    async def test_uses_injected_graph(self):
        graph = Mock()
        graph.ainvoke = AsyncMock(
            return_value={"sql_query": "SELECT 1", "response": "ok", "error": ""}
        )

        agent = SqlAgent(compiled_graph=graph)
        result = await agent.run("q", {"tables": {}}, thread_id="t")

        assert result["sql_query"] == "SELECT 1"
        assert result["agent_response"] == "ok"
        assert result["response"] == "ok"
        graph.ainvoke.assert_awaited_once()

    @pytest.mark.anyio
    async def test_normalizes_agent_state_object(self):
        graph = Mock()
        graph.ainvoke = AsyncMock(
            return_value=AgentState(query="q", sql_query="SELECT 3", response="done")
        )

        agent = SqlAgent(compiled_graph=graph)
        result = await agent.run("q", {"tables": {}})

        assert result["sql_query"] == "SELECT 3"
        assert result["agent_response"] == "done"

    @pytest.mark.anyio
    async def test_handles_unexpected_result_type_gracefully(self):
        graph = Mock()
        graph.ainvoke = AsyncMock(return_value="unexpected string")

        agent = SqlAgent(compiled_graph=graph)
        result = await agent.run("q", {"tables": {}})

        assert isinstance(result, dict)
        assert result["sql_query"] == ""
        assert result["agent_response"] == ""

    @pytest.mark.anyio
    async def test_exception_is_reported_without_sql(self):
        graph = Mock()
        graph.ainvoke = AsyncMock(side_effect=Exception("boom"))

        agent = SqlAgent(compiled_graph=graph)
        result = await agent.run("q", {"tables": {}})

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

        agent = SqlAgent(compiled_graph=graph)
        start_time = time.time()
        for index in range(10):
            result = await agent.run(f"query {index}", {"tables": {}})
            assert result["sql_query"] == "SELECT 1"
        assert (time.time() - start_time) < 5.0
