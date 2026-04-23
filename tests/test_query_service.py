from unittest.mock import Mock

from app.services.query_service import QueryService
from app.services.schema_service import SchemaService


class TestQueryServiceSchemaHandling:
    """Verify deterministic schema queries bypass the agent path."""

    def test_list_tables_bypasses_agent(self):
        """Table-listing requests should be answered directly from schema data."""
        mock_agent = Mock()
        mock_db = Mock()
        mock_db.get_database_schema.return_value = {
            "tables": {
                "public.actor": {"table_name": "actor", "columns": []},
                "public.film": {"table_name": "film", "columns": []},
            }
        }

        service = QueryService(
            agent=mock_agent,
            database_gateway=mock_db,
            schema_service=SchemaService(mock_db),
        )

        result = service.execute_query("Show me all tables", "thread-1")

        assert result.success is True
        assert result.affected_rows == 2
        assert result.data == [
            {"table_name": "public.actor"},
            {"table_name": "public.film"},
        ]
        mock_agent.execute_query.assert_not_called()
        mock_agent.record_thread_activity.assert_called_once_with("thread-1", "schema_list")

    def test_describe_table_bypasses_agent(self):
        """Table-description requests should return schema details directly."""
        mock_agent = Mock()
        mock_agent.get_thread_info.return_value = {"thread_id": "thread-2", "query_count": 1}
        mock_db = Mock()
        mock_db.get_database_schema.return_value = {
            "tables": {
                "public.actor": {
                    "table_name": "actor",
                    "columns": [
                        {"name": "actor_id", "type": "INTEGER"},
                        {"name": "first_name", "type": "VARCHAR"},
                    ],
                    "primary_keys": ["actor_id"],
                    "foreign_keys": [],
                    "indices": [],
                }
            }
        }

        service = QueryService(
            agent=mock_agent,
            database_gateway=mock_db,
            schema_service=SchemaService(mock_db),
        )

        result = service.execute_query("Describe table actor", "thread-2")

        assert result.success is True
        assert result.affected_rows == 2
        assert result.data[0]["table_name"] == "actor"
        mock_agent.execute_query.assert_not_called()
        mock_agent.record_thread_activity.assert_called_once_with("thread-2", "schema_describe")

    def test_non_schema_query_still_uses_agent(self):
        """Regular data questions should still flow through the agent."""
        mock_agent = Mock()
        mock_agent.execute_query.return_value = {
            "success": True,
            "response": "Found actor rows",
            "data": [{"actor_id": 1}],
            "affected_rows": 1,
        }
        mock_agent.get_thread_info.return_value = {"thread_id": "thread-3"}
        mock_db = Mock()
        mock_db.get_database_schema.return_value = {"tables": {}}

        service = QueryService(
            agent=mock_agent,
            database_gateway=mock_db,
            schema_service=SchemaService(mock_db),
        )

        result = service.execute_query("Show me all actors", "thread-3")

        assert result.success is True
        assert result.data == [{"actor_id": 1}]
        mock_agent.execute_query.assert_called_once_with(
            query="Show me all actors",
            thread_id="thread-3",
        )
