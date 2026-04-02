"""시험지 API — L2-A 파이프라인

POST  /api/v1/exams                      — 시험지 구성 요청
GET   /api/v1/exams                      — 시험지 목록
GET   /api/v1/exams/{id}                 — 시험지 상세
POST  /api/v1/exams/{id}/confirm         — 시험지 확정 (EXAM_CONFIRMED)
PATCH /api/v1/exams/{id}/questions/{seq}/points — 개별 배점 수정
"""
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, get_redis, require_teacher
from core.queue import PIPELINE_TASKS_STREAM, publish_task
from models.exam import Exam, ExamQuestion
from models.question import Question

router = APIRouter()


class ExamCreateRequest(BaseModel):
    title: str
    subject: str = "수학"
    grade: int | None = None
    time_limit_minutes: int = 50
    conditions: dict = {}
    question_pkeys: list[str] = []  # 교사가 직접 선택한 문항들
    points_per_type: dict[str, int] = {"객관식": 3, "단답형": 4, "서술형": 6}


class PointsUpdateRequest(BaseModel):
    points: float


@router.post("")
async def create_exam(
    request: ExamCreateRequest,
    current_user: dict = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
    redis=Depends(get_redis),
):
    """시험지 구성 요청 → EXAM_COMPOSE → EXAM_REVIEW 파이프라인"""
    now = datetime.now(timezone.utc)
    exam_prefix = f"EX-{now.strftime('%Y%m%d')}"
    count = (await db.execute(
        select(func.count()).select_from(Exam).where(Exam.id.like(f"{exam_prefix}%"))
    )).scalar() or 0
    exam_id = f"{exam_prefix}-{count + 1:03d}"

    exam = Exam(
        id=exam_id,
        title=request.title,
        subject=request.subject,
        grade=request.grade,
        created_by=int(current_user["sub"]),
        status="EXAM_COMPOSE",
        time_limit_minutes=request.time_limit_minutes,
    )
    db.add(exam)

    # 문항 연결 + 자동 배점
    total_points = 0
    for seq, pkey in enumerate(request.question_pkeys, 1):
        q = (await db.execute(select(Question).where(Question.pkey == pkey))).scalar_one_or_none()
        if not q:
            continue
        q_type = "객관식"  # 기본값; 실제로는 metadata에서 가져와야
        points = request.points_per_type.get(q_type, 3)
        total_points += points

        eq = ExamQuestion(
            exam_id=exam_id, pkey=pkey, seq_order=seq,
            points_auto=points, points_current=points, is_points_modified=False,
        )
        db.add(eq)

    exam.total_questions = len(request.question_pkeys)
    exam.total_points = total_points
    await db.commit()

    # L2-A 파이프라인 시작
    await publish_task(
        redis, PIPELINE_TASKS_STREAM, "a10_exam_reviewer",
        ref_id=exam_id, level="L2A",
        payload={"exam_id": exam_id, "conditions": request.conditions},
    )
    exam.status = "EXAM_REVIEW"
    await db.commit()

    return {
        "exam_id": exam_id, "status": exam.status,
        "total_questions": exam.total_questions, "total_points": total_points,
    }


@router.get("")
async def list_exams(
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    status: str | None = Query(None),
    current_user: dict = Depends(require_teacher),
    db: AsyncSession = Depends(get_db),
):
    """시험지 목록"""
    offset = (page - 1) * limit
    query = select(Exam).where(
        Exam.deleted_at.is_(None),
        Exam.created_by == int(current_user["sub"]),
    )
    if status:
        query = query.where(Exam.status == status)

    total = (await db.execute(
        select(func.count()).select_from(Exam).where(
            Exam.deleted_at.is_(None), Exam.created_by == int(current_user["sub"]),
        )
    )).scalar() or 0

    result = await db.execute(query.order_by(Exam.created_at.desc()).offset(offset).limit(limit))
    exams = [
        {
            "id": e.id, "title": e.title, "status": e.status,
            "total_questions": e.total_questions, "total_points": e.total_points,
            "time_limit_minutes": e.time_limit_minutes,
            "created_at": e.created_at.isoformat() if e.created_at else None,
        }
        for e in result.scalars()
    ]
    return {"data": exams, "meta": {"total": total, "page": page, "limit": limit}}


@router.get("/{exam_id}")
async def get_exam(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """시험지 상세"""
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="시험지를 찾을 수 없습니다")

    eq_result = await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam_id).order_by(ExamQuestion.seq_order)
    )
    questions = [
        {
            "seq_order": eq.seq_order, "pkey": eq.pkey,
            "points_auto": eq.points_auto, "points_current": eq.points_current,
            "is_points_modified": eq.is_points_modified,
        }
        for eq in eq_result.scalars()
    ]
    return {
        "id": exam.id, "title": exam.title, "status": exam.status,
        "total_questions": exam.total_questions, "total_points": exam.total_points,
        "time_limit_minutes": exam.time_limit_minutes,
        "questions": questions,
    }


@router.post("/{exam_id}/confirm")
async def confirm_exam(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """시험지 확정 — EXAM_CONFIRMED (이후 콘텐츠 불변)"""
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="시험지를 찾을 수 없습니다")
    if exam.status == "EXAM_CONFIRMED":
        raise HTTPException(status_code=400, detail="이미 확정된 시험지입니다")
    if exam.status not in ("EXAM_REVIEW", "EXAM_COMPOSE"):
        raise HTTPException(status_code=400, detail=f"확정 불가 상태: {exam.status}")

    exam.status = "EXAM_CONFIRMED"
    await db.commit()
    return {"exam_id": exam_id, "status": "EXAM_CONFIRMED"}


@router.patch("/{exam_id}/questions/{seq}/points")
async def update_question_points(
    exam_id: str,
    seq: int,
    request: PointsUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """개별 배점 수정 (EXAM_CONFIRMED 전에만 가능)"""
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="시험지를 찾을 수 없습니다")
    if exam.status == "EXAM_CONFIRMED":
        raise HTTPException(status_code=400, detail="확정된 시험지는 배점 수정 불가")

    eq = (await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam_id, ExamQuestion.seq_order == seq)
    )).scalar_one_or_none()
    if not eq:
        raise HTTPException(status_code=404, detail="문항을 찾을 수 없습니다")

    eq.points_modified = request.points
    eq.points_current = request.points
    eq.is_points_modified = True

    # total_points 재계산
    all_eq = (await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
    )).scalars().all()
    exam.total_points = sum(e.points_current for e in all_eq)
    await db.commit()

    return {"exam_id": exam_id, "seq": seq, "points": request.points, "total_points": exam.total_points}


class AddQuestionRequest(BaseModel):
    pkey: str
    points: float = 3.0


class ReorderRequest(BaseModel):
    question_pkeys: list[str]  # 새로운 순서의 pkey 목록


@router.post("/{exam_id}/questions")
async def add_question_to_exam(
    exam_id: str,
    request: AddQuestionRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """시험지에 문항 추가"""
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="시험지를 찾을 수 없습니다")

    # 중복 검사
    existing = (await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam_id, ExamQuestion.pkey == request.pkey)
    )).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=400, detail="이미 포함된 문항입니다")

    # 마지막 순서 + 1
    max_seq = (await db.execute(
        select(func.max(ExamQuestion.seq_order)).where(ExamQuestion.exam_id == exam_id)
    )).scalar() or 0

    eq = ExamQuestion(
        exam_id=exam_id, pkey=request.pkey,
        seq_order=max_seq + 1,
        points_auto=request.points, points_current=request.points,
    )
    db.add(eq)
    exam.total_questions += 1
    exam.total_points = int(exam.total_points + request.points)
    await db.commit()

    return {"exam_id": exam_id, "pkey": request.pkey, "seq_order": eq.seq_order}


@router.delete("/{exam_id}/questions/{pkey}")
async def remove_question_from_exam(
    exam_id: str,
    pkey: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """시험지에서 문항 제거"""
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="시험지를 찾을 수 없습니다")

    eq = (await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam_id, ExamQuestion.pkey == pkey)
    )).scalar_one_or_none()
    if not eq:
        raise HTTPException(status_code=404, detail="해당 문항이 시험지에 없습니다")

    await db.delete(eq)

    # 순서 재정렬
    remaining = (await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
        .order_by(ExamQuestion.seq_order)
    )).scalars().all()
    for i, r in enumerate(remaining):
        r.seq_order = i + 1

    exam.total_questions = len(remaining)
    exam.total_points = int(sum(r.points_current for r in remaining))
    await db.commit()

    return {"exam_id": exam_id, "removed": pkey, "total_questions": exam.total_questions}


@router.put("/{exam_id}/reorder")
async def reorder_exam_questions(
    exam_id: str,
    request: ReorderRequest,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """시험지 문항 순서 변경"""
    exam = (await db.execute(select(Exam).where(Exam.id == exam_id))).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=404, detail="시험지를 찾을 수 없습니다")

    eqs = (await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
    )).scalars().all()
    eq_map = {eq.pkey: eq for eq in eqs}

    for i, pkey in enumerate(request.question_pkeys):
        if pkey in eq_map:
            eq_map[pkey].seq_order = i + 1

    await db.commit()
    return {"exam_id": exam_id, "order": request.question_pkeys}
