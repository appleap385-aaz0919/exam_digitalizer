from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, get_redis, require_admin, require_teacher
from core.queue import PIPELINE_TASKS_STREAM, publish_task
from models.pipeline import PipelineHistory, PipelineState
from models.question import Batch, Question, QuestionMetadata, QuestionProduced, QuestionRaw, QuestionStructured
from models.user import User

router = APIRouter()


# ─── 시스템 지표 ───────────────────────────────────────────────────
@router.get("/metrics")
async def get_metrics(
    current_user: dict = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
):
    """시스템 전체 통계 (ADMIN 전용)"""
    total_users = (await db.execute(
        select(func.count()).select_from(User).where(User.deleted_at.is_(None))
    )).scalar()

    total_questions = (await db.execute(
        select(func.count()).select_from(Question).where(Question.deleted_at.is_(None))
    )).scalar()

    total_batches = (await db.execute(
        select(func.count()).select_from(Batch).where(Batch.deleted_at.is_(None))
    )).scalar()

    pipeline_in_progress = (await db.execute(
        select(func.count()).select_from(PipelineState).where(
            PipelineState.status == "IN_PROGRESS"
        )
    )).scalar()

    pipeline_human_review = (await db.execute(
        select(func.count()).select_from(PipelineState).where(
            PipelineState.status == "HUMAN_REVIEW"
        )
    )).scalar()

    return {
        "total_users": total_users,
        "total_questions": total_questions,
        "total_batches": total_batches,
        "pipeline_in_progress": pipeline_in_progress,
        "pipeline_human_review": pipeline_human_review,
    }


# ─── Human Review 큐 ──────────────────────────────────────────────

@router.get("/human-review")
async def list_human_review(
    current_user: dict = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    """AI가 3회 반려한 문항 목록 조회 (교사/관리자 전용)"""
    rows = (await db.execute(
        select(PipelineState, Question, QuestionProduced, QuestionRaw, QuestionMetadata)
        .join(Question, Question.pkey == PipelineState.ref_id)
        .outerjoin(QuestionProduced, QuestionProduced.pkey == Question.pkey)
        .outerjoin(QuestionRaw, QuestionRaw.pkey == Question.pkey)
        .outerjoin(QuestionMetadata, QuestionMetadata.pkey == Question.pkey)
        .where(
            PipelineState.status == "HUMAN_REVIEW",
            PipelineState.pipeline_level == "L1",
            Question.deleted_at.is_(None),
        )
        .order_by(PipelineState.updated_at.desc())
    )).all()

    items = []
    for state, q, produced, raw, meta in rows:
        items.append({
            "pkey": q.pkey,
            "seq_num": q.seq_num,
            "batch_id": q.batch_id,
            "current_stage": state.current_stage,
            "reject_count": state.reject_count,
            "reject_context": state.reject_context,
            "last_score": state.last_score,
            "raw_text": raw.raw_text if raw else None,
            "render_html": produced.render_html if produced else None,
            "content_html": produced.content_html if produced else None,
            "answer_correct": produced.answer_correct if produced else None,
            "answer_source": produced.answer_source if produced else None,
            "metadata": {
                "subject": meta.subject,
                "grade": meta.grade,
                "unit": meta.unit,
                "difficulty": meta.difficulty,
                "question_type": meta.question_type,
            } if meta else None,
            "updated_at": state.updated_at.isoformat() if state.updated_at else None,
        })

    return {"data": items, "total": len(items)}


@router.post("/human-review/{pkey}/approve")
async def approve_human_review(
    pkey: str,
    current_user: dict = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """사람이 검토 후 승인 → DATA 스테이지로 진행"""
    state = (await db.execute(
        select(PipelineState).where(
            PipelineState.ref_id == pkey,
            PipelineState.pipeline_level == "L1",
        )
    )).scalar_one_or_none()

    if not state:
        raise HTTPException(status_code=404, detail="파이프라인 상태를 찾을 수 없습니다")
    if state.status != "HUMAN_REVIEW":
        raise HTTPException(
            status_code=400,
            detail=f"HUMAN_REVIEW 상태가 아닙니다: {state.status}",
        )

    prev_stage = state.current_stage
    now = datetime.now(timezone.utc)

    # 상태 전이: DATA 스테이지로 진행
    state.status = "IN_PROGRESS"
    state.current_stage = "DATA"
    state.reject_count = 0
    state.reject_context = None

    # 이력 기록
    db.add(PipelineHistory(
        ref_id=pkey,
        pipeline_level="L1",
        from_stage=prev_stage,
        to_stage="DATA",
        action="HUMAN_CONFIRM",
        score=state.last_score,
        score_detail={
            "approved_by": current_user.get("sub"),
            "approved_at": now.isoformat(),
        },
        created_at=now,
    ))

    # a07_data 에이전트에 작업 발행
    payload = {
        "ref_id": pkey,
        "pkey": pkey,
        "level": "L1",
        "stage": "DATA",
        "timestamp": now.isoformat(),
        "human_confirmed": True,
        "confirmed_by": current_user.get("sub"),
    }
    await publish_task(redis, PIPELINE_TASKS_STREAM, "a07_data", pkey, "L1", payload, stage="DATA")

    await db.commit()
    return {"ok": True, "pkey": pkey, "next_stage": "DATA", "message": "승인 완료 — DATA 스테이지로 진행합니다"}


@router.post("/human-review/{pkey}/reject")
async def reject_human_review(
    pkey: str,
    current_user: dict = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """사람이 검토 후 반려 → PRODUCTION 스테이지로 재작업"""
    state = (await db.execute(
        select(PipelineState).where(
            PipelineState.ref_id == pkey,
            PipelineState.pipeline_level == "L1",
        )
    )).scalar_one_or_none()

    if not state:
        raise HTTPException(status_code=404, detail="파이프라인 상태를 찾을 수 없습니다")
    if state.status != "HUMAN_REVIEW":
        raise HTTPException(
            status_code=400,
            detail=f"HUMAN_REVIEW 상태가 아닙니다: {state.status}",
        )

    prev_stage = state.current_stage
    now = datetime.now(timezone.utc)

    # 반려 횟수 리셋 후 PRODUCTION으로 되돌리기
    state.status = "IN_PROGRESS"
    state.current_stage = "PRODUCTION"
    state.reject_count = 0
    state.reject_context = {
        "human_rejected_at": now.isoformat(),
        "rejected_by": current_user.get("sub"),
    }

    # 이력 기록
    db.add(PipelineHistory(
        ref_id=pkey,
        pipeline_level="L1",
        from_stage=prev_stage,
        to_stage="PRODUCTION",
        action="HUMAN_REJECT",
        score=state.last_score,
        score_detail={
            "rejected_by": current_user.get("sub"),
            "rejected_at": now.isoformat(),
        },
        created_at=now,
    ))

    # a05_producer 에이전트에 재작업 발행
    structured = (await db.execute(
        select(QuestionStructured).where(QuestionStructured.pkey == pkey)
    )).scalar_one_or_none()

    payload: dict = {
        "ref_id": pkey,
        "pkey": pkey,
        "level": "L1",
        "stage": "PRODUCTION",
        "timestamp": now.isoformat(),
        "reject_context": {"reason": "사람 검수자 반려 — 제작 단계 재시도"},
    }
    if structured:
        payload["structured_question"] = {
            "pkey": pkey,
            "question_text": structured.question_text or "",
            "segments": [],
            "choices": [],
            "metadata": {},
        }

    await publish_task(redis, PIPELINE_TASKS_STREAM, "a05_producer", pkey, "L1", payload, stage="PRODUCTION")

    await db.commit()
    return {"ok": True, "pkey": pkey, "next_stage": "PRODUCTION", "message": "반려 완료 — PRODUCTION 재작업을 시작합니다"}
