"""Prompt text and prompt-time schema formatting for the LangGraph agent.

Kept separate from the graph wiring so prompts can be reviewed and tuned in one
place, and so this module stays free of heavy LangChain imports.
"""

from typing import Any, Dict

SYSTEM_MESSAGE = """You are an expert PostgreSQL assistant. Given a database schema and a user request, produce a single executable SQL statement that fulfils it.

Rules:
1. Output exactly one SQL statement, with no markdown code fences.
2. Only reference tables and columns that appear in the provided schema.
3. Prefer read-only SELECT statements unless the user clearly asks to modify data.
4. If the request cannot be answered with SQL against this schema, return an empty sql_query and explain why in the explanation.
"""

# Filled in at invocation time with the compact schema summary and user request.
USER_PROMPT_TEMPLATE = "Database schema:\n{schema}\n\nUser request: {query}"


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
