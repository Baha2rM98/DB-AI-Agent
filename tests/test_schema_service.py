from unittest.mock import AsyncMock, Mock

import pytest

from app.services.schema_service import SchemaService


class TestSchemaServiceCaching:
    """Verify the TTL schema cache avoids redundant database inspection."""

    @pytest.mark.anyio
    async def test_schema_is_cached_within_ttl(self):
        """Repeated reads within the TTL should hit the cache, not the gateway."""
        schema = {"tables": {"public.actor": {"table_name": "actor", "columns": []}}}
        mock_db = Mock()
        mock_db.aget_database_schema = AsyncMock(return_value=schema)

        service = SchemaService(mock_db, cache_ttl_seconds=300)

        first = await service.get_database_schema()
        second = await service.get_database_schema()

        assert first is second
        mock_db.aget_database_schema.assert_awaited_once()

    @pytest.mark.anyio
    async def test_dependent_reads_share_one_inspection(self):
        """list_tables + get_table_details should inspect the database once."""
        schema = {
            "tables": {
                "public.actor": {"table_name": "actor", "columns": [{"name": "actor_id"}]},
                "public.film": {"table_name": "film", "columns": []},
            }
        }
        mock_db = Mock()
        mock_db.aget_database_schema = AsyncMock(return_value=schema)

        service = SchemaService(mock_db, cache_ttl_seconds=300)

        tables = await service.list_tables()
        details = await service.get_table_details("actor")

        assert tables == ["public.actor", "public.film"]
        assert details["table_name"] == "actor"
        mock_db.aget_database_schema.assert_awaited_once()

    @pytest.mark.anyio
    async def test_refresh_forces_reinspection(self):
        """refresh() should bypass the cache and replace it with fresh data."""
        mock_db = Mock()
        mock_db.aget_database_schema = AsyncMock(
            side_effect=[{"tables": {"a": {}}}, {"tables": {"b": {}}}]
        )

        service = SchemaService(mock_db, cache_ttl_seconds=300)

        await service.get_database_schema()
        refreshed = await service.refresh()

        assert "b" in refreshed["tables"]
        assert mock_db.aget_database_schema.await_count == 2

    @pytest.mark.anyio
    async def test_invalidate_triggers_reinspection(self):
        """invalidate() should drop the cache so the next read re-inspects."""
        mock_db = Mock()
        mock_db.aget_database_schema = AsyncMock(
            side_effect=[{"tables": {"a": {}}}, {"tables": {"b": {}}}]
        )

        service = SchemaService(mock_db, cache_ttl_seconds=300)

        await service.get_database_schema()
        service.invalidate()
        again = await service.get_database_schema()

        assert "b" in again["tables"]
        assert mock_db.aget_database_schema.await_count == 2

    @pytest.mark.anyio
    async def test_expired_cache_reinspects(self):
        """A zero TTL makes every read stale, forcing re-inspection."""
        mock_db = Mock()
        mock_db.aget_database_schema = AsyncMock(
            side_effect=[{"tables": {"a": {}}}, {"tables": {"b": {}}}]
        )

        service = SchemaService(mock_db, cache_ttl_seconds=0)

        await service.get_database_schema()
        await service.get_database_schema()

        assert mock_db.aget_database_schema.await_count == 2
