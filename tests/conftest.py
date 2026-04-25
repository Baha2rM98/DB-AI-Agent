import pytest
import asyncio
import os
from unittest.mock import AsyncMock, Mock, patch
from sqlalchemy import text
from fastapi.testclient import TestClient

from app.main import app
from app.api.dependencies import get_query_service
from app.services.query_service import QueryResult, QueryService


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
def test_db_config():
    """Test database configuration."""
    return {
        "host": os.getenv("TEST_DB_HOST", "localhost"),
        "port": os.getenv("TEST_DB_PORT", "5432"),
        "user": os.getenv("TEST_DB_USER", "postgres"),
        "password": os.getenv("TEST_DB_PASSWORD", "postgres"),
        "database": os.getenv("TEST_DB_NAME", "test_db")
    }


@pytest.fixture
def test_connection_string(test_db_config):
    """Create test database connection string."""
    return f"postgresql://{test_db_config['user']}:{test_db_config['password']}@{test_db_config['host']}:{test_db_config['port']}/{test_db_config['database']}"


@pytest.fixture
def sample_actor_data():
    """Sample actor data for testing."""
    return [
        {"actor_id": 1, "first_name": "John", "last_name": "Doe"},
        {"actor_id": 2, "first_name": "Jane", "last_name": "Smith"},
        {"actor_id": 3, "first_name": "Bob", "last_name": "Johnson"}
    ]


@pytest.fixture
def mock_agent_result():
    """Mock agent result for testing."""
    return {
        "response": "I found 2 actors named John in the database.",
        "context": {
            "sql_query": "SELECT * FROM actor WHERE first_name = 'John'",
            "execution_plan": "select operation on actor table",
            "operation_details": "Retrieve actors with first name John"
        },
        "execution_details": {
            "success": True,
            "operation": "select",
            "data": []
        }
    }


@pytest.fixture
def mock_query_service():
    """Mock the application query service used by the API layer."""
    mock_service = Mock(spec=QueryService)
    mock_service.execute_query = AsyncMock(return_value=QueryResult(
        success=True,
        message="Found 2 actors",
        agent_response="Found 2 actors",
        thread_id="test_session",
        data=[
            {"actor_id": 1, "first_name": "John"},
            {"actor_id": 2, "first_name": "Jane"},
        ],
        affected_rows=2,
        context_info={
            "thread_id": "test_session",
            "created_at": "2024-01-01T12:00:00",
            "last_activity": "2024-01-01T12:30:00",
            "query_count": 1,
            "last_table": "actor",
            "last_operation": "select",
            "context_summary": "Test session",
        },
    ))
    mock_service.get_active_threads = AsyncMock(return_value=["test_session"])
    mock_service.get_thread_info = AsyncMock(return_value={
        "thread_id": "test_session",
        "created_at": "2024-01-01T12:00:00",
        "last_activity": "2024-01-01T12:30:00",
        "query_count": 1,
        "last_table": "actor",
        "last_operation": "select",
        "context_summary": "Test session",
    })
    mock_service.clear_thread = AsyncMock(return_value=True)
    mock_service.aclose = AsyncMock(return_value=None)
    return mock_service


@pytest.fixture
def test_client():
    """FastAPI test client."""
    return TestClient(app)


@pytest.fixture
def mock_service_dependency(mock_query_service):
    """Override API dependencies with test doubles."""

    def override_get_query_service():
        return mock_query_service

    app.dependency_overrides[get_query_service] = override_get_query_service
    yield mock_query_service
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def setup_test_env():
    """Setup test environment variables."""
    test_env = {
        "GOOGLE_API_KEY": "test_api_key",
        "DB_HOST": "localhost",
        "DB_PORT": "5432",
        "DB_USER": "test_user",
        "DB_PASSWORD": "test_pass",
        "DB_NAME": "test_db"
    }

    with patch.dict(os.environ, test_env):
        yield


class DatabaseTestHelper:
    """Helper class for database testing operations."""

    @staticmethod
    def create_test_tables(engine):
        """Create test tables for integration testing."""
        with engine.connect() as conn:
            conn.execute(text("""
                              CREATE TABLE IF NOT EXISTS test_actor
                              (
                                  actor_id
                                  SERIAL
                                  PRIMARY
                                  KEY,
                                  first_name
                                  VARCHAR
                              (
                                  45
                              ) NOT NULL,
                                  last_name VARCHAR
                              (
                                  45
                              ) NOT NULL,
                                  last_update TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                                  )
                              """))
            conn.commit()

    @staticmethod
    def cleanup_test_tables(engine):
        """Clean up test tables after testing."""
        with engine.connect() as conn:
            conn.execute(text("DROP TABLE IF EXISTS test_actor CASCADE"))
            conn.commit()


@pytest.fixture
def db_test_helper():
    """Database test helper fixture."""
    return DatabaseTestHelper
