"""Async engine / session factory."""
from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.database.models import Base


def normalize_url(url: str) -> str:
    """Allow plain postgres:// or postgresql:// URLs by selecting the asyncpg driver."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+asyncpg://" + url[len(prefix):]
    return url


def create_session_factory(url: str) -> tuple[AsyncEngine, async_sessionmaker[AsyncSession]]:
    engine = create_async_engine(normalize_url(url), pool_pre_ping=True)
    return engine, async_sessionmaker(engine, expire_on_commit=False)


async def init_db(engine: AsyncEngine) -> None:
    """Create tables if missing. (Alembic migrations are planned for a later phase.)"""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
