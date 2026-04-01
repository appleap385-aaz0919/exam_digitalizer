from datetime import datetime
from typing import Optional

from sqlalchemy import Boolean, Float, ForeignKey, Integer, String, Text, TIMESTAMP, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, SoftDeleteMixin


class Exam(Base, TimestampMixin, SoftDeleteMixin):
    """시험지 마스터 — 콘텐츠 담당 (v1.3: hwp_file_path 없음, 학급별로 이동)"""
    __tablename__ = "exams"

    id: Mapped[str] = mapped_column(String(30), primary_key=True)  # EX-YYYYMMDD-NNN
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    subject: Mapped[str] = mapped_column(String(50), nullable=False, default="수학")
    grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="EXAM_COMPOSE"
    )  # EXAM_COMPOSE / EXAM_REVIEW / EXAM_CONFIRMED
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_points: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    time_limit_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    preview_html_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)

    # Relationships
    creator: Mapped["User"] = relationship()
    questions: Mapped[list["ExamQuestion"]] = relationship(back_populates="exam")
    classroom_exams: Mapped[list["ClassroomExam"]] = relationship(back_populates="exam")


class ExamQuestion(Base, TimestampMixin):
    """시험지-문항 연결 (배점 포함)"""
    __tablename__ = "exam_questions"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), nullable=False, index=True)
    pkey: Mapped[str] = mapped_column(ForeignKey("questions.pkey"), nullable=False)
    seq_order: Mapped[int] = mapped_column(Integer, nullable=False)
    points_auto: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 자동 배정
    points_modified: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 교사 수정
    points_current: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # points_current = points_modified if modified else points_auto
    is_points_modified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    __table_args__ = (
        UniqueConstraint("exam_id", "seq_order", name="uq_exam_question_seq"),
        UniqueConstraint("exam_id", "pkey", name="uq_exam_question_pkey"),
    )

    # Relationships
    exam: Mapped["Exam"] = relationship(back_populates="questions")
    question: Mapped["Question"] = relationship()
