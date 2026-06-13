from app.services.sql_safety import (
    SqlSafetyPolicy,
    detect_operation_type,
    has_multiple_statements,
)


class TestSqlValidation:
    """Operation gating and multi-statement rejection."""

    def test_select_is_allowed(self):
        result = SqlSafetyPolicy().validate("SELECT * FROM actor")
        assert result.allowed is True
        assert result.operation_type == "select"

    def test_write_blocked_by_default(self):
        result = SqlSafetyPolicy().validate("UPDATE actor SET first_name = 'x'")
        assert result.allowed is False
        assert result.operation_type == "update"
        assert "writes are disabled" in result.reason

    def test_write_allowed_when_enabled(self):
        result = SqlSafetyPolicy(allow_writes=True).validate("INSERT INTO actor VALUES (1)")
        assert result.allowed is True

    def test_delete_requires_both_flags(self):
        assert SqlSafetyPolicy(allow_writes=True).validate("DELETE FROM actor").allowed is False
        assert (
            SqlSafetyPolicy(allow_writes=True, allow_deletes=True)
            .validate("DELETE FROM actor")
            .allowed
            is True
        )

    def test_multiple_statements_blocked(self):
        result = SqlSafetyPolicy().validate("SELECT * FROM actor; DROP TABLE actor;")
        assert result.allowed is False
        assert "multiple statements" in result.reason

    def test_helpers(self):
        assert detect_operation_type("  Select 1") == "select"
        assert has_multiple_statements("SELECT 1; SELECT 2") is True
        assert has_multiple_statements("SELECT 1;") is False


class TestRowLimitEnforcement:
    """Automatic LIMIT injection for unbounded SELECTs."""

    def test_limit_appended_to_unbounded_select(self):
        policy = SqlSafetyPolicy(max_select_rows=1000)
        assert policy.enforce_row_limit("SELECT * FROM actor", "select") == (
            "SELECT * FROM actor LIMIT 1000"
        )

    def test_trailing_semicolon_handled(self):
        policy = SqlSafetyPolicy(max_select_rows=1000)
        assert policy.enforce_row_limit("SELECT * FROM actor;", "select") == (
            "SELECT * FROM actor LIMIT 1000"
        )

    def test_existing_limit_is_preserved(self):
        policy = SqlSafetyPolicy(max_select_rows=1000)
        assert policy.enforce_row_limit("SELECT * FROM actor LIMIT 5", "select") == (
            "SELECT * FROM actor LIMIT 5"
        )

    def test_existing_limit_offset_is_preserved(self):
        policy = SqlSafetyPolicy(max_select_rows=1000)
        sql = "SELECT * FROM actor LIMIT 5 OFFSET 10"
        assert policy.enforce_row_limit(sql, "select") == sql

    def test_non_select_is_untouched(self):
        policy = SqlSafetyPolicy(max_select_rows=1000)
        assert policy.enforce_row_limit("UPDATE actor SET x = 1", "update") == (
            "UPDATE actor SET x = 1"
        )

    def test_disabled_when_zero(self):
        policy = SqlSafetyPolicy(max_select_rows=0)
        assert policy.enforce_row_limit("SELECT * FROM actor", "select") == "SELECT * FROM actor"
