"""학생 접속 (비인증) — QR/초대코드로 접속 후 이름 선택/입력"""
import secrets
from datetime import datetime, timezone

import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

import redis.asyncio as aioredis
from core.deps import get_db, get_redis
from models.classroom import Classroom, ClassroomStudent, ClassroomExam
from models.exam import Exam, ExamQuestion
from models.question import QuestionProduced, QuestionRaw, QuestionMetadata
from models.submission import Submission, SubmissionAnswer
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


# ── 학생 세션 (비인증) ──────────────────────────────────────

async def _verify_student_token(token: str, redis: aioredis.Redis) -> dict:
    """student_token → Redis에서 학생 정보 조회"""
    key = f"student_token:{token}"
    data = await redis.hgetall(key)
    if not data:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="유효하지 않은 학생 토큰")
    return data


@router.post("/sessions/start")
async def student_start_session(
    data: dict,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """학생 응시 시작 (비인증 — student_token으로 본인 확인)"""
    student_token: str = data.get("student_token", "")
    classroom_exam_id: int = data.get("classroom_exam_id", 0)
    if not student_token or not classroom_exam_id:
        raise HTTPException(status_code=400, detail="student_token과 classroom_exam_id 필요")

    student_info = await _verify_student_token(student_token, redis)
    student_id = int(student_info.get("student_id", 0))
    if student_id == 0:
        raise HTTPException(status_code=400, detail="유효하지 않은 학생 ID")

    # 재응시 방지
    existing = (await db.execute(
        select(Submission).where(
            Submission.classroom_exam_id == classroom_exam_id,
            Submission.student_id == student_id,
        )
    )).scalar_one_or_none()

    if existing and existing.submitted_at:
        raise HTTPException(status_code=400, detail="이미 제출한 시험입니다")
    if existing:
        return {"submission_id": existing.id, "status": "resumed"}

    submission = Submission(
        classroom_exam_id=classroom_exam_id,
        student_id=student_id,
        started_at=datetime.now(timezone.utc),
        status="IN_PROGRESS",
    )
    db.add(submission)
    await db.commit()
    await db.refresh(submission)

    logger.info("session_started", submission_id=submission.id, student_id=student_id)
    return {"submission_id": submission.id, "status": "started"}


@router.post("/sessions/submit")
async def student_submit_answers(
    data: dict,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """답안 제출 (비인증 — student_token + answers)"""
    student_token: str = data.get("student_token", "")
    submission_id: int = data.get("submission_id", 0)
    answers: list = data.get("answers", [])

    if not student_token or not submission_id:
        raise HTTPException(status_code=400, detail="student_token과 submission_id 필요")

    student_info = await _verify_student_token(student_token, redis)
    student_id = int(student_info.get("student_id", 0))

    submission = (await db.execute(
        select(Submission).where(
            Submission.id == submission_id,
            Submission.student_id == student_id,
        )
    )).scalar_one_or_none()

    if not submission:
        raise HTTPException(status_code=404, detail="세션을 찾을 수 없습니다")
    if submission.submitted_at:
        raise HTTPException(status_code=400, detail="이미 제출한 시험입니다")

    # 답안 저장
    now = datetime.now(timezone.utc)
    for ans in answers:
        sa = SubmissionAnswer(
            submission_id=submission_id,
            pkey=ans.get("pkey", ""),
            seq_order=ans.get("seq", 0),
            answer_type=ans.get("question_type") or "short_answer",
            value=ans.get("value"),
            answered_at=now if ans.get("value") else None,
        )
        db.add(sa)

    # 제출 완료
    submission.submitted_at = now
    submission.status = "SUBMITTED"
    await db.commit()

    # 자동 채점 (규칙 기반 — 객관식/단답형)
    try:
        await _auto_grade(db, submission, answers)
    except Exception as e:
        logger.warning("auto_grade_failed", error=str(e))

    logger.info("session_submitted", submission_id=submission_id, student_id=student_id, answer_count=len(answers))
    return {"submission_id": submission_id, "status": "SUBMITTED", "answer_count": len(answers)}


async def _auto_grade(db: AsyncSession, submission: Submission, raw_answers: list) -> None:
    """규칙 기반 자동 채점: 정답 비교 후 GradeResult + SubmissionAnswer.is_correct 업데이트"""
    from models.submission import GradeResult

    # 시험 문항 + 정답 로드
    ce = (await db.execute(
        select(ClassroomExam).where(ClassroomExam.id == submission.classroom_exam_id)
    )).scalar_one()

    exam_questions = (await db.execute(
        select(ExamQuestion).where(ExamQuestion.exam_id == ce.exam_id).order_by(ExamQuestion.seq_order)
    )).scalars().all()

    # pkey → {correct_answer, points}
    answer_key: dict[str, dict] = {}
    for eq in exam_questions:
        produced = (await db.execute(
            select(QuestionProduced).where(QuestionProduced.pkey == eq.pkey)
        )).scalar_one_or_none()
        correct = None
        if produced and produced.answer_correct:
            ac = produced.answer_correct
            correct = ac.get("correct", [ac.get("value")]) if isinstance(ac, dict) else [str(ac)]
        answer_key[eq.pkey] = {"correct": correct, "points": eq.points_current}

    # 채점
    total_score = 0.0
    max_score = sum(ak["points"] for ak in answer_key.values())
    correct_count = 0

    # SubmissionAnswer에 is_correct, score 업데이트
    sa_list = (await db.execute(
        select(SubmissionAnswer).where(SubmissionAnswer.submission_id == submission.id)
    )).scalars().all()

    for sa in sa_list:
        key = answer_key.get(sa.pkey)
        if not key or not key["correct"]:
            continue
        student_val = (sa.value or "").strip()
        correct_vals = [str(c).strip() for c in key["correct"]] if key["correct"] else []
        is_correct = student_val in correct_vals
        sa.is_correct = is_correct
        sa.score = key["points"] if is_correct else 0.0
        if is_correct:
            total_score += key["points"]
            correct_count += 1

    # GradeResult 생성
    gr = GradeResult(
        submission_id=submission.id,
        total_score=total_score,
        max_score=max_score,
        percentage=round(total_score / max_score * 100, 1) if max_score > 0 else 0,
        correct_count=correct_count,
        total_count=len(sa_list),
        graded_at=datetime.now(timezone.utc),
        graded_by="auto",
    )
    db.add(gr)

    submission.total_score = total_score
    submission.status = "GRADED"
    await db.commit()

    logger.info("auto_grade_complete", submission_id=submission.id, score=total_score, max=max_score)
