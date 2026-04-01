"""BaseAgent — 모든 에이전트의 공통 베이스 클래스"""
import asyncio
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

import structlog

from config import settings
from core.queue import (
    AGENT_WORKERS_GROUP,
    PIPELINE_TASKS_STREAM,
    ack_task,
    consume_tasks,
    get_redis,
    publish_result,
    setup_streams,
)

logger = structlog.get_logger()

HEARTBEAT_INTERVAL = 30  # 초


class AgentResult:
    PASS = "PASS"
    REJECT = "REJECT"
    ERROR = "ERROR"


class BaseAgent(ABC):
    """Redis Stream에서 메시지를 수신하고 처리하는 에이전트 베이스 클래스"""

    agent_name: str = "base"

    def __init__(self, worker_id: str = "0"):
        self.consumer_name = f"{self.agent_name}-{worker_id}"
        self._running = False

    @abstractmethod
    async def process(self, payload: dict[str, Any]) -> dict:
        """
        실제 처리 로직. 서브클래스에서 구현.

        반환값:
        {
            "result": "PASS" | "REJECT" | "ERROR",
            "score": float | None,
            "score_detail": dict | None,
            "reject_reason": str | None,
        }
        """
        raise NotImplementedError

    async def run(self) -> None:
        """메인 루프 — Redis Stream 소비"""
        redis = await get_redis()
        await setup_streams(redis)
        self._running = True

        # Heartbeat 비동기 태스크 시작
        heartbeat_task = asyncio.create_task(self._send_heartbeats(redis))

        logger.info("agent_started", agent=self.agent_name, consumer=self.consumer_name)
        try:
            while self._running:
                messages = await consume_tasks(
                    redis,
                    group=AGENT_WORKERS_GROUP,
                    consumer=self.consumer_name,
                    stream=PIPELINE_TASKS_STREAM,
                    count=1,
                    block_ms=5000,
                )
                for msg_id, fields in messages:
                    # 이 에이전트 대상 메시지만 처리
                    if fields.get("agent") != self.agent_name:
                        # 다른 에이전트 메시지 → ACK 없이 스킵 (PEL 유지)
                        continue

                    await self._handle_message(redis, msg_id, fields)
        finally:
            heartbeat_task.cancel()
            logger.info("agent_stopped", agent=self.agent_name)

    async def _handle_message(self, redis, msg_id: str, fields: dict) -> None:
        task_id = fields.get("task_id", "unknown")
        ref_id = fields.get("ref_id", "")
        level = fields.get("level", "L1")
        stage = fields.get("stage", "")
        payload = fields.get("payload", {})

        log = logger.bind(agent=self.agent_name, task_id=task_id, ref_id=ref_id)
        log.info("task_received", stage=stage)

        start_time = time.time()
        try:
            # 타임아웃 래퍼 (300초)
            result_data = await asyncio.wait_for(
                self.process(payload),
                timeout=settings.AGENT_TIMEOUT_SECONDS,
            )
            duration_ms = int((time.time() - start_time) * 1000)
            log.info(
                "task_processed",
                result=result_data.get("result"),
                score=result_data.get("score"),
                duration_ms=duration_ms,
            )
        except asyncio.TimeoutError:
            duration_ms = int((time.time() - start_time) * 1000)
            log.error("task_timeout", duration_ms=duration_ms)
            result_data = {"result": AgentResult.ERROR, "reject_reason": f"타임아웃 ({settings.AGENT_TIMEOUT_SECONDS}s)"}
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            log.error("task_error", error=str(e), duration_ms=duration_ms)
            result_data = {"result": AgentResult.ERROR, "reject_reason": str(e)}

        # 결과 발행
        await publish_result(
            redis,
            task_id=task_id,
            agent=self.agent_name,
            ref_id=ref_id,
            level=level,
            stage=stage,
            result=result_data.get("result", AgentResult.ERROR),
            score=result_data.get("score"),
            score_detail=result_data.get("score_detail"),
            reject_reason=result_data.get("reject_reason"),
        )

        await ack_task(redis, PIPELINE_TASKS_STREAM, AGENT_WORKERS_GROUP, msg_id)

    async def _send_heartbeats(self, redis) -> None:
        """30초마다 HEARTBEAT 전송"""
        while True:
            try:
                await redis.setex(
                    f"agent:heartbeat:{self.consumer_name}",
                    HEARTBEAT_INTERVAL * 2,
                    datetime.now(timezone.utc).isoformat(),
                )
            except Exception as e:
                logger.error("heartbeat_failed", agent=self.agent_name, error=str(e))
            await asyncio.sleep(HEARTBEAT_INTERVAL)
