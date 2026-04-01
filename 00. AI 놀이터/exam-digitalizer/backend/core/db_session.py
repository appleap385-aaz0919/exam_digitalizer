"""에이전트용 DB 세션 헬퍼

에이전트가 process() 내에서 DB에 직접 쓸 때 사용합니다.
"""
from contextlib import asynccontextmanager

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings

_engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
_async_session = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


@asynccontextmanager
async def get_agent_db():
    """에이전트용 DB 세션 컨텍스트 매니저"""
    async with _async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
