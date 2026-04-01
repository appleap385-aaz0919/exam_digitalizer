"""성적 API — 채점 결과 조회

GET /api/v1/grades/classroom-exam/{ce_id}/summary  — 학급별 성적 요약
GET /api/v1/grades/exam/{exam_id}/summary          — 시험 전체 통합 성적
GET /api/v1/grades/submission/{sub_id}             — 개별 학생 채점 상세
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession

from core.deps import get_db, require_teacher
from models.submission import GradeResult, Submission, SubmissionAnswer
from models.classroom import ClassroomExam, ClassroomStudent

router = APIRouter()


@router.get("/classroom-exam/{ce_id}/summary")
async def classroom_exam_summary(
    ce_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """학급별 성적 요약"""
    submissions = (await db.execute(
        select(Submission, GradeResult)
        .outerjoin(GradeResult, GradeResult.submission_id == Submission.id)
        .where(Submission.classroom_exam_id == ce_id)
    )).all()

    students = []
    total_score_sum = 0
    graded_count = 0

    for sub, grade in submissions:
        student = (await db.execute(
            select(ClassroomStudent).where(ClassroomStudent.id == sub.student_id)
        )).scalar_one_or_none()

        entry = {
            "student_id": sub.student_id,
            "student_name": student.name if student else "Unknown",
            "status": sub.status,
            "submitted_at": sub.submitted_at.isoformat() if sub.submitted_at else None,
            "total_score": grade.total_score if grade else None,
            "max_score": grade.max_score if grade else None,
            "percentage": grade.percentage if grade else None,
        }
        students.append(entry)
        if grade:
            total_score_sum += grade.total_score
            graded_count += 1

    avg_score = total_score_sum / graded_count if graded_count > 0 else 0

    return {
        "classroom_exam_id": ce_id,
        "total_students": len(students),
        "submitted": sum(1 for s in students if s["status"] == "SUBMITTED"),
        "graded": graded_count,
        "average_score": round(avg_score, 1),
        "students": students,
    }


@router.get("/exam/{exam_id}/summary")
async def exam_summary(
    exam_id: str,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """시험 전체 통합 성적 (모든 학급)"""
    ce_result = await db.execute(
        select(ClassroomExam).where(ClassroomExam.exam_id == exam_id)
    )
    ce_ids = [ce.id for ce in ce_result.scalars()]

    if not ce_ids:
        return {"exam_id": exam_id, "classroom_count": 0, "total_students": 0}

    submissions = (await db.execute(
        select(GradeResult)
        .join(Submission, Submission.id == GradeResult.submission_id)
        .where(Submission.classroom_exam_id.in_(ce_ids))
    )).scalars().all()

    scores = [g.total_score for g in submissions]
    return {
        "exam_id": exam_id,
        "classroom_count": len(ce_ids),
        "total_students": len(scores),
        "average_score": round(sum(scores) / len(scores), 1) if scores else 0,
        "max_score": max(scores) if scores else 0,
        "min_score": min(scores) if scores else 0,
    }


@router.get("/submission/{submission_id}")
async def get_submission_grade(
    submission_id: int,
    db: AsyncSession = Depends(get_db),
    _user: dict = Depends(require_teacher),
):
    """개별 학생 채점 상세"""
    grade = (await db.execute(
        select(GradeResult).where(GradeResult.submission_id == submission_id)
    )).scalar_one_or_none()
    if not grade:
        raise HTTPException(status_code=404, detail="채점 결과를 찾을 수 없습니다")

    answers = (await db.execute(
        select(SubmissionAnswer).where(SubmissionAnswer.submission_id == submission_id)
        .order_by(SubmissionAnswer.seq_order)
    )).scalars().all()

    return {
        "submission_id": submission_id,
        "total_score": grade.total_score,
        "max_score": grade.max_score,
        "percentage": grade.percentage,
        "correct_count": grade.correct_count,
        "total_count": grade.total_count,
        "answers": [
            {
                "pkey": a.pkey, "seq_order": a.seq_order,
                "answer_type": a.answer_type, "value": a.value,
                "is_correct": a.is_correct, "score": a.score,
            }
            for a in answers
        ],
    }
