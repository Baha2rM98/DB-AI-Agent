"""Async LangGraph workflow for natural-language database requests."""

import logging
from typing import Any, Dict, List, Optional

from langchain_core.prompts import ChatPromptTemplate
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, StateGraph
from pydantic import BaseModel

logger = logging.getLogger(__name__)


class AgentState(BaseModel):
    """State passed between LangGraph workflow nodes."""

    query: str
    context: Dict[str, Any] = {}
    database_info: Dict[str, Any] = {}
    current_plan: List[str] = []
    execution_result: Dict[str, Any] = {}
    response: str = ""
    error: str = ""


SYSTEM_MESSAGE = """You are a database assistant that helps users interact with a PostgreSQL database.
You can interpret user queries, develop plans to retrieve or modify data,
and execute those plans.

Important instructions:
1. When asked about tables, make sure to reference all tables from the database.
2. For data retrieval, use the appropriate SQL operations (SELECT).
3. Format your responses clearly and concisely.
4. If the database schema information is incomplete, ask the user to provide it.

The database schema will be provided separately via the `database_info` context.
Your goal is to understand what the user wants to do with the database and help
them accomplish it.
"""


def initialize_agent(
    checkpointer: Optional[Any] = None,
    model_name: str = "gemini-1.5-pro",
):
    """Build the async LangGraph workflow used by the application."""
    llm = ChatGoogleGenerativeAI(
        model=model_name,
        temperature=0,
        convert_system_message_to_human=True,
    )

    workflow = StateGraph(AgentState)

    async def understand_query(state: AgentState) -> AgentState:
        """Parse and understand the user's natural language query."""
        prompt = ChatPromptTemplate.from_messages(
            [("system", SYSTEM_MESSAGE), ("user", "{query}")]
        )
        chain = prompt | llm
        result = await chain.ainvoke(
            {"query": state.query, "database_info": state.database_info}
        )
        state.context["understood_intent"] = result.content
        return state

    async def plan_execution(state: AgentState) -> AgentState:
        """Develop a plan for database operations."""
        if "understood_intent" not in state.context:
            state.error = "Query understanding failed. Cannot create execution plan."
            return state

        planning_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a database operation planner.
Your job is to convert natural language database requests into a sequence of specific operations.

For the database with the following structure:
{database_info}

Create a detailed plan that includes:
1. The type of operation (select, insert, update, delete)
2. The specific tables involved
3. The columns to be affected
4. Any conditions or filters
5. Any sorting or grouping requirements

Format your response as a JSON-like structure that can be parsed and executed.
""",
                ),
                ("user", "User query: {query}\nUnderstood intent: {understood_intent}"),
            ]
        )
        chain = planning_prompt | llm

        try:
            result = await chain.ainvoke(
                {
                    "query": state.query,
                    "understood_intent": state.context.get("understood_intent", ""),
                    "database_info": state.database_info,
                }
            )
            state.context["execution_plan"] = result.content

            lowered = result.content.lower()
            if "select" in lowered:
                state.current_plan.append("select")
            elif "insert" in lowered:
                state.current_plan.append("insert")
            elif "update" in lowered:
                state.current_plan.append("update")
            elif "delete" in lowered:
                state.current_plan.append("delete")
            else:
                state.current_plan.append("unknown")
            return state
        except Exception as exc:
            state.error = f"Failed to create execution plan: {exc}"
            return state

    async def execute_plan(state: AgentState) -> AgentState:
        """Translate the plan into SQL-oriented execution details."""
        if "execution_plan" not in state.context:
            state.error = "Execution plan missing. Cannot proceed with execution."
            return state

        execution_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a database operation executor.
Your job is to convert a high-level database operation plan into the specific
parameters required to perform the operation on the database.

The database you are working with has the following structure:
{database_info}

Parse the execution plan and extract the exact parameters needed for:
- operation_type (select, insert, update, delete)
- table name
- columns/fields
- conditions
- values (for insert/update)

You must output:
- A JSON object containing the extracted fields, and
- A complete SQL statement that can be executed directly.

Only reference tables and columns present in `database_info`.
""",
                ),
                ("user", "Execution plan: {execution_plan}"),
            ]
        )
        chain = execution_prompt | llm

        try:
            result = await chain.ainvoke(
                {
                    "execution_plan": state.context["execution_plan"],
                    "database_info": state.database_info,
                }
            )
            state.context["operation_details"] = result.content

            lowered = result.content.lower()
            if "```sql" in lowered:
                sql = result.content.split("```sql")[1].split("```")[0].strip()
                state.context["sql_query"] = sql
                state.current_plan.append("sql")
            elif "select" in lowered:
                state.current_plan.append("select")
            elif "insert" in lowered:
                state.current_plan.append("insert")
            elif "update" in lowered:
                state.current_plan.append("update")
            elif "delete" in lowered:
                state.current_plan.append("delete")
            else:
                state.current_plan.append("unknown")

            state.execution_result = {
                "success": True,
                "operation": state.current_plan[0] if state.current_plan else "unknown",
                "details": "Database operation plan created successfully.",
                "data": [],
            }
            return state
        except Exception as exc:
            state.error = f"Failed to execute plan: {exc}"
            return state

    async def formulate_response(state: AgentState) -> AgentState:
        """Generate a natural-language response from the execution state."""
        if state.error:
            response_prompt = ChatPromptTemplate.from_messages(
                [
                    (
                        "system",
                        """You are a helpful database assistant.
When operations fail, provide a clear explanation and suggest possible fixes.
Be conversational and helpful.
""",
                    ),
                    ("user", "Error: {error}\nOriginal query: {query}"),
                ]
            )
            chain = response_prompt | llm
            result = await chain.ainvoke({"error": state.error, "query": state.query})
            state.response = result.content
            return state

        response_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a helpful database assistant.
Generate a natural-language response explaining the results of database operations.
For SELECT operations, summarize what data was retrieved.
For INSERT, UPDATE, DELETE operations, explain what changes were made.
Be concise but informative.
""",
                ),
                ("user", "Original query: {query}\nOperation result: {result}"),
            ]
        )
        chain = response_prompt | llm

        try:
            result = await chain.ainvoke(
                {"query": state.query, "result": state.context["operation_details"]}
            )
            state.response = result.content
            return state
        except Exception as exc:
            state.error = f"Failed to formulate response: {exc}"
            state.response = f"I encountered an issue while processing your request: {exc}"
            return state

    async def handle_error(state: AgentState) -> AgentState:
        """Handle errors that occurred during processing."""
        error_prompt = ChatPromptTemplate.from_messages(
            [
                (
                    "system",
                    """You are a database troubleshooter.
Diagnose query issues, suggest possible solutions, and use a helpful tone.
""",
                ),
                ("user", "Query: {query}\nError: {error}\nContext: {context}"),
            ]
        )
        chain = error_prompt | llm

        try:
            context_str = str(
                {k: v for k, v in state.context.items() if k not in ["database_info"]}
            )
            result = await chain.ainvoke(
                {"query": state.query, "error": state.error, "context": context_str}
            )
            state.response = result.content
            return state
        except Exception:
            state.response = (
                "I'm sorry, but I encountered an error processing your request. "
                f"Error details: {state.error}"
            )
            return state

    workflow.add_node("understand_query", understand_query)
    workflow.add_node("plan_execution", plan_execution)
    workflow.add_node("execute_plan", execute_plan)
    workflow.add_node("formulate_response", formulate_response)
    workflow.add_node("handle_error", handle_error)

    workflow.add_edge("understand_query", "plan_execution")
    workflow.add_edge("plan_execution", "execute_plan")
    workflow.add_edge("execute_plan", "formulate_response")
    workflow.add_edge("formulate_response", END)

    workflow.add_conditional_edges(
        "understand_query",
        lambda state: "handle_error" if state.error else "plan_execution",
    )
    workflow.add_conditional_edges(
        "plan_execution",
        lambda state: "handle_error" if state.error else "execute_plan",
    )
    workflow.add_conditional_edges(
        "execute_plan",
        lambda state: "handle_error" if state.error else "formulate_response",
    )
    workflow.add_edge("handle_error", "formulate_response")
    workflow.set_entry_point("understand_query")

    return workflow.compile(checkpointer=checkpointer)


async def query_database(
    query: str,
    context_schema: Dict[str, Any],
    thread_id: Optional[str] = None,
    checkpointer: Optional[Any] = None,
    model_name: str = "gemini-1.5-pro",
) -> Dict[str, Any]:
    """Execute a query against the database using the async LangGraph agent."""
    database_info = {
        "database_name": context_schema.get("database_name", "unknown"),
        "tables": context_schema.get("tables", {}),
        "summary": context_schema.get("summary", {}),
    }

    try:
        logger.info("Initializing LangGraph agent for thread %s", thread_id or "default")
        agent = initialize_agent(checkpointer=checkpointer, model_name=model_name)
        initial_state = AgentState(query=query, database_info=database_info)
        invoke_config = {"configurable": {"thread_id": thread_id}} if thread_id else None
        result = await agent.ainvoke(initial_state, config=invoke_config)
        logger.debug("Agent result type: %s", type(result))

        if isinstance(result, dict):
            return result
        if hasattr(result, "response"):
            return {
                "response": result.response,
                "context": result.context if hasattr(result, "context") else {},
                "execution_details": (
                    result.execution_result if hasattr(result, "execution_result") else {}
                ),
            }
        logger.warning("Unexpected result type from agent: %s", type(result))
        return {
            "response": "The agent could not process your query properly.",
            "context": {},
            "execution_details": {},
        }
    except Exception as exc:
        import traceback

        logger.error("Error in query_database: %s", exc)
        logger.debug(traceback.format_exc())
        return {
            "response": f"Error processing query: {exc}",
            "context": {"error": str(exc)},
            "execution_details": {"error": traceback.format_exc()},
        }
