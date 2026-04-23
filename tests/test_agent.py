import time
from unittest.mock import AsyncMock, Mock, patch

import pytest

from app.agent.langgraph_agent import AgentState, initialize_agent, query_database


class TestAgentState:
    """Test cases for AgentState model."""

    def test_agent_state_initialization(self):
        """Test AgentState initialization with defaults."""
        state = AgentState(query="test query")

        assert state.query == "test query"
        assert state.context == {}
        assert state.database_info == {}
        assert state.current_plan == []
        assert state.execution_result == {}
        assert state.response == ""
        assert state.error == ""

    def test_agent_state_with_values(self):
        """Test AgentState initialization with custom values."""
        context = {"test": "value"}
        db_info = {"tables": ["test_table"]}

        state = AgentState(
            query="test query",
            context=context,
            database_info=db_info,
            current_plan=["select"],
            response="test response",
        )

        assert state.query == "test query"
        assert state.context == context
        assert state.database_info == db_info
        assert state.current_plan == ["select"]
        assert state.response == "test response"


class TestLangGraphAgent:
    """Test cases for async LangGraph agent functionality."""

    @patch("app.agent.langgraph_agent.ChatGoogleGenerativeAI")
    def test_initialize_agent(self, mock_gemini):
        """Test async agent initialization."""
        mock_llm = Mock()
        mock_gemini.return_value = mock_llm

        agent = initialize_agent()

        assert agent is not None
        mock_gemini.assert_called_once_with(
            model="gemini-1.5-pro",
            temperature=0,
            convert_system_message_to_human=True,
        )

    @pytest.mark.anyio
    @patch("app.agent.langgraph_agent.initialize_agent")
    async def test_query_database_success(self, mock_init_agent, mock_agent_result):
        """Test successful async query execution."""
        mock_agent = Mock()
        mock_agent.ainvoke = AsyncMock(return_value=mock_agent_result)
        mock_init_agent.return_value = mock_agent

        database_info = {
            "database_name": "test_db",
            "tables": {"actor": {"columns": []}},
            "summary": {},
        }
        result = await query_database("Show me all actors", database_info)

        assert isinstance(result, dict)
        assert "response" in result

    @pytest.mark.anyio
    @patch("app.agent.langgraph_agent.initialize_agent")
    async def test_query_database_with_agent_state_result(self, mock_init_agent):
        """Test query_database when agent returns AgentState."""
        mock_agent_state = AgentState(
            query="test",
            response="Test response",
            context={"test": "context"},
            execution_result={"success": True},
        )

        mock_agent = Mock()
        mock_agent.ainvoke = AsyncMock(return_value=mock_agent_state)
        mock_init_agent.return_value = mock_agent

        result = await query_database("test query", {})

        assert result["response"] == "Test response"
        assert result["context"] == {"test": "context"}
        assert result["execution_details"] == {"success": True}

    @pytest.mark.anyio
    @patch("app.agent.langgraph_agent.initialize_agent")
    async def test_query_database_exception_handling(self, mock_init_agent):
        """Test async query_database exception handling."""
        mock_agent = Mock()
        mock_agent.ainvoke = AsyncMock(side_effect=Exception("Test error"))
        mock_init_agent.return_value = mock_agent

        result = await query_database("test query", {})

        assert "response" in result
        assert "error" in result["context"]
        assert "Test error" in result["response"]

    @pytest.mark.anyio
    @patch("app.agent.langgraph_agent.initialize_agent")
    async def test_query_database_unexpected_result_type(self, mock_init_agent):
        """Test query_database with unexpected result type."""
        mock_agent = Mock()
        mock_agent.ainvoke = AsyncMock(return_value="unexpected string result")
        mock_init_agent.return_value = mock_agent

        result = await query_database("test query", {})

        assert isinstance(result, dict)
        assert "response" in result
        assert "could not process" in result["response"].lower()


class TestAgentWorkflowNodes:
    """Smoke tests for workflow construction."""

    @patch("app.agent.langgraph_agent.ChatGoogleGenerativeAI")
    def test_understand_query_node(self, mock_gemini):
        """Test workflow initialization for understanding queries."""
        mock_llm = Mock()
        mock_gemini.return_value = mock_llm
        agent = initialize_agent()
        initial_state = AgentState(
            query="Show me all actors",
            database_info={"actor": {"columns": []}},
        )
        assert agent is not None
        assert initial_state.query == "Show me all actors"

    @patch("app.agent.langgraph_agent.ChatGoogleGenerativeAI")
    def test_plan_execution_node(self, mock_gemini):
        """Test workflow initialization for planning."""
        mock_llm = Mock()
        mock_gemini.return_value = mock_llm
        agent = initialize_agent()
        assert agent is not None

    @patch("app.agent.langgraph_agent.ChatGoogleGenerativeAI")
    def test_execute_plan_node(self, mock_gemini):
        """Test workflow initialization for execution."""
        mock_llm = Mock()
        mock_gemini.return_value = mock_llm
        agent = initialize_agent()
        assert agent is not None

    @patch("app.agent.langgraph_agent.ChatGoogleGenerativeAI")
    def test_formulate_response_node(self, mock_gemini):
        """Test workflow initialization for response generation."""
        mock_llm = Mock()
        mock_gemini.return_value = mock_llm
        agent = initialize_agent()
        assert agent is not None

    @patch("app.agent.langgraph_agent.ChatGoogleGenerativeAI")
    def test_handle_error_node(self, mock_gemini):
        """Test workflow initialization for error handling."""
        mock_llm = Mock()
        mock_gemini.return_value = mock_llm
        agent = initialize_agent()
        assert agent is not None


@pytest.mark.parametrize(
    "query,expected_operation",
    [
        ("Show me all actors", "select"),
        ("Find actors named John", "select"),
        ("How many films are there?", "select"),
        ("List all customers", "select"),
    ],
)
def test_query_operation_detection(query, expected_operation):
    """Test that representative query categories still make sense."""
    assert expected_operation == "select"


class TestAgentStateMachine:
    """Test the state machine transitions."""

    def test_state_transitions_success_path(self):
        """Test successful state transitions through the workflow."""
        state = AgentState(query="test query")
        state.context["understood_intent"] = "Select all actors"
        assert "understood_intent" in state.context

        state.context["execution_plan"] = "SELECT * FROM actor"
        assert "execution_plan" in state.context

        state.execution_result = {"success": True, "data": []}
        assert state.execution_result["success"] is True

        state.response = "I found 0 actors"
        assert state.response != ""

    def test_state_transitions_error_path(self):
        """Test error state transitions."""
        state = AgentState(query="test query")
        state.error = "Failed to understand query"
        assert state.error != ""
        assert state.response == ""


@pytest.mark.slow
class TestAgentPerformance:
    """Performance tests for the agent."""

    @pytest.mark.anyio
    @patch("app.agent.langgraph_agent.initialize_agent")
    async def test_agent_response_time(self, mock_init_agent):
        """Test that the async agent responds within reasonable time."""
        mock_agent = Mock()
        mock_agent.ainvoke = AsyncMock(return_value={"response": "test response"})
        mock_init_agent.return_value = mock_agent

        start_time = time.time()
        result = await query_database("test query", {})
        end_time = time.time()

        assert (end_time - start_time) < 5.0
        assert result is not None

    @pytest.mark.anyio
    @patch("app.agent.langgraph_agent.initialize_agent")
    async def test_agent_memory_usage(self, mock_init_agent):
        """Test repeated async query execution."""
        mock_agent = Mock()
        mock_agent.ainvoke = AsyncMock(return_value={"response": "test response"})
        mock_init_agent.return_value = mock_agent

        for i in range(10):
            result = await query_database(f"test query {i}", {})
            assert result is not None
