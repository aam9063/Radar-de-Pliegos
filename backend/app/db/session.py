from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import get_settings

_engine: AsyncEngine | None = None
_session_maker: async_sessionmaker[AsyncSession] | None = None


def _get_session_maker() -> async_sessionmaker[AsyncSession]:
    """Create the engine lazily so importing this module has no side effects."""
    global _engine, _session_maker
    if _engine is None or _session_maker is None:
        _engine = create_async_engine(get_settings().database_url)
        _session_maker = async_sessionmaker(_engine, expire_on_commit=False)
    return _session_maker


async def get_session() -> AsyncIterator[AsyncSession]:
    async with _get_session_maker()() as session:
        yield session
