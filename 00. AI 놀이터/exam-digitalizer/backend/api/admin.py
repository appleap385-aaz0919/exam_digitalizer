from fastapi import APIRouter, Depends
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, require_admin
from models.pipeline import PipelineState
from models.question import Batch, Question
from models.user import User

router = APIRouter()


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

    return {
        "total_users": total_users,
        "total_questions": total_questions,
        "total_batches": total_batches,
        "pipeline_in_progress": pipeline_in_progress,
    }
