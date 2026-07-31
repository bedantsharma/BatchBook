import time

from loguru import logger
from sqlalchemy import event
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import Settings, get_settings
from telemetry import instrument_engine

# Supabase routes Postgres through Supavisor, its connection pooler:
#   port 5432 on *.pooler.supabase.com -> session mode
#   port 6543 on *.pooler.supabase.com -> transaction mode
# asyncpg caches server-side prepared statements per connection, which breaks
# against a pooler that can hand the same client a different backend between
# statements ("prepared statement _pgN already exists"). Disabling the cache is
# mandatory for transaction mode and harmless in session mode -- asyncpg falls
# back to unnamed prepared statements, which cost one round trip per query
# instead of the two a prepare+execute pair costs on a cold connection.
_SUPAVISOR_HOST = "pooler.supabase.com"


def is_pooled_postgres(database_url: str) -> bool:
    """True when the URL points at Supabase's Supavisor pooler."""
    return _SUPAVISOR_HOST in database_url


def build_engine_kwargs(settings: Settings) -> dict:
    """Assemble create_async_engine kwargs for the configured DATABASE_URL.

    Split out from the module-level engine construction so the pooling policy
    is unit-testable without opening a real connection.
    """
    database_url = settings.database_url
    kwargs: dict = {"echo": settings.db_echo}

    # Pool sizing only applies to real connection pools (asyncpg, not SQLite).
    if database_url.startswith("sqlite"):
        return kwargs

    kwargs.update(
        {
            "pool_size": settings.db_pool_size,
            "max_overflow": settings.db_max_overflow,
            "pool_pre_ping": settings.db_pool_pre_ping,
            "pool_recycle": settings.db_pool_recycle,
        }
    )

    if is_pooled_postgres(database_url):
        kwargs["connect_args"] = {"statement_cache_size": 0}

    return kwargs


def register_pool_diagnostics(sync_engine) -> None:
    """Log every pool lifecycle event so connection churn is visible in Grafana.

    Traces only show `Engine.connect()` (a pool *checkout*), which cannot
    distinguish "reused a warm connection" from "opened a new socket". These
    listeners record the difference directly: a `connect` event means a real
    physical connection was established.
    """

    @event.listens_for(sync_engine, "connect")
    def _on_connect(dbapi_connection, connection_record):
        connection_record.info["opened_at"] = time.perf_counter()
        logger.bind(db_pool_event="connect", **_pool_stats(sync_engine)).info(
            "db pool: opened a new physical connection"
        )

    @event.listens_for(sync_engine, "checkout")
    def _on_checkout(dbapi_connection, connection_record, connection_proxy):
        logger.bind(db_pool_event="checkout", **_pool_stats(sync_engine)).debug(
            "db pool: connection checked out"
        )

    @event.listens_for(sync_engine, "checkin")
    def _on_checkin(dbapi_connection, connection_record):
        logger.bind(db_pool_event="checkin", **_pool_stats(sync_engine)).debug(
            "db pool: connection returned to pool"
        )

    @event.listens_for(sync_engine, "close")
    def _on_close(dbapi_connection, connection_record):
        opened_at = connection_record.info.get("opened_at")
        logger.bind(
            db_pool_event="close",
            lifetime_s=round(time.perf_counter() - opened_at, 2) if opened_at else None,
            **_pool_stats(sync_engine),
        ).info("db pool: physical connection closed")

    @event.listens_for(sync_engine, "invalidate")
    def _on_invalidate(dbapi_connection, connection_record, exception):
        logger.bind(
            db_pool_event="invalidate",
            exception=repr(exception) if exception else None,
            **_pool_stats(sync_engine),
        ).warning("db pool: connection invalidated")


def _pool_stats(sync_engine) -> dict:
    """Current pool occupancy, best-effort -- not every pool class exposes these."""
    pool = sync_engine.pool
    stats = {}
    for attr in ("size", "checkedin", "checkedout", "overflow"):
        getter = getattr(pool, attr, None)
        if callable(getter):
            try:
                stats[f"pool_{attr}"] = getter()
            except (AttributeError, TypeError):
                pass
    return stats


_settings = get_settings()

engine = create_async_engine(
    _settings.database_url,
    **build_engine_kwargs(_settings),
)
instrument_engine(engine)

if _settings.db_log_pool_events:
    register_pool_diagnostics(engine.sync_engine)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
