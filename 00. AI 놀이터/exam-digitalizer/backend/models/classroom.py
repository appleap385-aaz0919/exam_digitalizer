from datetime import datetime
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, TIMESTAMP, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin, SoftDeleteMixin


class Classroom(Base, TimestampMixin, SoftDeleteMixin):
    """학급"""
    __tablename__ = "classrooms"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)  # UUID
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    teacher_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    invite_code: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    subject: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    invite_qr_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)

    # Relationships
    teacher: Mapped["User"] = relationship(back_populates="classrooms")
    students: Mapped[list["ClassroomStudent"]] = relationship(back_populates="classroom")
    exams: Mapped[list["ClassroomExam"]] = relationship(back_populates="classroom")


class ClassroomStudent(Base, TimestampMixin):
    """학급 내 학생 — 계정 없음, (classroom_id, name) UNIQUE"""
    __tablename__ = "classroom_students"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    classroom_id: Mapped[str] = mapped_column(
        ForeignKey("classrooms.id"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    student_number: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    is_self_registered: Mapped[bool] = mapped_column(default=False, nullable=False)

    __table_args__ = (
        UniqueConstraint("classroom_id", "name", name="uq_classroom_student_name"),
    )

    # Relationships
    classroom: Mapped["Classroom"] = relationship(back_populates="students")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="student")


class ClassroomExam(Base, TimestampMixin, SoftDeleteMixin):
    """학급-시험 배포 단위 (v1.3: hwp_file_path, exam_qr_path 포함)"""
    __tablename__ = "classroom_exams"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    classroom_id: Mapped[str] = mapped_column(
        ForeignKey("classrooms.id"), nullable=False, index=True
    )
    exam_id: Mapped[str] = mapped_column(ForeignKey("exams.id"), nullable=False, index=True)
    opens_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    closes_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)
    hwp_file_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    exam_qr_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    status: Mapped[str] = mapped_column(
        String(30), nullable=False, default="DEPLOY_REQUESTED"
    )
    # DEPLOY_REQUESTED / HWP_GENERATING / HWP_REVIEW / DEPLOY_READY
    # / SCHEDULED / ACTIVE / CLOSED / DEPLOY_CANCELLED
    time_limit_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Relationships
    classroom: Mapped["Classroom"] = relationship(back_populates="exams")
    exam: Mapped["Exam"] = relationship(back_populates="classroom_exams")
    submissions: Mapped[list["Submission"]] = relationship(back_populates="classroom_exam")
