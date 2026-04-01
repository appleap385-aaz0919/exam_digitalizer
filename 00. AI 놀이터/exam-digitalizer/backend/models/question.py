from datetime import datetime
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Float, ForeignKey, Integer,
    String, Text, TIMESTAMP, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from pgvector.sqlalchemy import Vector

from .base import Base, TimestampMixin, SoftDeleteMixin


class Batch(Base, TimestampMixin, SoftDeleteMixin):
    """HWP 파일 업로드 배치"""
    __tablename__ = "batches"

    id: Mapped[str] = mapped_column(String(20), primary_key=True)  # QI-YYYYMM-NNN
    original_hwp_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    answer_sheet_path: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    subject: Mapped[str] = mapped_column(String(50), nullable=False, default="수학")
    grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="UPLOADED")
    total_questions: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    uploaded_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)

    # Relationships
    questions: Mapped[list["Question"]] = relationship(back_populates="batch")


class Question(Base, TimestampMixin, SoftDeleteMixin):
    """문항 마스터 — PKey: QI-{배치}-{순번}-{버전}"""
    __tablename__ = "questions"

    pkey: Mapped[str] = mapped_column(String(30), primary_key=True)  # QI-YYYYMM-NNN-VVV
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), nullable=False, index=True)
    seq_num: Mapped[int] = mapped_column(Integer, nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    current_stage: Mapped[str] = mapped_column(String(30), nullable=False, default="PARSING")
    reject_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # v1.4 패치 #1: 정답 확인 이력
    confirmed_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True)
    confirmed_at: Mapped[Optional[datetime]] = mapped_column(TIMESTAMP(timezone=True), nullable=True)

    # Relationships
    batch: Mapped["Batch"] = relationship(back_populates="questions")
    raw: Mapped[Optional["QuestionRaw"]] = relationship(back_populates="question", uselist=False)
    structured: Mapped[Optional["QuestionStructured"]] = relationship(
        back_populates="question", uselist=False
    )
    produced: Mapped[Optional["QuestionProduced"]] = relationship(
        back_populates="question", uselist=False
    )
    embedding: Mapped[Optional["QuestionEmbedding"]] = relationship(
        back_populates="question", uselist=False
    )
    metadata_: Mapped[Optional["QuestionMetadata"]] = relationship(
        back_populates="question", uselist=False, foreign_keys="QuestionMetadata.pkey"
    )


class QuestionRaw(Base, TimestampMixin):
    """파싱팀(#1) 출력 — 원본 파싱 결과"""
    __tablename__ = "question_raw"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pkey: Mapped[str] = mapped_column(ForeignKey("questions.pkey"), nullable=False, unique=True)
    raw_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    images: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    formulas: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    parse_source: Mapped[str] = mapped_column(String(20), nullable=False, default="hwpml")
    parse_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    parse_issues: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    question: Mapped["Question"] = relationship(back_populates="raw")


class QuestionStructured(Base, TimestampMixin):
    """메타팀(#3) 출력 — 구조화된 문항"""
    __tablename__ = "question_structured"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pkey: Mapped[str] = mapped_column(ForeignKey("questions.pkey"), nullable=False, unique=True)
    question_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    question_latex: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    choices: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    passage: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    images_processed: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    question_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    group_id: Mapped[Optional[int]] = mapped_column(ForeignKey("question_groups.id"), nullable=True)
    meta_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    meta_issues: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    question: Mapped["Question"] = relationship(back_populates="structured")
    group: Mapped[Optional["QuestionGroup"]] = relationship(back_populates="structured_questions")


class QuestionProduced(Base, TimestampMixin):
    """제작팀(#5) 출력 — 최종 제작 문항 (v1.4: xapi_config 임시 JSONB)"""
    __tablename__ = "question_produced"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pkey: Mapped[str] = mapped_column(ForeignKey("questions.pkey"), nullable=False, unique=True)
    content_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_latex: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    answer_correct: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # answer_correct 구조:
    # { "correct": [3], "is_multiple": false, "scoring_mode": "any" }  -- 단일
    # { "correct": [2, 4], "is_multiple": true, "scoring_mode": "all" } -- 복수
    answer_source: Mapped[str] = mapped_column(
        String(20), nullable=False, default="answer_sheet"
    )  # answer_sheet / ai_derived / teacher_input
    render_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    xapi_config: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)  # v1.4 패치 #2 임시
    prod_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    prod_issues: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)

    # Relationships
    question: Mapped["Question"] = relationship(back_populates="produced")


class QuestionEmbedding(Base, TimestampMixin):
    """벡터 임베딩 (pgvector, HNSW 인덱스)"""
    __tablename__ = "question_embeddings"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pkey: Mapped[str] = mapped_column(ForeignKey("questions.pkey"), nullable=False, unique=True)
    embedding: Mapped[Optional[list]] = mapped_column(Vector(1536), nullable=True)
    embedding_model: Mapped[str] = mapped_column(
        String(50), nullable=False, default="text-embedding-3-small"
    )
    embedded_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    question: Mapped["Question"] = relationship(back_populates="embedding")


class QuestionMetadata(Base, TimestampMixin):
    """문항 메타정보 (v1.4: is_multiple_answer 추가)"""
    __tablename__ = "question_metadata"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    pkey: Mapped[str] = mapped_column(
        ForeignKey("questions.pkey"), nullable=False, unique=True
    )
    subject: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    grade: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    difficulty: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 상/중/하
    bloom_level: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    question_type: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    is_multiple_answer: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )  # v1.4 패치 #3
    tags: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    schema_version: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)

    # 학습맵 + 표준체계 연결 (② 메타팀 고도화)
    learning_map_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("learning_maps.id"), nullable=True, index=True,
    )
    achievement_code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)
    achievement_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    content_area: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    school_level: Mapped[Optional[str]] = mapped_column(String(5), nullable=True)

    __table_args__ = (
        # v1.3 복합 인덱스: 유사문항 검색 최적화
        Index("ix_qmeta_subject_grade_unit_diff", "subject", "grade", "unit", "difficulty"),
    )

    # Relationships
    question: Mapped["Question"] = relationship(
        back_populates="metadata_", foreign_keys=[pkey]
    )
    learning_map: Mapped[Optional["LearningMap"]] = relationship()


class QuestionGroup(Base, TimestampMixin):
    """세트 문항 그룹 (예: [1-3] 지문 기반 문항)"""
    __tablename__ = "question_groups"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    batch_id: Mapped[str] = mapped_column(ForeignKey("batches.id"), nullable=False, index=True)
    group_label: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)  # "[1-3]" 등
    passage_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    passage_html: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    group_type: Mapped[str] = mapped_column(String(30), nullable=False, default="passage")

    # Relationships
    structured_questions: Mapped[list["QuestionStructured"]] = relationship(
        back_populates="group"
    )
