from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from config import get_settings

engine = create_async_engine(
    get_settings().database_url,
    echo=True,
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    expire_on_commit=False,
)


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
