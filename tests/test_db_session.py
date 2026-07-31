"""Covers the pooling policy in db/session.py.

Production traces showed a ~280ms `Engine.connect()` span on nearly every
request -- the cost of a fresh TCP+TLS+auth handshake, meaning pooled
connections were not surviving checkin. These tests pin the configuration that
governs that behaviour so a future edit can't silently drop pooling again.
"""

from config import Settings
from db.session import build_engine_kwargs, is_pooled_postgres

POOLER_URL = (
    "postgresql+asyncpg://postgres.abc:pw@aws-1-ap-southeast-2.pooler.supabase.com:5432/postgres"
)
DIRECT_URL = "postgresql+asyncpg://postgres:pw@db.abc.supabase.co:5432/postgres"


def _settings(database_url: str, **overrides) -> Settings:
    defaults = {
        "project_name": "BatchBook-Test",
        "database_url": database_url,
        "supabase_url": "https://test.supabase.co",
        "supabase_key": "test-key",
    }
    return Settings(**{**defaults, **overrides})


class TestIsPooledPostgres:
    def test_detects_supavisor_pooler_host(self):
        assert is_pooled_postgres(POOLER_URL) is True

    def test_direct_connection_is_not_pooled(self):
        assert is_pooled_postgres(DIRECT_URL) is False

    def test_sqlite_is_not_pooled(self):
        assert is_pooled_postgres("sqlite+aiosqlite:///:memory:") is False


class TestBuildEngineKwargs:
    def test_sqlite_gets_no_pool_settings(self):
        # SQLite uses a non-queue pool; passing pool_size to it raises TypeError.
        kwargs = build_engine_kwargs(_settings("sqlite+aiosqlite:///:memory:"))

        assert kwargs == {"echo": False}

    def test_postgres_gets_pool_settings(self):
        kwargs = build_engine_kwargs(_settings(DIRECT_URL))

        assert kwargs["pool_size"] == 5
        assert kwargs["max_overflow"] == 10
        assert kwargs["pool_recycle"] == 1800
        assert kwargs["pool_pre_ping"] is True

    def test_pool_settings_are_config_driven(self):
        kwargs = build_engine_kwargs(
            _settings(DIRECT_URL, db_pool_size=20, db_max_overflow=0, db_pool_recycle=300)
        )

        assert kwargs["pool_size"] == 20
        assert kwargs["max_overflow"] == 0
        assert kwargs["pool_recycle"] == 300

    def test_pre_ping_can_be_disabled(self):
        kwargs = build_engine_kwargs(_settings(DIRECT_URL, db_pool_pre_ping=False))

        assert kwargs["pool_pre_ping"] is False

    def test_pooler_url_disables_asyncpg_statement_cache(self):
        # Supavisor can hand the same client a different backend between
        # statements; a per-connection prepared-statement cache breaks on that.
        kwargs = build_engine_kwargs(_settings(POOLER_URL))

        assert kwargs["connect_args"] == {"statement_cache_size": 0}

    def test_direct_url_keeps_statement_cache(self):
        # No pooler in front means prepared statements are safe and worth keeping.
        kwargs = build_engine_kwargs(_settings(DIRECT_URL))

        assert "connect_args" not in kwargs

    def test_sqlite_never_gets_asyncpg_connect_args(self):
        kwargs = build_engine_kwargs(_settings("sqlite+aiosqlite:///:memory:"))

        assert "connect_args" not in kwargs


class TestPoolDiagnostics:
    def test_registers_without_error_on_a_real_engine(self):
        from sqlalchemy.ext.asyncio import create_async_engine

        from db.session import register_pool_diagnostics

        eng = create_async_engine("sqlite+aiosqlite:///:memory:")
        register_pool_diagnostics(eng.sync_engine)  # must not raise

    async def test_logs_a_connect_event_on_first_use(self):
        from sqlalchemy import text
        from sqlalchemy.ext.asyncio import create_async_engine

        from db.session import register_pool_diagnostics

        events = []
        eng = create_async_engine("sqlite+aiosqlite:///:memory:")
        register_pool_diagnostics(eng.sync_engine)

        from loguru import logger

        sink_id = logger.add(
            lambda m: events.append(m.record["extra"].get("db_pool_event")), level="DEBUG"
        )
        try:
            async with eng.connect() as conn:
                await conn.execute(text("SELECT 1"))
        finally:
            logger.remove(sink_id)
            await eng.dispose()

        assert "connect" in events
        assert "checkout" in events
