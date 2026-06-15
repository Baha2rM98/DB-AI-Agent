"""Class-based LangGraph agent for natural-language database requests.

The agent is structured so it can grow: each graph node is a method on
``SqlAgent`` and the workflow (nodes + edges) is wired and compiled once in the
constructor. Today the graph is a single ``generate_sql`` step (earlier versions
chained four sequential LLM calls; collapsing to one cut per-query latency and
token cost ~4x), but adding a node is now a matter of writing a method and an
edge rather than rewriting a builder function.

Scope boundary: this class owns the *graph* only. It accepts a checkpointer but
knows nothing about how it is created or persisted - that lifecycle lives in
``app.integrations.persistent_agent.PersistentLangGraphAgent``.

Heavy LangChain/LangGraph imports are deferred into the constructor so importing
this module does not pull the full LLM stack until an agent is actually built.
"""

import logging
from typing import Any, Dict, Optional

from app.agent.prompts import SYSTEM_MESSAGE, USER_PROMPT_TEMPLATE, summarize_schema
from app.agent.states import AgentState, SqlGeneration

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-1.5-flash"


class SqlAgent:
    """Compile and run the SQL-generation LangGraph workflow.

    Construction is the expensive step (LLM client + graph compilation), so a
    single instance should be built once and reused across requests. Pass
    ``compiled_graph`` to inject a pre-built graph (used by tests) and skip the
    LLM/graph construction entirely.
    """

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        checkpointer: Optional[Any] = None,
        *,
        compiled_graph: Optional[Any] = None,
    ) -> None:
        """Build the LLM chain and compile the workflow graph once."""
        if compiled_graph is not None:
            self._chain = None
            self._graph = compiled_graph
            return

        from langchain_core.prompts import ChatPromptTemplate
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langgraph.graph import END, StateGraph

        llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", SYSTEM_MESSAGE),
                ("user", USER_PROMPT_TEMPLATE),
            ]
        )
        self._chain = prompt | llm.with_structured_output(SqlGeneration)

        workflow = StateGraph(AgentState)
        workflow.add_node("generate_sql", self.generate_sql)
        workflow.set_entry_point("generate_sql")
        workflow.add_edge("generate_sql", END)
        self._graph = workflow.compile(checkpointer=checkpointer)

    async def generate_sql(self, state: AgentState) -> AgentState:
        """Node: translate the user's request into SQL in a single LLM call."""
        try:
            result = await self._chain.ainvoke(
                {
                    "schema": summarize_schema(state.database_info),
                    "query": state.query,
                }
            )
            state.sql_query = (getattr(result, "sql_query", "") or "").strip()
            state.response = getattr(result, "explanation", "") or ""
        except Exception as exc:
            logger.error("SQL generation failed: %s", exc)
            state.error = str(exc)
            state.response = f"I could not process your request: {exc}"
        return state

    async def run(
        self,
        query: str,
        context_schema: Dict[str, Any],
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Invoke the compiled graph and normalize its output for the service layer."""
        database_info = {
            "database_name": context_schema.get("database_name", "unknown"),
            "tables": context_schema.get("tables", {}),
        }

        try:
            initial_state = AgentState(query=query, database_info=database_info)
            invoke_config = {"configurable": {"thread_id": thread_id}} if thread_id else None
            result = await self._graph.ainvoke(initial_state, config=invoke_config)
            return self._normalize_result(result)
        except Exception as exc:
            logger.error("Error running SQL agent: %s", exc)
            if logger.isEnabledFor(logging.DEBUG):
                import traceback

                logger.debug("SqlAgent.run traceback: %s", traceback.format_exc())
            return {
                "response": f"Error processing query: {exc}",
                "agent_response": f"Error processing query: {exc}",
                "sql_query": "",
                "context": {"error": str(exc)},
                "execution_details": {},
                "error": str(exc),
            }

    @staticmethod
    def _normalize_result(result: Any) -> Dict[str, Any]:
        """Shape a finished graph state into the dict the service layer expects."""
        if isinstance(result, dict):
            sql_query = result.get("sql_query", "") or ""
            response = result.get("response", "") or ""
            error = result.get("error", "") or ""
        else:
            sql_query = getattr(result, "sql_query", "") or ""
            response = getattr(result, "response", "") or ""
            error = getattr(result, "error", "") or ""

        return {
            "response": response,
            "agent_response": response,
            "sql_query": sql_query,
            "context": {"sql_query": sql_query, "error": error},
            "execution_details": {},
            "error": error,
        }
