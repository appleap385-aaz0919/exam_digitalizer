from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Float, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Submission(Base, TimestampMixin):
    """응시 세션"""
    __tablename__ = "submissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    classroom_exam_id: Mapped[int] = mapped_column(
        ForeignKey("classroom_exams.id"), nullable=False, index=True
    )
    student_id: Mapped[int] = mapped_column(
        ForeignKey("classroom_students.id"), nullable=False, index=True
    )
    started_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    submitted_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    is_auto_submitted: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default="IN_PROGRESS"
    )  # IN_PROGRESS / SUBMITTED / NO_SHOW
    total_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    session_id: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)

    # Relationships
    classroom_exam: Mapped["ClassroomExam"] = relationship(back_populates="submissions")
    student: Mapped["ClassroomStudent"] = relationship(back_populates="submissions")
    answers: Mapped[list["SubmissionAnswer"]] = relationship(back_populates="submission")
    grade_result: Mapped[Optional["GradeResult"]] = relationship(
        back_populates="submission", uselist=False
    )


class SubmissionAnswer(Base, TimestampMixin):
    """문항별 답안"""
    __tablename__ = "submission_answers"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, index=True
    )
    pkey: Mapped[str] = mapped_column(ForeignKey("questions.pkey"), nullable=False)
    seq_order: Mapped[int] = mapped_column(Integer, nullable=False)
    answer_type: Mapped[str] = mapped_column(String(30), nullable=False)
    # choice / choice_multiple / short_answer / descriptive
    value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # 단일: "3" / 복수: "[2, 4]" / 단답형: "3cm" / 서술형: text / 미응답: null
    is_correct: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    answered_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    submission: Mapped["Submission"] = relationship(back_populates="answers")
    question: Mapped["Question"] = relationship()


class GradeResult(Base, TimestampMixin):
    """채점 결과"""
    __tablename__ = "grade_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("submissions.id"), nullable=False, unique=True
    )
    total_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    max_score: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    percentage: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    correct_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    score_detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    graded_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    graded_by: Mapped[str] = mapped_column(String(20), nullable=False, default="auto")
    # auto / teacher / admin
    delivered_to_student_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    delivered_to_teacher_at: Mapped[Optional[datetime]] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    # Relationships
    submission: Mapped["Submission"] = relationship(back_populates="grade_result")


class AnswerCorrection(Base, TimestampMixin):
    """정답 정정 이력"""
    __tablename__ = "answer_corrections"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pkey: Mapped[str] = mapped_column(ForeignKey("questions.pkey"), nullable=False, index=True)
    exam_id: Mapped[Optional[str]] = mapped_column(ForeignKey("exams.id"), nullable=True)
    before_answer: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    after_answer: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    corrected_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    is_regraded: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    regraded_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    corrector: Mapped["User"] = relationship()
    question: Mapped["Question"] = relationship()
