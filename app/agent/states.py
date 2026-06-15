"""State and structured-output models for the LangGraph agent.

These are the data contracts that flow through the graph. They are kept free of
any LangChain/LangGraph imports so they can be imported cheaply (e.g. by the
service layer or tests) without pulling in the heavy LLM stack.
"""

from typing import Any, Dict

from pydantic import BaseModel, Field


class AgentState(BaseModel):
    """State passed through the LangGraph workflow."""

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
