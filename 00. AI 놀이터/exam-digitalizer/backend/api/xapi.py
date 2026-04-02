"""xAPI 학습 이벤트 수집 API

POST /api/v1/xapi/events  — xAPI 이벤트 저장 (비인증 — 학생 접속용)
GET  /api/v1/xapi/events  — 이벤트 조회 (교사 전용)
"""
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, get_redis

router = APIRouter()
logger = structlog.get_logger()

# 간이 저장소 (프로덕션에서는 LRS로 전송)
# Redis에 리스트로 저장
XAPI_KEY = "xapi:events"


class XApiEvent(BaseModel):
    verb: str
    actor: str | None = None
    object_id: str | None = None
    object_type: str | None = None
    result: dict | None = None
    context: dict | None = None
    timestamp: str | None = None


@router.post("/events")
async def store_xapi_event(
    event: XApiEvent,
    redis=Depends(get_redis),
):
    """xAPI 이벤트 저장 (Redis 리스트)"""
    import json

    record = {
        "verb": event.verb,
        "actor": event.actor,
        "object": {"id": event.object_id, "type": event.object_type},
        "result": event.result,
        "context": event.context,
        "timestamp": event.timestamp or datetime.now(timezone.utc).isoformat(),
    }
    await redis.rpush(XAPI_KEY, json.dumps(record, ensure_ascii=False))
    logger.info("xapi_event_stored", verb=event.verb, object_id=event.object_id)
    return {"stored": True}


@router.get("/events")
async def get_xapi_events(
    limit: int = 50,
    redis=Depends(get_redis),
):
    """xAPI 이벤트 조회 (최근 N개)"""
    import json

    raw = await redis.lrange(XAPI_KEY, -limit, -1)
    events = [json.loads(r) for r in raw]
    return {"data": events, "total": await redis.llen(XAPI_KEY)}
