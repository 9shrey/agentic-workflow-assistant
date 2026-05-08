from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from app.config import settings

SYNC_DATABASE_URL = settings.database_url.replace("+aiosqlite", "")

sync_engine = create_engine(SYNC_DATABASE_URL, echo=False)
async_engine = create_async_engine(settings.database_url, echo=False)

async_session_factory = async_sessionmaker(
    async_engine, class_=AsyncSession, expire_on_commit=False
)


class Base(DeclarativeBase):
    pass


def init_db():
    from app.models import audit_log, approval, contact_memory, workflow_run  # noqa: F401
    Base.metadata.create_all(sync_engine)


async def get_db() -> AsyncSession:
    async with async_session_factory() as session:
        try:
            yield session
        finally:
            await session.close()
