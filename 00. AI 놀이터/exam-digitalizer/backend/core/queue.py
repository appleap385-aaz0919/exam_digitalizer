"""Redis Streams 메시지 큐 유틸리티"""
import json
import uuid
from datetime import datetime, timezone
from typing import Any, Optional

import redis.asyncio as aioredis
import structlog

from config import settings

logger = structlog.get_logger()

# Stream 및 Consumer Group 이름
PIPELINE_TASKS_STREAM = "pipeline:tasks"
PIPELINE_RESULTS_STREAM = "pipeline:results"
AGENT_WORKERS_GROUP = "agent-workers"
ORCHESTRATOR_GROUP = "orchestrator"


async def get_redis() -> aioredis.Redis:
    return aioredis.from_url(settings.REDIS_URL, decode_responses=True)


async def setup_streams(redis: aioredis.Redis) -> None:
    """Stream과 Consumer Group 초기화"""
    for stream, group in [
        (PIPELINE_TASKS_STREAM, AGENT_WORKERS_GROUP),
        (PIPELINE_RESULTS_STREAM, ORCHESTRATOR_GROUP),
    ]:
        try:
            # Stream이 없으면 더미 메시지로 생성
            await redis.xadd(stream, {"init": "1"}, id="0-1")
        except Exception:
            pass
        try:
            await redis.xgroup_create(stream, group, id="0", mkstream=True)
            logger.info("stream_group_created", stream=stream, group=group)
        except Exception as e:
            if "BUSYGROUP" in str(e):
                logger.debug("stream_group_already_exists", stream=stream, group=group)
            else:
                logger.error("stream_group_create_failed", stream=stream, group=group, error=str(e))


async def publish_task(
    redis: aioredis.Redis,
    stream: str,
    agent: str,
    ref_id: str,
    level: str,
    payload: dict[str, Any],
    stage: str = "",
) -> str:
    """파이프라인 작업 발행 → XADD → message_id 반환"""
    task_id = str(uuid.uuid4())
    message = {
        "task_id": task_id,
        "agent": agent,
        "ref_id": ref_id,
        "level": level,  # L1 / L2A / L2B
        "stage": stage,  # PARSING / META / PRODUCTION 등
        "payload": json.dumps(payload),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    msg_id = await redis.xadd(stream, message)
    logger.info("task_published", task_id=task_id, agent=agent, ref_id=ref_id, stage=stage, msg_id=msg_id)
    return msg_id


async def consume_tasks(
    redis: aioredis.Redis,
    group: str,
    consumer: str,
    stream: str,
    count: int = 1,
    block_ms: int = 5000,
) -> list[tuple[str, dict]]:
    """XREADGROUP으로 메시지 소비 → [(msg_id, fields), ...]"""
    try:
        results = await redis.xreadgroup(
            groupname=group,
            consumername=consumer,
            streams={stream: ">"},
            count=count,
            block=block_ms,
        )
        if not results:
            return []
        # results = [(stream_name, [(msg_id, fields), ...])]
        messages = []
        for _, msgs in results:
            for msg_id, fields in msgs:
                if "payload" in fields:
                    fields["payload"] = json.loads(fields["payload"])
                messages.append((msg_id, fields))
        return messages
    except Exception as e:
        logger.error("consume_tasks_failed", stream=stream, group=group, error=str(e))
        return []


async def ack_task(
    redis: aioredis.Redis,
    stream: str,
    group: str,
    message_id: str,
) -> None:
    """메시지 처리 완료 ACK"""
    await redis.xack(stream, group, message_id)
    logger.debug("task_acked", stream=stream, group=group, message_id=message_id)


async def publish_result(
    redis: aioredis.Redis,
    task_id: str,
    agent: str,
    ref_id: str,
    level: str,
    stage: str,
    result: str,  # PASS / REJECT / ERROR
    score: Optional[float] = None,
    score_detail: Optional[dict] = None,
    reject_reason: Optional[str] = None,
) -> str:
    """에이전트 처리 결과 발행"""
    message = {
        "task_id": task_id,
        "agent": agent,
        "ref_id": ref_id,
        "level": level,
        "stage": stage,
        "result": result,
        "score": str(score) if score is not None else "",
        "score_detail": json.dumps(score_detail or {}),
        "reject_reason": reject_reason or "",
        "completed_at": datetime.now(timezone.utc).isoformat(),
    }
    msg_id = await redis.xadd(PIPELINE_RESULTS_STREAM, message)
    logger.info(
        "result_published",
        task_id=task_id,
        agent=agent,
        ref_id=ref_id,
        result=result,
        score=score,
    )
    return msg_id
