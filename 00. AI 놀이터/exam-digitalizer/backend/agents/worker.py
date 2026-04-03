"""Worker 진입점 — Redis Stream 소비자 (replicas:2)

모든 에이전트를 하나의 워커 프로세스에서 실행합니다.
pipeline:tasks 스트림에서 메시지를 읽고, agent 필드를 보고 해당 에이전트로 디스패치합니다.
"""
import asyncio
import os
import time

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


def _build_agent_registry() -> dict:
    """14개 에이전트 + 더미 에이전트 인스턴스 맵 생성"""
    from agents.a01_parser import ParserAgent
    from agents.a02_parse_reviewer import ParseReviewerAgent
    from agents.a03_meta import MetaAgent
    from agents.a04_meta_reviewer import MetaReviewerAgent
    from agents.a05_producer import ProducerAgent
    from agents.a06_prod_reviewer import ProdReviewerAgent
    from agents.a07_data import DataAgent
    from agents.a08_data_reviewer import DataReviewerAgent
    from agents.a09_exam_composer import ExamComposerAgent
    from agents.a10_exam_reviewer import ExamReviewerAgent
    from agents.a11_service import ServiceAgent
    from agents.a12_service_reviewer import ServiceReviewerAgent
    from agents.a13_grader import GraderAgent
    from agents.a14_grade_reviewer import GradeReviewerAgent
    from agents.embedding_agent import EmbeddingAgent
    from agents.dummy_agent import DummyAgent, DummyReviewer

    return {
        "a01_parser": ParserAgent(),
        "a02_parse_reviewer": ParseReviewerAgent(),
        "a03_meta": MetaAgent(),
        "a04_meta_reviewer": MetaReviewerAgent(),
        "a05_producer": ProducerAgent(),
        "a06_prod_reviewer": ProdReviewerAgent(),
        "a07_data": DataAgent(),
        "a08_data_reviewer": DataReviewerAgent(),
        "a09_exam_composer": ExamComposerAgent(),
        "a10_exam_reviewer": ExamReviewerAgent(),
        "a11_service": ServiceAgent(),
        "a12_service_reviewer": ServiceReviewerAgent(),
        "a13_grader": GraderAgent(),
        "a14_grade_reviewer": GradeReviewerAgent(),
        # 임베딩
        "embedding": EmbeddingAgent(),
        # 더미 (테스트/폴백)
        "dummy": DummyAgent(),
        "dummy_reviewer": DummyReviewer(),
    }


async def main():
    worker_id = os.environ.get("WORKER_ID", os.environ.get("HOSTNAME", "0"))
    consumer_name = f"worker-{worker_id}"

    redis = await get_redis()
    await setup_streams(redis)

    registry = _build_agent_registry()
    agent_names = list(registry.keys())

    logger.info(
        "worker_started",
        worker_id=worker_id,
        consumer=consumer_name,
        agents=agent_names,
    )

    while True:
        try:
            messages = await consume_tasks(
                redis,
                group=AGENT_WORKERS_GROUP,
                consumer=consumer_name,
                stream=PIPELINE_TASKS_STREAM,
                count=1,
                block_ms=5000,
            )

            for msg_id, fields in messages:
                agent_name = fields.get("agent", "")
                task_id = fields.get("task_id", "unknown")
                ref_id = fields.get("ref_id", "")
                level = fields.get("level", "L1")
                stage = fields.get("stage", "")
                payload = fields.get("payload", {})

                agent = registry.get(agent_name)
                if not agent:
                    logger.warning(
                        "unknown_agent",
                        agent=agent_name,
                        task_id=task_id,
                        ref_id=ref_id,
                    )
                    # ACK + ERROR 결과 반환
                    await publish_result(
                        redis, task_id=task_id, agent=agent_name,
                        ref_id=ref_id, level=level, stage=stage,
                        result="ERROR",
                        reject_reason=f"알 수 없는 에이전트: {agent_name}",
                    )
                    await ack_task(redis, PIPELINE_TASKS_STREAM, AGENT_WORKERS_GROUP, msg_id)
                    continue

                log = logger.bind(
                    agent=agent_name, task_id=task_id,
                    ref_id=ref_id, worker=consumer_name,
                )
                log.info("task_dispatched")

                start_time = time.time()
                try:
                    # 타임아웃 래핑
                    result_data = await asyncio.wait_for(
                        agent.process(payload),
                        timeout=settings.AGENT_TIMEOUT_SECONDS,
                    )
                    duration_ms = int((time.time() - start_time) * 1000)
                    log.info(
                        "task_completed",
                        result=result_data.get("result"),
                        score=result_data.get("score"),
                        duration_ms=duration_ms,
                    )
                except asyncio.TimeoutError:
                    duration_ms = int((time.time() - start_time) * 1000)
                    log.error("task_timeout", duration_ms=duration_ms)
                    result_data = {
                        "result": "ERROR",
                        "reject_reason": f"타임아웃 ({settings.AGENT_TIMEOUT_SECONDS}s)",
                    }
                except Exception as e:
                    duration_ms = int((time.time() - start_time) * 1000)
                    log.error("task_error", error=str(e), duration_ms=duration_ms)
                    result_data = {"result": "ERROR", "reject_reason": str(e)}

                # 결과 발행
                await publish_result(
                    redis,
                    task_id=task_id,
                    agent=agent_name,
                    ref_id=ref_id,
                    level=level,
                    stage=stage,
                    result=result_data.get("result", "ERROR"),
                    score=result_data.get("score"),
                    score_detail=result_data.get("score_detail"),
                    reject_reason=result_data.get("reject_reason"),
                )

                # ACK
                await ack_task(redis, PIPELINE_TASKS_STREAM, AGENT_WORKERS_GROUP, msg_id)

        except Exception as e:
            logger.error("worker_loop_error", error=str(e))
            await asyncio.sleep(1)


if __name__ == "__main__":
    asyncio.run(main())
