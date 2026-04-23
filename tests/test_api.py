from unittest.mock import Mock
from app.services.query_service import QueryResult


class TestAPIRoutes:
    """Test cases for API routes."""

    def test_read_root(self, test_client):
        """Test root endpoint."""
        response = test_client.get("/")

        assert response.status_code == 200
        data = response.json()
        assert "name" in data
        assert "LangGraph Database Agent" in data["name"]

    def test_health_check_success(self, test_client, mock_service_dependency, mock_db_connector):
        """Test successful health check."""
        mock_db_connector.test_connection.return_value = True
        mock_service_dependency.get_active_threads.return_value = ["session1"]

        response = test_client.get("/db_connection")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "connected"
        assert data["database_connection"] == "ok"
        assert data["active_threads"] == 1

    def test_health_check_failure(self, test_client, mock_service_dependency, mock_db_connector):
        """Test health check with database connection failure."""
        mock_db_connector.test_connection.return_value = False

        response = test_client.get("/db_connection")

        assert response.status_code == 503
        data = response.json()
        assert "Database connection failed" in data["detail"]

    def test_process_query_success(self, test_client, mock_service_dependency):
        """Test successful query processing."""
        mock_service_dependency.execute_query.return_value = QueryResult(
            success=True,
            message="Found 2 actors",
            agent_response="Found 2 actors",
            data=[
                {"actor_id": 1, "first_name": "John"},
                {"actor_id": 2, "first_name": "Jane"},
            ],
            affected_rows=2,
            thread_id="test_session",
            context_info={"thread_id": "test_session", "query_count": 1},
        )

        request_data = {
            "query": "Show me all actors",
            "thread_id": "test_session"
        }

        response = test_client.post("/query", json=request_data)

        assert response.status_code == 200
        data = response.json()
        assert data["success"] is True
        assert data["message"] == "Found 2 actors"
        assert len(data["data"]) == 2
        assert data["thread_id"] == "test_session"

    def test_process_query_empty_query(self, test_client, mock_service_dependency):
        """Test processing empty query."""
        request_data = {
            "query": "",
            "thread_id": "test_session"
        }

        response = test_client.post("/query", json=request_data)

        assert response.status_code == 400
        assert "Query cannot be empty" in response.json()["detail"]

    def test_get_active_threads(self, test_client, mock_service_dependency):
        """Test getting active threads."""
        response = test_client.get("/threads")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)

    def test_get_thread_info_success(self, test_client, mock_service_dependency):
        """Test getting thread information."""
        response = test_client.get("/threads/test_session")

        assert response.status_code == 200
        data = response.json()
        assert data["thread_id"] == "test_session"

    def test_clear_thread_success(self, test_client, mock_service_dependency):
        """Test successful thread clearing."""
        response = test_client.delete("/threads/test_session")

        assert response.status_code == 200
        data = response.json()
        assert "cleared successfully" in data["message"]


class TestRequestValidation:
    """Test request validation and edge cases."""

    def test_query_request_validation(self, test_client, mock_service_dependency):
        """Test QueryRequest model validation."""
        # Missing query field
        response = test_client.post("/query", json={"thread_id": "test"})
        assert response.status_code == 422

        # Invalid JSON
        response = test_client.post("/query", data="invalid json")
        assert response.status_code == 422

    def test_query_with_special_characters(self, test_client, mock_service_dependency):
        """Test query with special characters and Unicode."""
        special_queries = [
            "Find actors with names containing 'ñ'",
            "Search for films with rating >= 'PG-13'",
            "Show customers where email contains '@'",
            "Find actors named 'José' or 'François'"
        ]

        for query in special_queries:
            request_data = {"query": query, "thread_id": "test"}
            response = test_client.post("/query", json=request_data)
            assert response.status_code == 200
