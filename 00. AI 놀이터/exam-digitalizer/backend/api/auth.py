import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from jose import JWTError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, get_redis
from core.security import (
    create_access_token,
    create_refresh_token,
    decode_token,
    verify_password,
)
from models.user import User
from schemas.auth import LoginRequest, RefreshRequest, TokenResponse
from schemas.common import ErrorCode

router = APIRouter()
logger = structlog.get_logger()


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    # 사용자 조회
    result = await db.execute(
        select(User).where(User.email == request.email, User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()

    if not user or not verify_password(request.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "error_code": ErrorCode.UNAUTHORIZED,
                "message": "이메일 또는 비밀번호가 올바르지 않습니다",
            },
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"error_code": ErrorCode.FORBIDDEN, "message": "비활성화된 계정입니다"},
        )

    token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
    access_token = create_access_token(token_data)
    refresh_token = create_refresh_token(token_data)

    logger.info("user_login", user_id=user.id, role=user.role)
    return TokenResponse(access_token=access_token, refresh_token=refresh_token)


@router.post("/refresh", response_model=TokenResponse)
async def refresh_token(request: RefreshRequest, db: AsyncSession = Depends(get_db)):
    try:
        payload = decode_token(request.refresh_token)
        if payload.get("type") != "refresh":
            raise ValueError("refresh token이 아닙니다")
    except (JWTError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": ErrorCode.UNAUTHORIZED, "message": "유효하지 않은 refresh token"},
        )

    user_id = payload.get("sub")
    result = await db.execute(
        select(User).where(User.id == int(user_id), User.deleted_at.is_(None))
    )
    user = result.scalar_one_or_none()
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error_code": ErrorCode.UNAUTHORIZED, "message": "사용자를 찾을 수 없습니다"},
        )

    token_data = {"sub": str(user.id), "email": user.email, "role": user.role}
    return TokenResponse(
        access_token=create_access_token(token_data),
        refresh_token=create_refresh_token(token_data),
    )
