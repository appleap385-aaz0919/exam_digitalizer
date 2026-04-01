"""오케스트레이터 — 파이프라인의 두뇌 (단일 인스턴스, replicas:1)

pipeline:results Stream을 소비하여 상태 전이를 실행하고
pipeline:tasks에 다음 작업을 발행합니다.
"""
import asyncio
import json
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from config import settings
from core.queue import (
    ORCHESTRATOR_GROUP,
    PIPELINE_RESULTS_STREAM,
    PIPELINE_TASKS_STREAM,
    ack_task,
    consume_tasks,
    get_redis,
    publish_task,
    setup_streams,
)
from models.classroom import ClassroomExam
from models.pipeline import PipelineHistory, PipelineState

logger = structlog.get_logger()

# ─── L1 파이프라인 상태 전이표 ─────────────────────────────────────
L1_TRANSITIONS = {
    "PARSING":          ("PARSE_REVIEW",  "a02_parse_reviewer"),
    "PARSE_REVIEW":     ("META",          "a03_meta"),
    "META":             ("META_REVIEW",   "a04_meta_reviewer"),
    "META_REVIEW":      ("PRODUCTION",    "a05_producer"),
    "PRODUCTION":       ("PROD_REVIEW",   "a06_prod_reviewer"),
    # PROD_REVIEW 분기: answer_source == "ai_derived" → HUMAN_CONFIRM_ANSWER
    "PROD_REVIEW":      None,  # 특수 처리
    "HUMAN_CONFIRM":    ("DATA",          "a07_data"),
    "DATA":             ("DATA_REVIEW",   "a08_data_reviewer"),
    "DATA_REVIEW":      ("EMBEDDING",     "embedding"),
    "EMBEDDING":        ("L1_COMPLETED",  None),
}

# L1 반려 시 되돌아갈 스테이지
L1_REJECT_MAP = {
    "PARSE_REVIEW":  "PARSING",
    "META_REVIEW":   "META",
    "PROD_REVIEW":   "PRODUCTION",
    "DATA_REVIEW":   "DATA",
}

# L2-A 파이프라인
L2A_TRANSITIONS = {
    "EXAM_COMPOSE": ("EXAM_REVIEW", "a10_exam_reviewer"),
    "EXAM_REVIEW":  ("EXAM_CONFIRMED", None),
}
L2A_REJECT_MAP = {
    "EXAM_REVIEW": "EXAM_COMPOSE",
}

# L2-B 파이프라인
L2B_TRANSITIONS = {
    "DEPLOY_REQUESTED": ("HWP_GENERATING", "a11_service"),
    "HWP_GENERATING":   ("HWP_REVIEW",     "a12_service_reviewer"),
    "HWP_REVIEW":       ("DEPLOY_READY",   None),
    "DEPLOY_READY":     ("SCHEDULED",      None),
}
L2B_REJECT_MAP = {
    "HWP_REVIEW": "HWP_GENERATING",
}

HUMAN_REVIEW_THRESHOLD = 3
TIMEOUT_SECONDS = settings.AGENT_TIMEOUT_SECONDS


class Orchestrator:
    def __init__(self):
        engine = create_async_engine(settings.DATABASE_URL, echo=False)
        self.session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
        self.consumer_name = "orchestrator-0"

    async def run(self) -> None:
        redis = await get_redis()
        await setup_streams(redis)
        logger.info("orchestrator_started")

        while True:
            messages = await consume_tasks(
                redis,
                group=ORCHESTRATOR_GROUP,
                consumer=self.consumer_name,
                stream=PIPELINE_RESULTS_STREAM,
                count=10,
                block_ms=5000,
            )
            for msg_id, fields in messages:
                try:
                    await self._handle_result(redis, fields)
                    await ack_task(redis, PIPELINE_RESULTS_STREAM, ORCHESTRATOR_GROUP, msg_id)
                except Exception as e:
                    logger.error("orchestrator_handle_error", error=str(e), fields=fields)

    async def _handle_result(self, redis, fields: dict) -> None:
        ref_id = fields["ref_id"]
        level = fields["level"]
        stage = fields["stage"]
        result = fields["result"]  # PASS / REJECT / ERROR
        score = float(fields["score"]) if fields.get("score") else None
        score_detail = json.loads(fields.get("score_detail", "{}"))
        reject_reason = fields.get("reject_reason", "")

        async with self.session_factory() as db:
            if result == "PASS":
                await self._advance_stage(redis, db, ref_id, level, stage, score, score_detail)
            elif result == "REJECT":
                await self._reject_stage(redis, db, ref_id, level, stage, reject_reason, score, score_detail)
            elif result == "ERROR":
                await self._handle_error(db, ref_id, level, stage, reject_reason)

    async def _advance_stage(
        self, redis, db: AsyncSession,
        ref_id: str, level: str, stage: str,
        score: float | None, score_detail: dict,
    ) -> None:
        """성공: 다음 스테이지로 전이"""
        next_stage, next_agent = self._get_next_stage(level, stage, ref_id)

        if next_stage is None:
            # 파이프라인 완료
            await self._update_pipeline_state(db, ref_id, level, "COMPLETED", next_stage or stage, score)
            await self._record_history(db, ref_id, level, stage, stage, "COMPLETE", score, score_detail)
            logger.info("pipeline_completed", ref_id=ref_id, level=level)
            return

        await self._update_pipeline_state(db, ref_id, level, "IN_PROGRESS", next_stage, score)
        await self._record_history(db, ref_id, level, stage, next_stage, "ADVANCE", score, score_detail)

        if next_agent:
            # PARSE_REVIEW → META: 배치 단위 → 문항 단위로 분기
            if level == "L1" and stage == "PARSE_REVIEW" and next_stage == "META":
                await self._dispatch_per_question(redis, db, ref_id, next_agent, next_stage, level)
            else:
                payload = await self._assemble_payload(db, ref_id, level, next_stage)
                await publish_task(redis, PIPELINE_TASKS_STREAM, next_agent, ref_id, level, payload, stage=next_stage)
            logger.info("stage_advanced", ref_id=ref_id, from_stage=stage, to_stage=next_stage)

        # L2-B 상태 동기화 (v1.4 패치 #4)
        if level == "L2B":
            await self._sync_classroom_exam_status(db, ref_id, next_stage)

        await db.commit()

    async def _reject_stage(
        self, redis, db: AsyncSession,
        ref_id: str, level: str, stage: str,
        reject_reason: str, score: float | None, score_detail: dict,
    ) -> None:
        """반려: 해당 작업팀으로 되돌아가고 version+1"""
        reject_map = {
            "L1": L1_REJECT_MAP,
            "L2A": L2A_REJECT_MAP,
            "L2B": L2B_REJECT_MAP,
        }[level]

        prev_stage = reject_map.get(stage)
        if not prev_stage:
            logger.error("no_reject_stage_found", ref_id=ref_id, stage=stage)
            return

        # 연속 반려 횟수 증가
        state = await self._get_pipeline_state(db, ref_id, level)
        new_reject_count = (state.reject_count if state else 0) + 1

        if new_reject_count >= HUMAN_REVIEW_THRESHOLD:
            await self._update_pipeline_state(
                db, ref_id, level, "HUMAN_REVIEW", stage, score,
                reject_count=new_reject_count,
                reject_context={"reason": reject_reason, "stage": stage},
            )
            await self._record_history(db, ref_id, level, stage, "HUMAN_REVIEW", "HUMAN_REVIEW", score, score_detail)
            logger.warning(
                "human_review_triggered",
                ref_id=ref_id,
                level=level,
                reject_count=new_reject_count,
            )
        else:
            # version +1 (L1만)
            if level == "L1":
                await self._increment_question_version(db, ref_id)

            reject_agent = self._get_agent_for_stage(level, prev_stage)
            await self._update_pipeline_state(
                db, ref_id, level, "IN_PROGRESS", prev_stage, score,
                reject_count=new_reject_count,
                reject_context={"reason": reject_reason, "stage": stage},
            )
            await self._record_history(db, ref_id, level, stage, prev_stage, "REJECT", score, score_detail)

            if reject_agent:
                payload = await self._assemble_payload(db, ref_id, level, prev_stage)
                payload["reject_context"] = {"reason": reject_reason}
                await publish_task(redis, PIPELINE_TASKS_STREAM, reject_agent, ref_id, level, payload, stage=prev_stage)

        await db.commit()
        logger.info("stage_rejected", ref_id=ref_id, from_stage=stage, to_stage=prev_stage)

    async def _handle_error(
        self, db: AsyncSession,
        ref_id: str, level: str, stage: str, error_msg: str,
    ) -> None:
        await self._update_pipeline_state(db, ref_id, level, "ERROR", stage, None)
        await self._record_history(db, ref_id, level, stage, stage, "ERROR", None, {"error": error_msg})
        await db.commit()
        logger.error("pipeline_error", ref_id=ref_id, level=level, stage=stage, error=error_msg)

    async def _dispatch_per_question(
        self, redis, db: AsyncSession,
        batch_id: str, agent: str, stage: str, level: str,
    ) -> None:
        """배치 내 각 문항에 대해 개별 파이프라인 디스패치"""
        from models.question import Question, QuestionRaw

        questions = (await db.execute(
            select(Question).where(Question.batch_id == batch_id)
        )).scalars().all()

        for q in questions:
            raw = (await db.execute(
                select(QuestionRaw).where(QuestionRaw.pkey == q.pkey)
            )).scalar_one_or_none()

            formula_segs = (raw.formulas or {}).get("segments", []) if raw else []
            text_segs = [{"type": "text", "content": raw.raw_text or ""}] if raw else []

            payload = {
                "ref_id": q.pkey,
                "pkey": q.pkey,
                "batch_id": batch_id,
                "level": level,
                "stage": stage,
                "raw_question": {
                    "seq_num": q.seq_num,
                    "raw_text": raw.raw_text or "" if raw else "",
                    "segments": text_segs + formula_segs,
                    "choices": [],
                    "question_type": "단답형" if raw and raw.raw_text else "unknown",
                },
            }
            await publish_task(
                redis, PIPELINE_TASKS_STREAM, agent,
                ref_id=q.pkey, level=level, payload=payload, stage=stage,
            )
            logger.info("dispatched_per_question", pkey=q.pkey, agent=agent, stage=stage)

    def _get_next_stage(
        self, level: str, stage: str, ref_id: str = ""
    ) -> tuple[str | None, str | None]:
        """다음 스테이지와 에이전트 반환"""
        transitions = {"L1": L1_TRANSITIONS, "L2A": L2A_TRANSITIONS, "L2B": L2B_TRANSITIONS}[level]
        transition = transitions.get(stage)
        if transition is None:
            return None, None
        return transition

    def _get_agent_for_stage(self, level: str, stage: str) -> str | None:
        transitions = {"L1": L1_TRANSITIONS, "L2A": L2A_TRANSITIONS, "L2B": L2B_TRANSITIONS}[level]
        transition = transitions.get(stage)
        if not transition:
            return None
        return transition[1]

    async def _assemble_payload(
        self, db: AsyncSession, ref_id: str, level: str, stage: str
    ) -> dict:
        """v1.4 패치 #6: 오케스트레이터가 DB에서 에이전트 payload 조립

        각 스테이지별로 해당 에이전트가 필요한 데이터를 DB에서 가져와 전달합니다.
        """
        base = {
            "ref_id": ref_id,
            "pkey": ref_id,
            "level": level,
            "stage": stage,
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }

        try:
            if level == "L1":
                base = await self._assemble_l1_payload(db, ref_id, stage, base)
            elif level == "L2A":
                base["exam_id"] = ref_id
            elif level == "L2B":
                base["classroom_exam_id"] = ref_id
        except Exception as e:
            logger.warning("payload_assemble_partial", ref_id=ref_id, stage=stage, error=str(e))

        return base

    async def _assemble_l1_payload(
        self, db: AsyncSession, pkey: str, stage: str, base: dict,
    ) -> dict:
        """L1 스테이지별 payload 조립"""
        from models.question import Question, QuestionRaw, QuestionStructured, QuestionProduced, Batch

        # ref_id가 배치 ID일 수도, pkey일 수도 있음
        q = (await db.execute(
            select(Question).where(Question.pkey == pkey)
        )).scalar_one_or_none()

        batch_id = pkey  # 기본: ref_id 자체가 batch_id
        if q:
            batch_id = q.batch_id

        base["batch_id"] = batch_id
        batch = (await db.execute(
            select(Batch).where(Batch.id == batch_id)
        )).scalar_one_or_none()
        if batch:
            base["file_path"] = batch.original_hwp_path or ""

        # PARSE_REVIEW: 파싱팀 결과가 필요 — 같은 배치의 모든 문항
        if stage in ("PARSE_REVIEW",):
            all_raws = (await db.execute(
                select(QuestionRaw, Question)
                .join(Question, Question.pkey == QuestionRaw.pkey)
                .where(Question.batch_id == batch_id)
            )).all()
            raw_questions = []
            for raw_row, q_row in all_raws:
                # formulas에서 segment 복원
                formula_segs = (raw_row.formulas or {}).get("segments", [])
                text_segs = [{"type": "text", "content": raw_row.raw_text or ""}]
                all_segs = text_segs + formula_segs
                raw_questions.append({
                    "seq_num": q_row.seq_num,
                    "raw_text": raw_row.raw_text or "",
                    "question_type": "단답형" if raw_row.raw_text else "unknown",
                    "segments": all_segs,
                    "choices": [],
                    "group_id": None,
                    "formula_count": len(formula_segs),
                    "image_count": 0,
                })
            base["raw_questions"] = raw_questions
            base["parse_source"] = "hwpml"

        # META: 파싱 결과 → 메타팀에 전달 (개별 문항)
        if stage in ("META",):
            raw = (await db.execute(
                select(QuestionRaw).where(QuestionRaw.pkey == pkey)
            )).scalar_one_or_none()
            if raw:
                formula_segs = (raw.formulas or {}).get("segments", [])
                text_segs = [{"type": "text", "content": raw.raw_text or ""}]
                base["raw_question"] = {
                    "seq_num": q.seq_num if q else 0,
                    "raw_text": raw.raw_text or "",
                    "segments": text_segs + formula_segs,
                    "choices": [],
                    "question_type": "단답형" if raw.raw_text else "unknown",
                }

        # META_REVIEW: 메타팀 결과 → 메타검수팀에 전달
        if stage in ("META_REVIEW",):
            structured = (await db.execute(
                select(QuestionStructured).where(QuestionStructured.pkey == pkey)
            )).scalar_one_or_none()
            if structured:
                base["structured_question"] = {
                    "pkey": pkey,
                    "question_text": structured.question_text or "",
                    "segments": [],
                    "choices": [],
                    "metadata": {},
                }

        # PRODUCTION: 메타팀 결과 → 제작팀에 전달
        if stage in ("PRODUCTION",):
            structured = (await db.execute(
                select(QuestionStructured).where(QuestionStructured.pkey == pkey)
            )).scalar_one_or_none()
            if structured:
                base["structured_question"] = {
                    "pkey": pkey,
                    "question_text": structured.question_text or "",
                    "segments": [],
                    "choices": [],
                    "metadata": {},
                }

        # PROD_REVIEW: 제작팀 결과 → 제작검수팀에 전달
        if stage in ("PROD_REVIEW",):
            produced = (await db.execute(
                select(QuestionProduced).where(QuestionProduced.pkey == pkey)
            )).scalar_one_or_none()
            if produced:
                base["digital_question"] = {
                    "pkey": pkey,
                    "content_html": produced.content_html,
                    "content_latex": produced.content_latex,
                    "answer_correct": produced.answer_correct,
                    "answer_source": produced.answer_source,
                    "solution": {},
                    "render_html": produced.render_html,
                    "metadata": {},
                    "choices": [],
                }

        return base

    async def _get_pipeline_state(
        self, db: AsyncSession, ref_id: str, level: str
    ) -> PipelineState | None:
        result = await db.execute(
            select(PipelineState).where(
                PipelineState.ref_id == ref_id,
                PipelineState.pipeline_level == level,
            )
        )
        return result.scalar_one_or_none()

    async def _update_pipeline_state(
        self, db: AsyncSession,
        ref_id: str, level: str, status: str, stage: str,
        score: float | None,
        reject_count: int | None = None,
        reject_context: dict | None = None,
    ) -> None:
        state = await self._get_pipeline_state(db, ref_id, level)
        now = datetime.now(timezone.utc)
        if state:
            state.current_stage = stage
            state.status = status
            if score is not None:
                state.last_score = score
            if reject_count is not None:
                state.reject_count = reject_count
            if reject_context is not None:
                state.reject_context = reject_context
            state.timeout_at = now + timedelta(seconds=TIMEOUT_SECONDS)
        else:
            new_state = PipelineState(
                ref_id=ref_id,
                pipeline_level=level,
                current_stage=stage,
                status=status,
                last_score=score,
                reject_count=reject_count or 0,
                reject_context=reject_context,
                timeout_at=now + timedelta(seconds=TIMEOUT_SECONDS),
            )
            db.add(new_state)

    async def _record_history(
        self, db: AsyncSession,
        ref_id: str, level: str,
        from_stage: str, to_stage: str,
        action: str,
        score: float | None,
        score_detail: dict,
    ) -> None:
        history = PipelineHistory(
            ref_id=ref_id,
            pipeline_level=level,
            from_stage=from_stage,
            to_stage=to_stage,
            action=action,
            score=score,
            score_detail=score_detail,
            created_at=datetime.now(timezone.utc),
        )
        db.add(history)

    async def _increment_question_version(self, db: AsyncSession, pkey: str) -> None:
        from models.question import Question
        await db.execute(
            update(Question)
            .where(Question.pkey == pkey)
            .values(version=Question.version + 1)
        )

    async def _sync_classroom_exam_status(
        self, db: AsyncSession, ref_id: str, stage: str
    ) -> None:
        """v1.4 패치 #4: L2B 상태 전이 → classroom_exams.status 동기화"""
        stage_to_status = {
            "HWP_GENERATING": "HWP_GENERATING",
            "HWP_REVIEW": "HWP_REVIEW",
            "DEPLOY_READY": "DEPLOY_READY",
            "SCHEDULED": "SCHEDULED",
            "ACTIVE": "ACTIVE",
            "CLOSED": "CLOSED",
        }
        ce_status = stage_to_status.get(stage)
        if ce_status:
            try:
                ce_id = int(ref_id)
                await db.execute(
                    update(ClassroomExam)
                    .where(ClassroomExam.id == ce_id)
                    .values(status=ce_status)
                )
            except (ValueError, Exception) as e:
                logger.error("sync_classroom_exam_failed", ref_id=ref_id, error=str(e))


if __name__ == "__main__":
    orchestrator = Orchestrator()
    asyncio.run(orchestrator.run())
