"""알림 API

GET   /api/v1/notifications          — 내 알림 목록
PATCH /api/v1/notifications/{id}/read — 읽음 처리
GET   /api/v1/notifications/unread-count — 안 읽은 알림 수
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, get_current_user
from models.notification import Notification

router = APIRouter()


@router.get("")
async def list_notifications(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    offset = (page - 1) * limit
    user_id = int(current_user["sub"])

    total = (await db.execute(
        select(func.count()).select_from(Notification).where(Notification.user_id == user_id)
    )).scalar() or 0

    result = await db.execute(
        select(Notification).where(Notification.user_id == user_id)
        .order_by(Notification.created_at.desc()).offset(offset).limit(limit)
    )
    notifications = [
        {
            "id": n.id, "type": n.type, "title": n.title, "body": n.body,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in result.scalars()
    ]
    return {"data": notifications, "meta": {"total": total, "page": page, "limit": limit}}


@router.patch("/{notification_id}/read")
async def mark_as_read(
    notification_id: int,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    n = (await db.execute(
        select(Notification).where(
            Notification.id == notification_id,
            Notification.user_id == int(current_user["sub"]),
        )
    )).scalar_one_or_none()
    if n:
        n.is_read = True
        n.read_at = datetime.now(timezone.utc)
        await db.commit()
    return {"id": notification_id, "is_read": True}


@router.get("/unread-count")
async def unread_count(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    count = (await db.execute(
        select(func.count()).select_from(Notification).where(
            Notification.user_id == int(current_user["sub"]),
            Notification.is_read.is_(False),
        )
    )).scalar() or 0
    return {"unread_count": count}
