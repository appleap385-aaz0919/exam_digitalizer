from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from .base import Base, TimestampMixin


class PipelineState(Base, TimestampMixin):
    """파이프라인 현재 상태 (문항/시험지/배포 단위)"""
    __tablename__ = "pipeline_states"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    ref_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    # L1: pkey(QI-xxx), L2A: exam_id, L2B: classroom_exam_id(string)
    pipeline_level: Mapped[str] = mapped_column(String(10), nullable=False)  # L1 / L2A / L2B
    current_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="IN_PROGRESS")
    # IN_PROGRESS / COMPLETED / ERROR / HUMAN_REVIEW
    reject_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    last_agent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    last_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    reject_context: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    timeout_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)


class PipelineHistory(Base):
    """파이프라인 상태 변경 이력 (BIGSERIAL — 대량 이력)"""
    __tablename__ = "pipeline_history"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    ref_id: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    pipeline_level: Mapped[str] = mapped_column(String(10), nullable=False)
    from_stage: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    to_stage: Mapped[str] = mapped_column(String(30), nullable=False)
    agent: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    action: Mapped[str] = mapped_column(String(20), nullable=False)  # ADVANCE / REJECT / ERROR
    score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    score_detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        index=True,
    )
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
