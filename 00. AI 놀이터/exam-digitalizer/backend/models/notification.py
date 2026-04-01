from datetime import datetime
from typing import Optional

from sqlalchemy import BigInteger, Float, ForeignKey, Integer, String, Text, TIMESTAMP
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class Notification(Base, TimestampMixin):
    """사용자 알림"""
    __tablename__ = "notifications"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    body: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ref_type: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    ref_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    is_read: Mapped[bool] = mapped_column(default=False, nullable=False)
    read_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    user: Mapped["User"] = relationship(back_populates="notifications")


class AiExecutionLog(Base):
    """LLM API 실행 이력 (BIGSERIAL)"""
    __tablename__ = "ai_execution_logs"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    agent: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    ref_id: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    model: Mapped[str] = mapped_column(String(50), nullable=False)
    prompt_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    completion_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    total_tokens: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    duration_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="success")
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    request_hash: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, index=True
    )


class MetaSchema(Base, TimestampMixin):
    """과목별 메타 스키마 정의"""
    __tablename__ = "meta_schemas"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    subject: Mapped[str] = mapped_column(String(50), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(10), nullable=False, default="1.0")
    schema_def: Mapped[dict] = mapped_column(JSONB, nullable=False)
    # schema_def 구조:
    # {
    #   "unit": ["수와 연산", "문자와 식", ...],
    #   "difficulty": ["상", "중", "하"],
    #   "bloom_level": ["기억", "이해", "적용", ...],
    #   "question_type": ["객관식", "단답형", "서술형", "빈칸채우기"]
    # }
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
