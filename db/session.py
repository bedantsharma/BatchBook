from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import get_settings

# When switching DATABASE_URL to Supabase's Supavisor transaction-mode pooler
# (port 6543), also add: connect_args={"statement_cache_size": 0}
# to avoid "prepared statement already exists" errors under load.
_engine_kwargs = {
    "echo": get_settings().db_echo,
}

# Pool parameters only apply to real connection pools (asyncpg, not SQLite)
if not get_settings().database_url.startswith("sqlite"):
    _engine_kwargs.update(
        {
            "pool_size": get_settings().db_pool_size,
            "max_overflow": get_settings().db_max_overflow,
            "pool_pre_ping": True,
            "pool_recycle": get_settings().db_pool_recycle,
        }
    )

engine = create_async_engine(
    get_settings().database_url,
    **_engine_kwargs,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
