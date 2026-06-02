"""Async LangGraph workflow for natural-language database requests.

The workflow is a single SQL-generation step. Earlier versions chained four
sequential LLM calls (understand -> plan -> execute -> formulate); collapsing
them to one call cuts per-query latency and token cost by roughly 4x while
producing the same artifact the service layer needs: a SQL statement plus a
short natural-language explanation.

Heavy LangChain/LangGraph imports are deferred into ``initialize_agent`` so
importing this module (and therefore booting the app) does not pull the full
stack until a graph is actually compiled.
"""

import logging
from typing import Any, Dict, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "gemini-1.5-flash"


class AgentState(BaseModel):
    """State passed through the (single-node) LangGraph workflow."""

    query: str
    database_info: Dict[str, Any] = Field(default_factory=dict)
    sql_query: str = ""
    response: str = ""
    error: str = ""


class SqlGeneration(BaseModel):
    """Structured output contract for the SQL-generation LLM call."""

    sql_query: str = Field(
        default="",
        description=(
            "A single, complete, executable SQL statement with no markdown "
            "fences. Empty if the request cannot be answered with SQL."
        ),
    )
    explanation: str = Field(
        default="",
        description="A concise natural-language description of the query, "
        "or the reason no query could be produced.",
    )


SYSTEM_MESSAGE = """You are an expert PostgreSQL assistant. Given a database schema and a user request, produce a single executable SQL statement that fulfils it.

Rules:
1. Output exactly one SQL statement, with no markdown code fences.
2. Only reference tables and columns that appear in the provided schema.
3. Prefer read-only SELECT statements unless the user clearly asks to modify data.
4. If the request cannot be answered with SQL against this schema, return an empty sql_query and explain why in the explanation.
"""


def summarize_schema(database_info: Dict[str, Any]) -> str:
    """Render a compact, token-efficient schema summary for the prompt.

    Only table names, column names/types, primary keys, and foreign-key links
    are included - enough for the model to write correct SQL without paying for
    the full inspector payload (defaults, index metadata, etc.) on every call.
    """
    tables = database_info.get("tables", {})
    if not tables:
        return "(no tables found)"

    lines = []
    for qualified_name in sorted(tables):
        details = tables[qualified_name]
        columns = details.get("columns", [])
        column_text = ", ".join(
            f"{column['name']} {column.get('type', '')}".strip() for column in columns
        )

        primary_keys = details.get("primary_keys", [])
        pk_text = f" PK({', '.join(primary_keys)})" if primary_keys else ""

        foreign_keys = details.get("foreign_keys", [])
        fk_text = ""
        if foreign_keys:
            parts = [
                f"{','.join(fk['constrained_columns'])}->"
                f"{fk['referred_table']}({','.join(fk['referred_columns'])})"
                for fk in foreign_keys
            ]
            fk_text = f" FK[{'; '.join(parts)}]"

        lines.append(f"{qualified_name}({column_text}){pk_text}{fk_text}")

    return "\n".join(lines)


def initialize_agent(
    checkpointer: Optional[Any] = None,
    model_name: str = DEFAULT_MODEL,
):
    """Build and compile the single-node async LangGraph workflow.

    This is the expensive call (LLM client construction + graph compilation),
    so callers should compile once and reuse the result across requests rather
    than rebuilding it per query.
    """
    from langchain_core.prompts import ChatPromptTemplate
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langgraph.graph import END, StateGraph

    llm = ChatGoogleGenerativeAI(model=model_name, temperature=0)
    structured_llm = llm.with_structured_output(SqlGeneration)

    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_MESSAGE),
            ("user", "Database schema:\n{schema}\n\nUser request: {query}"),
        ]
    )
    chain = prompt | structured_llm

    async def generate_sql(state: AgentState) -> AgentState:
        """Translate the user's request into SQL in a single LLM call."""
        try:
            result = await chain.ainvoke(
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

    workflow = StateGraph(AgentState)
    workflow.add_node("generate_sql", generate_sql)
    workflow.set_entry_point("generate_sql")
    workflow.add_edge("generate_sql", END)

    return workflow.compile(checkpointer=checkpointer)


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


async def query_database(
    query: str,
    context_schema: Dict[str, Any],
    thread_id: Optional[str] = None,
    checkpointer: Optional[Any] = None,
    model_name: str = DEFAULT_MODEL,
    graph: Optional[Any] = None,
) -> Dict[str, Any]:
    """Run a query through the agent, compiling the graph only if none is given.

    Passing a pre-compiled ``graph`` (the production path) skips the expensive
    per-request compilation; omitting it compiles a one-off graph, which is
    convenient for tests and ad-hoc use.
    """
    database_info = {
        "database_name": context_schema.get("database_name", "unknown"),
        "tables": context_schema.get("tables", {}),
    }

    try:
        if graph is None:
            logger.info("Compiling one-off LangGraph agent for thread %s", thread_id or "default")
            graph = initialize_agent(checkpointer=checkpointer, model_name=model_name)

        initial_state = AgentState(query=query, database_info=database_info)
        invoke_config = {"configurable": {"thread_id": thread_id}} if thread_id else None
        result = await graph.ainvoke(initial_state, config=invoke_config)
        return _normalize_result(result)
    except Exception as exc:
        logger.error("Error in query_database: %s", exc)
        if logger.isEnabledFor(logging.DEBUG):
            import traceback

            logger.debug("query_database traceback: %s", traceback.format_exc())
        return {
            "response": f"Error processing query: {exc}",
            "agent_response": f"Error processing query: {exc}",
            "sql_query": "",
            "context": {"error": str(exc)},
            "execution_details": {},
            "error": str(exc),
        }

