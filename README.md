# LangGraph Database Agent

Natural-language database API built with FastAPI, LangGraph, Gemini, and PostgreSQL.

## Overview

This project exposes a small HTTP API that:

- accepts natural-language database questions
- persists conversational state with LangGraph checkpoints
- handles simple schema questions deterministically
- uses Gemini through LangChain/LangGraph for broader query interpretation
- stores thread metadata through a thread-first API surface

The codebase is intentionally flattened around a practical structure:

```text
app/
  agent/
  api/
  integrations/
  services/
  main.py
```

## Current Architecture

### API

- [app/api/routes.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/app/api/routes.py)
  FastAPI endpoints and response shaping
- [app/api/dependencies.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/app/api/dependencies.py)
  dependency wiring for settings, DB gateway, schema service, and query service

### Services

- [app/services/query_service.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/app/services/query_service.py)
  main orchestration logic
- [app/services/schema_service.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/app/services/schema_service.py)
  deterministic schema operations like table listing and table description

### Integrations

- [app/integrations/database.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/app/integrations/database.py)
  SQLAlchemy gateway with sync and native async DB access
- [app/integrations/persistent_agent.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/app/integrations/persistent_agent.py)
  LangGraph-backed persistent agent adapter
- [app/integrations/checkpoint_factory.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/app/integrations/checkpoint_factory.py)
  LangGraph saver creation for memory, SQLite, or Postgres backends
- [app/integrations/settings.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/app/integrations/settings.py)
  typed environment-backed settings

### Agent Workflow

- [app/agent/langgraph_agent.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/app/agent/langgraph_agent.py)
  LangGraph workflow definition and async invocation path

## Features

- `thread_id`-first API design
- async FastAPI request path
- native async LangGraph invocation
- native async SQLAlchemy engine for request-time DB access
- deterministic handling for:
  - `show me all tables`
  - `list tables`
  - `describe table actor`
  - `schema for actor`
  - `columns in actor`
- Dockerized local stack with Postgres
- Makefile shortcuts for common dev workflows

## Installation

### Prerequisites

- Python 3.11+
- PostgreSQL
- Google API key
- Docker optional for containerized local runs

### Local Setup

```bash
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
copy .env.example .env
```

Fill in `.env` with your database credentials and `GOOGLE_API_KEY`.

### Run Locally

```bash
python app/main.py
```

Or:

```bash
uvicorn app.main:app --reload
```

## Docker

Use the provided Compose stack:

```bash
make up
make down
make restart
make rebuild
make logs
```

The current stack is defined in:

- [compose.yaml](C:/Users/baha2/PycharmProjects/DB-AI-Agent/compose.yaml)
- [docker/Dockerfile](C:/Users/baha2/PycharmProjects/DB-AI-Agent/docker/Dockerfile)

## Configuration

Important environment variables:

```bash
# Target database: the external database users ask about.
TARGET_DATABASE_URL=
TARGET_DB_HOST=localhost
TARGET_DB_PORT=5432
TARGET_DB_USER=postgres
TARGET_DB_PASSWORD=postgres
TARGET_DB_NAME=sakila
ALLOW_TARGET_WRITES=false
ALLOW_TARGET_DELETES=false

# Seconds to cache the inspected target-database schema (0 disables caching).
SCHEMA_CACHE_TTL_SECONDS=300

GOOGLE_API_KEY=your_google_api_key
LLM_MODEL=gemini-1.5-flash

# Internal persistence for LangGraph memory/checkpoints.
CHECKPOINTER_BACKEND=memory
# memory | sqlite | postgres

CHECKPOINTER_DATABASE_URL=
CHECKPOINTER_SQLITE_PATH=checkpoints.db

HOST=0.0.0.0
PORT=8000
LOG_LEVEL=INFO
```

## API

### `GET /`

Basic app metadata.

### `GET /healthz`

Lightweight app liveness check for Docker and process monitoring.

Example response:

```json
{
  "status": "ok"
}
```

### `POST /query`

Run a natural-language query.

Request:

```json
{
  "query": "show me all tables",
  "thread_id": "user-123"
}
```

Response shape:

```json
{
  "success": true,
  "message": "I found 5 tables in the database.",
  "agent_response": "I found 5 tables in the database.",
  "data": [
    { "table_name": "public.actor" }
  ],
  "affected_rows": 5,
  "thread_id": "user-123",
  "context_info": {
    "thread_id": "user-123"
  },
  "sql_query": null,
  "operation_type": null,
  "error": null
}
```

### `GET /threads`

List active thread ids known to the app instance.

### `GET /threads/{thread_id}`

Return metadata for a thread.

### `DELETE /threads/{thread_id}`

Clear thread metadata tracked by the app.

## Notes On Persistence

The system uses LangGraph checkpoints for conversational persistence.

Current behavior:

- target database schema and user-requested SQL execution use the target database settings
- durable graph state is handled by LangGraph checkpointers
- lightweight API-facing thread metadata is tracked separately
- thread deletion currently clears tracked metadata, not checkpoint rows

## Testing

Run the suite with:

```bash
.venv\Scripts\python.exe -m pytest -q
```

Current status after the latest refactor:

- `45 passed, 1 skipped`

Test files:

- [tests/test_agent.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/tests/test_agent.py)
- [tests/test_api.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/tests/test_api.py)
- [tests/test_database.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/tests/test_database.py)
- [tests/test_query_service.py](C:/Users/baha2/PycharmProjects/DB-AI-Agent/tests/test_query_service.py)

## Development Notes

The refactor moved the project away from:

- global mutable API state
- manual in-process session management
- session-based API contracts
- over-layered folder structure
- sync request handlers that blocked on LLM work

The current design is much closer to:

- flat, practical modules
- `thread_id`-first request flow
- async request handling
- persistent LangGraph threads
- deterministic schema responses where possible

## References

Native async DB access uses SQLAlchemy asyncio with the Psycopg dialect:

- [SQLAlchemy PostgreSQL dialect docs](https://docs.sqlalchemy.org/21/dialects/postgresql.html)

LangGraph supports async graph invocation and async savers such as `AsyncPostgresSaver` and `AsyncSqliteSaver`:

- [LangGraph docs](https://langchain-ai.github.io/langgraph/)
