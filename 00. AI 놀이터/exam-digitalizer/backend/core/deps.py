"""FastAPI 의존성 주입 — 인증/권한"""
import secrets

import redis.asyncio as aioredis
import structlog
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jose import JWTError
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from core.security import decode_token

logger = structlog.get_logger()

# ─── DB 세션 ──────────────────────────────────────────────────────
_engine = create_async_engine(settings.DATABASE_URL, echo=False, pool_pre_ping=True)
AsyncSessionLocal = sessionmaker(_engine, class_=AsyncSession, expire_on_commit=False)


async def get_db() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session


# ─── Redis 클라이언트 ─────────────────────────────────────────────
_redis_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    global _redis_client
    if _redis_client is None:
        _redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    return _redis_client


# ─── JWT 디펜던시 ─────────────────────────────────────────────────
bearer_scheme = HTTPBearer()


def _get_user_from_token(token: str) -> dict:
    try:
        payload = decode_token(token)
        if payload.get("type") != "access":
            raise ValueError("access token이 아닙니다")
        return payload
    except (JWTError, ValueError) as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": str(e)},
        )


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> dict:
    return _get_user_from_token(credentials.credentials)


def require_role(*roles: str):
    """역할 기반 접근 제어 데코레이터 팩토리"""
    async def _check_role(current_user: dict = Depends(get_current_user)) -> dict:
        if current_user.get("role") not in roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"error_code": "FORBIDDEN", "message": "접근 권한이 없습니다"},
            )
        return current_user
    return _check_role


# ─── 학생 토큰 디펜던시 ───────────────────────────────────────────
async def get_current_student(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
    redis: aioredis.Redis = Depends(get_redis),
) -> dict:
    token = credentials.credentials
    key = f"student_token:{token}"
    data = await redis.hgetall(key)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": "UNAUTHORIZED", "message": "유효하지 않은 학생 토큰입니다"},
        )
    return data


require_admin = require_role("ADMIN")
require_teacher = require_role("ADMIN", "TEACHER")
