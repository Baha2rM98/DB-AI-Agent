import pytest
from unittest.mock import AsyncMock, Mock, patch
from sqlalchemy.exc import SQLAlchemyError
from app.integrations.database import SQLAlchemyDatabaseGateway


class TestSQLAlchemyDatabaseGateway:
    """Test cases for SQLAlchemyDatabaseGateway."""

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_init_with_connection_string(self, mock_create_engine, mock_create_async_engine):
        """Test initialization with explicit connection string."""
        conn_str = "postgresql://user:pass@localhost:5432/testdb"
        connector = SQLAlchemyDatabaseGateway(conn_str)
        assert connector.connection_string == conn_str
        assert connector.async_connection_string == "postgresql+psycopg://user:pass@localhost:5432/testdb"

    @patch.dict('os.environ', {
        'DB_USER': 'test_user',
        'DB_PASSWORD': 'test_pass',
        'DB_HOST': 'test_host',
        'DB_PORT': '5432',
        'DB_NAME': 'test_db'
    })
    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_init_with_environment_variables(self, mock_create_engine, mock_create_async_engine):
        """Test initialization using an explicit connection string."""
        connector = SQLAlchemyDatabaseGateway(
            "postgresql+psycopg://test_user:test_pass@test_host:5432/test_db"
        )
        expected = "postgresql+psycopg://test_user:test_pass@test_host:5432/test_db"
        assert connector.connection_string == expected

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_test_connection_success(self, mock_create_engine, mock_create_async_engine):
        """Test successful database connection."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection")
        result = connector.test_connection()

        assert result is True
        mock_conn.execute.assert_called_once()

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_test_connection_failure(self, mock_create_engine, mock_create_async_engine):
        """Test database connection failure."""
        mock_engine = Mock()
        mock_engine.connect.side_effect = SQLAlchemyError("Connection failed")
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection")
        result = connector.test_connection()

        assert result is False

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_execute_query_select_success(self, mock_create_engine, mock_create_async_engine):
        """Test successful SELECT query execution."""
        # Setup mocks
        mock_engine = Mock()
        mock_conn = Mock()
        mock_result = Mock()

        mock_result.returns_rows = True
        mock_result.keys.return_value = ['id', 'name']
        mock_result.fetchall.return_value = [(1, 'John'), (2, 'Jane')]
        mock_result.fetchmany.return_value = [(1, 'John'), (2, 'Jane')]
        mock_result.rowcount = 2

        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection")
        result = connector.execute_query("SELECT * FROM users")

        assert result["success"] is True
        assert len(result["data"]) == 2
        assert result["data"][0] == {"id": 1, "name": "John"}
        assert result["affected_rows"] == 2

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_execute_query_insert_success(self, mock_create_engine, mock_create_async_engine):
        """Test successful INSERT query execution."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_result = Mock()

        mock_result.returns_rows = False
        mock_result.rowcount = 1

        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection")
        result = connector.execute_query("INSERT INTO users (name) VALUES ('John')")

        assert result["success"] is True
        assert result["data"] == []  # Changed: INSERT returns empty data array
        assert result["affected_rows"] == 1
        assert result["operation_type"] == "insert"  # Added: verify operation type

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_execute_query_with_parameters(self, mock_create_engine, mock_create_async_engine):
        """Test query execution with parameters."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_result = Mock()

        mock_result.returns_rows = True
        mock_result.keys.return_value = ['id', 'name']
        mock_result.fetchall.return_value = [(1, 'John')]
        mock_result.fetchmany.return_value = [(1, 'John')]
        mock_result.rowcount = 1

        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection")
        result = connector.execute_query(
            "SELECT * FROM users WHERE name = :name",
            {"name": "John"}
        )

        assert result["success"] is True

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_execute_query_failure(self, mock_create_engine, mock_create_async_engine):
        """Test query execution failure."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_conn.execute.side_effect = SQLAlchemyError("Query failed")
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection")
        result = connector.execute_query("INVALID SQL")

        assert result["success"] is False
        assert "error" in result

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.inspect')
    @patch('app.integrations.database.create_engine')
    def test_get_table_names(self, mock_create_engine, mock_inspect, mock_create_async_engine):
        """Test getting table names."""
        mock_inspector = Mock()
        mock_inspector.get_table_names.return_value = ["users", "products", "orders"]
        mock_inspect.return_value = mock_inspector

        connector = SQLAlchemyDatabaseGateway("test://connection")
        tables = connector.get_table_names()

        assert tables == ["orders", "products", "users"]

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.inspect')
    @patch('app.integrations.database.create_engine')
    def test_get_table_schema(self, mock_create_engine, mock_inspect, mock_create_async_engine):
        """Test getting table schema."""
        mock_inspector = Mock()
        mock_inspector.get_columns.return_value = [
            {"name": "id", "type": "INTEGER", "nullable": False, "default": None},
            {"name": "name", "type": "VARCHAR(255)", "nullable": True, "default": None}
        ]
        mock_inspector.get_pk_constraint.return_value = {"constrained_columns": ["id"]}
        mock_inspector.get_foreign_keys.return_value = []
        mock_inspector.get_indexes.return_value = []
        mock_inspect.return_value = mock_inspector

        connector = SQLAlchemyDatabaseGateway("test://connection")
        schema = connector.get_table_schema("users")

        assert schema["table_name"] == "users"
        assert len(schema["columns"]) == 2
        assert schema["primary_keys"] == ["id"]
        assert schema["foreign_keys"] == []

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_execute_operation_select(self, mock_create_engine, mock_create_async_engine):
        """Test execute_query with SELECT behavior through the gateway."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_result = Mock()

        mock_result.returns_rows = True
        mock_result.keys.return_value = ['id', 'name']
        mock_result.fetchall.return_value = [(1, 'John')]
        mock_result.fetchmany.return_value = [(1, 'John')]
        mock_result.rowcount = 1

        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection")
        result = connector.execute_query(
            "SELECT id, name FROM users WHERE age > 18 ORDER BY name LIMIT 10"
        )

        assert result["success"] is True
        assert len(result["data"]) == 1

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_execute_operation_unsupported(self, mock_create_engine, mock_create_async_engine):
        """Test execute_query behavior with unsupported SQL classification."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_result = Mock()
        mock_result.returns_rows = False
        mock_result.rowcount = 0
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection")
        result = connector.execute_query("VACUUM")

        assert result["success"] is True

    @pytest.mark.anyio
    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    async def test_atest_connection_success(self, mock_create_engine, mock_create_async_engine):
        """Test successful async database connection."""
        mock_async_engine = Mock()
        mock_async_connection = AsyncMock()
        mock_async_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_async_connection)
        mock_async_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_create_async_engine.return_value = mock_async_engine

        connector = SQLAlchemyDatabaseGateway("postgresql://user:pass@localhost/testdb")
        result = await connector.atest_connection()

        assert result is True
        mock_async_connection.execute.assert_awaited_once()

    @pytest.mark.anyio
    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    async def test_aexecute_query_select_success(self, mock_create_engine, mock_create_async_engine):
        """Test successful async SELECT query execution."""
        mock_async_engine = Mock()
        mock_async_connection = AsyncMock()
        mock_result = Mock()
        mock_result.returns_rows = True
        mock_result.keys.return_value = ['id', 'name']
        mock_result.fetchall.return_value = [(1, 'John')]
        mock_result.fetchmany.return_value = [(1, 'John')]
        mock_result.rowcount = 1
        mock_async_connection.execute = AsyncMock(return_value=mock_result)
        mock_async_engine.connect.return_value.__aenter__ = AsyncMock(return_value=mock_async_connection)
        mock_async_engine.connect.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_create_async_engine.return_value = mock_async_engine

        connector = SQLAlchemyDatabaseGateway("postgresql://user:pass@localhost/testdb")
        result = await connector.aexecute_query("SELECT * FROM users")

        assert result["success"] is True
        assert result["data"] == [{"id": 1, "name": "John"}]


class TestSQLAlchemyDatabaseGatewayInternals:
    """Tests for lazy engine creation, PK caching, and bulk reflection."""

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_sync_engine_is_created_lazily(self, mock_create_engine, mock_create_async_engine):
        """The sync engine should not be built until first accessed."""
        connector = SQLAlchemyDatabaseGateway("postgresql://u:p@h/db")
        mock_create_engine.assert_not_called()

        _ = connector.engine
        mock_create_engine.assert_called_once()

        _ = connector.engine
        mock_create_engine.assert_called_once()  # cached, not rebuilt

    @pytest.mark.anyio
    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    async def test_returning_clause_uses_cached_pks(
        self, mock_create_engine, mock_create_async_engine
    ):
        """A cached primary key should produce RETURNING without a DB round-trip."""
        connector = SQLAlchemyDatabaseGateway("postgresql://u:p@h/db")
        connector._pk_cache["actor"] = ["actor_id"]

        out = await connector._aadd_returning_clause(
            "INSERT INTO actor (first_name) VALUES ('x')", "insert"
        )

        assert out.endswith("RETURNING actor_id")
        connector.async_engine.connect.assert_not_called()

    @pytest.mark.anyio
    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    async def test_returning_clause_falls_back_to_star(
        self, mock_create_engine, mock_create_async_engine
    ):
        """A table with no cached primary key falls back to RETURNING *."""
        connector = SQLAlchemyDatabaseGateway("postgresql://u:p@h/db")
        connector._pk_cache["logs"] = []

        out = await connector._aadd_returning_clause(
            "INSERT INTO logs (msg) VALUES ('x')", "insert"
        )

        assert out.endswith("RETURNING *")
        connector.async_engine.connect.assert_not_called()

    def test_assemble_table_schema_shape(self):
        """Bulk-reflection assembly must match the per-table inspector shape."""
        result = SQLAlchemyDatabaseGateway._assemble_table_schema(
            "public",
            "actor",
            [{"name": "actor_id", "type": "INTEGER", "nullable": False, "default": None}],
            {"constrained_columns": ["actor_id"]},
            [
                {
                    "constrained_columns": ["address_id"],
                    "referred_schema": "public",
                    "referred_table": "address",
                    "referred_columns": ["address_id"],
                }
            ],
            [{"name": "idx_actor_last_name"}],
        )

        assert result["schema"] == "public"
        assert result["table_name"] == "actor"
        assert result["columns"][0] == {
            "name": "actor_id",
            "type": "INTEGER",
            "nullable": False,
            "default": "None",
        }
        assert result["primary_keys"] == ["actor_id"]
        assert result["foreign_keys"][0]["referred_table"] == "address"
        assert result["indices"] == [{"name": "idx_actor_last_name"}]

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_pool_settings_passed_to_async_engine(
        self, mock_create_engine, mock_create_async_engine
    ):
        """Pool tuning should reach the async engine factory."""
        SQLAlchemyDatabaseGateway(
            "postgresql://u:p@h/db",
            pool_size=7,
            max_overflow=3,
            pool_recycle=60,
        )

        _, kwargs = mock_create_async_engine.call_args
        assert kwargs["pool_size"] == 7
        assert kwargs["max_overflow"] == 3
        assert kwargs["pool_recycle"] == 60
        assert kwargs["pool_pre_ping"] is True

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_select_is_capped_at_max_result_rows(
        self, mock_create_engine, mock_create_async_engine
    ):
        """A SELECT should fetch at most max_result_rows rows."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_result = Mock()
        mock_result.returns_rows = True
        mock_result.keys.return_value = ['id']
        mock_result.fetchmany.return_value = [(1,), (2,)]
        mock_result.rowcount = 2
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection", max_result_rows=2)
        result = connector.execute_query("SELECT * FROM big_table")

        assert len(result["data"]) == 2
        mock_result.fetchmany.assert_called_once_with(2)
        mock_result.fetchall.assert_not_called()

    @patch('app.integrations.database.create_async_engine')
    @patch('app.integrations.database.create_engine')
    def test_zero_cap_uses_fetchall(self, mock_create_engine, mock_create_async_engine):
        """A zero cap disables the bound and reads the full result set."""
        mock_engine = Mock()
        mock_conn = Mock()
        mock_result = Mock()
        mock_result.returns_rows = True
        mock_result.keys.return_value = ['id']
        mock_result.fetchall.return_value = [(1,)]
        mock_result.rowcount = 1
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__ = Mock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = Mock(return_value=None)
        mock_create_engine.return_value = mock_engine

        connector = SQLAlchemyDatabaseGateway("test://connection", max_result_rows=0)
        result = connector.execute_query("SELECT * FROM small_table")

        assert len(result["data"]) == 1
        mock_result.fetchall.assert_called_once()
        mock_result.fetchmany.assert_not_called()


@pytest.mark.integration
class TestSQLAlchemyDatabaseGatewayIntegration:
    """Integration tests for SQLAlchemyDatabaseGateway with real database."""

    @pytest.fixture(autouse=True)
    def setup_test_db(self, test_connection_string, db_test_helper):
        """Setup test database for integration tests."""
        try:
            from sqlalchemy import create_engine
            engine = create_engine(test_connection_string)
            db_test_helper.create_test_tables(engine)
            yield engine
        except Exception as e:
            pytest.skip(f"Test database not available: {e}")
        finally:
            try:
                db_test_helper.cleanup_test_tables(engine)
            except:
                pass

    def test_real_database_operations(self, test_connection_string, sample_actor_data, setup_test_db):
        """Test real database operations."""
        connector = SQLAlchemyDatabaseGateway(test_connection_string)

        # Test connection
        assert connector.test_connection() is True

        # Insert test data
        for actor in sample_actor_data:
            result = connector.execute_query(
                "INSERT INTO test_actor (first_name, last_name) VALUES (:first_name, :last_name)",
                {
                    "first_name": actor["first_name"],
                    "last_name": actor["last_name"],
                },
            )
            assert result["success"] is True

        # Query data
        result = connector.execute_query("SELECT * FROM test_actor")
        assert result["success"] is True
        assert len(result["data"]) == len(sample_actor_data)
