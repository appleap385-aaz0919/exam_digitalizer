"""CBT 세션 API — 학생 응시

POST /api/v1/sessions/start   — 응시 시작
POST /api/v1/sessions/answer  — 답안 저장 (실시간)
POST /api/v1/sessions/submit  — 답안 제출
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_current_student, get_db, get_redis
from models.classroom import ClassroomExam, ClassroomStudent
from models.submission import Submission, SubmissionAnswer

router = APIRouter()


class StartSessionRequest(BaseModel):
    classroom_exam_id: int


class SaveAnswerRequest(BaseModel):
    pkey: str
    answer_type: str
    value: str | int | list | None


class SubmitRequest(BaseModel):
    pass  # student_token에서 세션 정보 가져옴


@router.post("/start")
async def start_session(
    request: StartSessionRequest,
    student: dict = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """응시 시작"""
    student_id = int(student["student_id"])

    # 재응시 방지
    existing = (await db.execute(
        select(Submission).where(
            Submission.classroom_exam_id == request.classroom_exam_id,
            Submission.student_id == student_id,
        )
    )).scalar_one_or_none()

    if existing and existing.submitted_at:
        raise HTTPException(status_code=400, detail="이미 제출한 시험입니다")
    if existing:
        return {"submission_id": existing.id, "status": "resumed"}

    # 시험 상태 확인
    ce = (await db.execute(
        select(ClassroomExam).where(ClassroomExam.id == request.classroom_exam_id)
    )).scalar_one_or_none()
    if not ce or ce.status != "ACTIVE":
        raise HTTPException(status_code=400, detail="현재 응시 가능한 시험이 아닙니다")

    submission = Submission(
        classroom_exam_id=request.classroom_exam_id,
        student_id=student_id,
        started_at=datetime.now(timezone.utc),
        status="IN_PROGRESS",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    return {"submission_id": submission.id, "status": "started"}


@router.post("/submit")
async def submit_answers(
    student: dict = Depends(get_current_student),
    db: AsyncSession = Depends(get_db),
):
    """답안 제출"""
    student_id = int(student["student_id"])

    submission = (await db.execute(
        select(Submission).where(
            Submission.student_id == student_id,
            Submission.status == "IN_PROGRESS",
        ).order_by(Submission.created_at.desc())
    )).scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="진행 중인 시험이 없습니다")

    submission.submitted_at = datetime.now(timezone.utc)
    submission.status = "SUBMITTED"
    await db.commit()

    return {"submission_id": submission.id, "status": "SUBMITTED"}
