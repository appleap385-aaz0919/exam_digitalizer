"""학생 접속 (비인증) — QR/초대코드로 접속 후 이름 선택/입력"""
import secrets

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis
from core.deps import get_db, get_redis
from models.classroom import Classroom, ClassroomStudent, ClassroomExam
from models.exam import Exam, ExamQuestion
from models.question import QuestionProduced, QuestionRaw, QuestionMetadata
from schemas.auth import StudentTokenRequest, StudentTokenResponse
from schemas.common import ErrorCode

router = APIRouter()
logger = structlog.get_logger()

STUDENT_TOKEN_TTL = 86400  # 24시간


@router.get("/classroom")
async def find_classroom_by_invite(
    invite_code: str,
    db: AsyncSession = Depends(get_db),
):
    """초대코��로 학급 + 학생 목록 조회 (비인증)"""
    result = await db.execute(
        select(Classroom).where(
            Classroom.invite_code == invite_code,
            Classroom.deleted_at.is_(None),
            Classroom.is_active.is_(True),
        )
    )
    classroom = result.scalar_one_or_none()
    if not classroom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": ErrorCode.CLASSROOM_NOT_FOUND, "message": "올바른 초대 코드가 아닙니다"},
        )

    students_result = await db.execute(
        select(ClassroomStudent).where(ClassroomStudent.classroom_id == classroom.id)
        .order_by(ClassroomStudent.student_number)
    )
    students = [
        {"id": s.id, "name": s.name, "student_number": s.student_number}
        for s in students_result.scalars()
    ]
    return {
        "classroom_id": classroom.id,
        "name": classroom.name,
        "grade": classroom.grade,
        "students": students,
    }


@router.post("/select-student", response_model=StudentTokenResponse)
async def select_student(
    request: StudentTokenRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """학생 선택 또는 자기등록 → student_token 발급 (Redis TTL 24h)"""
    # 학급 조회
    result = await db.execute(
        select(Classroom).where(
            Classroom.id == request.classroom_id,
            Classroom.deleted_at.is_(None),
            Classroom.is_active.is_(True),
        )
    )
    classroom = result.scalar_one_or_none()
    if not classroom:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": ErrorCode.CLASSROOM_NOT_FOUND, "message": "학급을 찾을 수 없습니다"},
        )

    # 학생 조회
    student_result = await db.execute(
        select(ClassroomStudent).where(
            ClassroomStudent.classroom_id == request.classroom_id,
            ClassroomStudent.id == request.student_id,
        )
    )
    student = student_result.scalar_one_or_none()
    if not student:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={"error_code": ErrorCode.STUDENT_NOT_FOUND, "message": "학생을 찾을 수 없습니다"},
        )

    # 토큰 생성 및 Redis 저장
    token = secrets.token_urlsafe(32)
    key = f"student_token:{token}"
    await redis.hset(
        key,
        mapping={
            "classroom_id": request.classroom_id,
            "student_id": str(request.student_id),
            "student_name": student.name,
        },
    )
    await redis.expire(key, STUDENT_TOKEN_TTL)

    logger.info("student_token_issued", student_id=request.student_id, classroom_id=request.classroom_id)
    return StudentTokenResponse(
        student_token=token,
        student_id=student.id,
        student_name=student.name,
        classroom_id=request.classroom_id,
    )


@router.post("/by-name")
async def join_by_name(
    data: dict,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """이름 직접 입력으로 접속 — 기존 학생이면 매칭, 없으면 임시 게스트로 처리"""
    classroom_id: str = data.get("classroom_id", "")
    name: str = (data.get("name") or "").strip()
    student_number: int | None = data.get("student_number")
    if not classroom_id or not name:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="classroom_id와 name이 필요합니다")

    result = await db.execute(
        select(Classroom).where(
            Classroom.id == classroom_id,
            Classroom.deleted_at.is_(None),
            Classroom.is_active.is_(True),
        )
    )
    classroom = result.scalar_one_or_none()
    if not classroom:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="학급을 찾을 수 없습니다")

    # 이름으로 학생 조회 — 없으면 자기등록(is_self_registered=True)으로 생성
    student_result = await db.execute(
        select(ClassroomStudent).where(
            ClassroomStudent.classroom_id == classroom_id,
            ClassroomStudent.name == name,
        )
    )
    student = student_result.scalar_one_or_none()
    if not student:
        student = ClassroomStudent(
            classroom_id=classroom_id,
            name=name,
            student_number=student_number,
            is_self_registered=True,
        )
        db.add(student)
        await db.commit()
        await db.refresh(student)
    student_id = student.id

    token = secrets.token_urlsafe(32)
    key = f"student_token:{token}"
    await redis.hset(
        key,
        mapping={
            "classroom_id": classroom_id,
            "student_id": str(student_id),
            "student_name": name,
        },
    )
    await redis.expire(key, STUDENT_TOKEN_TTL)

    logger.info("student_token_by_name", name=name, classroom_id=classroom_id, student_id=student_id)
    return StudentTokenResponse(
        student_token=token,
        student_id=student_id,
        student_name=name,
        classroom_id=classroom_id,
    )


@router.get("/exam/{exam_id}/questions")
async def get_exam_questions_for_student(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
):
    """학생용 — 시험 문항 목록 + 렌더링 HTML 조회 (비인증)"""
    exam = (await db.execute(
        select(Exam).where(Exam.id == exam_id, Exam.deleted_at.is_(None))
    )).scalar_one_or_none()
    if not exam:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="시험지를 찾을 수 없습니다")

    eq_result = await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == exam_id)
        .order_by(ExamQuestion.seq_order)
    )
    exam_questions = eq_result.scalars().all()

    questions = []
    for eq in exam_questions:
        # render_html 우선, 없으면 raw_text
        produced = (await db.execute(
            select(QuestionProduced).where(QuestionProduced.pkey == eq.pkey)
        )).scalar_one_or_none()

        raw = (await db.execute(
            select(QuestionRaw).where(QuestionRaw.pkey == eq.pkey)
        )).scalar_one_or_none()

        meta = (await db.execute(
            select(QuestionMetadata).where(QuestionMetadata.pkey == eq.pkey)
        )).scalar_one_or_none()

        questions.append({
            "pkey": eq.pkey,
            "seq_order": eq.seq_order,
            "points": eq.points_current,
            "render_html": produced.render_html if produced else None,
            "raw_text": raw.raw_text if raw else None,
            "question_type": meta.question_type if meta else None,
        })

    return {
        "exam_id": exam_id,
        "title": exam.title,
        "total_questions": exam.total_questions,
        "total_points": exam.total_points,
        "time_limit_minutes": exam.time_limit_minutes,
        "questions": questions,
    }


@router.get("/classroom/{classroom_id}/exams")
async def get_classroom_exams_for_student(
    classroom_id: str,
    db: AsyncSession = Depends(get_db),
):
    """학생용 — 학급에 배포된 시험 목록 조회 (비인증, Exam join)"""
    from sqlalchemy.orm import selectinload
    result = await db.execute(
        select(ClassroomExam).where(
            ClassroomExam.classroom_id == classroom_id,
            ClassroomExam.deleted_at.is_(None),
        ).options(selectinload(ClassroomExam.exam))
        .order_by(ClassroomExam.created_at.desc())
    )
    exams = []
    for ce in result.scalars():
        exam = ce.exam
        exams.append({
            "id": ce.id,
            "exam_id": ce.exam_id,
            "exam_title": exam.title if exam else ce.exam_id,
            "total_questions": exam.total_questions if exam else 0,
            "total_points": exam.total_points if exam else 0,
            "status": ce.status,
            "time_limit_minutes": ce.time_limit_minutes or (exam.time_limit_minutes if exam else 50),
            "opens_at": ce.opens_at.isoformat() if ce.opens_at else None,
            "closes_at": ce.closes_at.isoformat() if ce.closes_at else None,
        })
    return {"data": exams}
