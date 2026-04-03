"""파이프라인 복구 스크립트

멈춘(ERROR) 파이프라인을 현재 스테이지에서 재시도합니다.

사용법:
  # 특정 배치 재시도
  python scripts/retry_pipeline.py QI-202604-001

  # 모든 ERROR 상태 문항 재시도
  python scripts/retry_pipeline.py --all
"""
import asyncio
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from core.queue import get_redis, publish_task, PIPELINE_TASKS_STREAM, setup_streams
from models.pipeline import PipelineState
from models.question import Question, QuestionRaw, QuestionStructured, QuestionProduced

logger = structlog.get_logger()

STAGE_AGENT_MAP = {
    "PARSING": "a01_parser",
    "PARSE_REVIEW": "a02_parse_reviewer",
    "META": "a03_meta",
    "META_REVIEW": "a04_meta_reviewer",
    "PRODUCTION": "a05_producer",
    "PROD_REVIEW": "a06_prod_reviewer",
    "DATA": "a07_data",
    "DATA_REVIEW": "a08_data_reviewer",
}


async def retry(batch_id: str | None = None, retry_all: bool = False):
    engine = create_async_engine(settings.DATABASE_URL)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    redis = await get_redis()
    await setup_streams(redis)

    async with async_session() as db:
        query = select(Question)
        if batch_id:
            query = query.where(Question.batch_id == batch_id)

        result = await db.execute(query)
        questions = result.scalars().all()

        retried = 0
        for q in questions:
            # PipelineState 확인
            ps = (await db.execute(
                select(PipelineState).where(PipelineState.ref_id == q.pkey)
            )).scalar_one_or_none()

            # ERROR 상태이거나, --all이면 현재 스테이지에서 재시도
            if not retry_all and ps and ps.status != "ERROR":
                continue

            stage = q.current_stage
            agent = STAGE_AGENT_MAP.get(stage)
            if not agent:
                continue

            # payload 구성
            payload = {"pkey": q.pkey, "batch_id": q.batch_id, "ref_id": q.pkey}

            if stage in ("PRODUCTION", "META_REVIEW"):
                sq = (await db.execute(
                    select(QuestionStructured).where(QuestionStructured.pkey == q.pkey)
                )).scalar_one_or_none()
                if sq:
                    payload["structured_question"] = {
                        "pkey": q.pkey,
                        "question_text": sq.question_text or "",
                        "segments": [], "choices": [], "metadata": {},
                    }

            if stage == "PROD_REVIEW":
                produced = (await db.execute(
                    select(QuestionProduced).where(QuestionProduced.pkey == q.pkey)
                )).scalar_one_or_none()
                if produced:
                    payload["digital_question"] = {
                        "pkey": q.pkey,
                        "content_html": produced.content_html,
                        "content_latex": produced.content_latex,
                        "answer_correct": produced.answer_correct,
                        "answer_source": produced.answer_source,
                        "solution": {},
                        "render_html": produced.render_html,
                        "metadata": {},
                        "choices": [],
                    }

            if stage in ("META", "PARSE_REVIEW"):
                raw = (await db.execute(
                    select(QuestionRaw).where(QuestionRaw.pkey == q.pkey)
                )).scalar_one_or_none()
                if raw:
                    payload["raw_question"] = {"raw_text": raw.raw_text or ""}

            # PipelineState 복구
            if ps and ps.status == "ERROR":
                ps.status = "IN_PROGRESS"

            await publish_task(
                redis, PIPELINE_TASKS_STREAM, agent, q.pkey, "L1", payload, stage=stage,
            )
            retried += 1
            print(f"  Retry: {q.pkey} [{stage}] -> {agent}")

        await db.commit()

    await engine.dispose()
    await redis.aclose()
    print(f"\nDone. {retried}/{len(questions)} questions retried.")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/retry_pipeline.py <batch_id> | --all")
        sys.exit(1)

    arg = sys.argv[1]
    if arg == "--all":
        asyncio.run(retry(retry_all=True))
    else:
        asyncio.run(retry(batch_id=arg))
