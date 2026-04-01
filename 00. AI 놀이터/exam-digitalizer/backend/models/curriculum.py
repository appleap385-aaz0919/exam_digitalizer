"""교과과정 표준체계 + 학습맵 모델

구조:
  curriculum_standards (420행) — 성취기준, 내용체계, 내용요소 3단계
  learning_maps (1,821행) — 학습맵 트리 (Depth 1~4)
  learning_map_standards (N:M) — 학습맵 노드 ↔ 표준체계 매핑

교사 UX 흐름:
  학습맵 Depth1(대단원) → Depth2(중단원) → Depth3(소단원) 선택
  → 해당 노드의 표준체계ID → 문항 리스팅
"""
from typing import Optional

from sqlalchemy import ForeignKey, Integer, String, Text, Boolean, Index
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import Base, TimestampMixin


class CurriculumStandard(Base, TimestampMixin):
    """교과과정 표준체계 (2022 개정, 420개 항목)"""
    __tablename__ = "curriculum_standards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    standard_id: Mapped[str] = mapped_column(
        String(30), unique=True, nullable=False, index=True,
    )  # E4MATA01B01C01
    revision_year: Mapped[int] = mapped_column(Integer, nullable=False)  # 2022
    subject_group: Mapped[str] = mapped_column(String(50), nullable=False)  # 수학과
    subject: Mapped[str] = mapped_column(String(50), nullable=False, index=True)  # 수학
    grade_group: Mapped[str] = mapped_column(String(20), nullable=False)  # "3, 4"
    content_area: Mapped[str] = mapped_column(String(100), nullable=False)  # 수와 연산
    content_element_1: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 1단계
    content_element_2: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 2단계
    content_element_3: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 3단계
    achievement_code: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # [4수01-01]
    achievement_desc: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="사용")
    knowledge_map_ids: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # pipe 구분

    # Relationships
    learning_map_links: Mapped[list["LearningMapStandard"]] = relationship(
        back_populates="standard",
    )

    __table_args__ = (
        Index("ix_cs_subject_area", "subject", "content_area"),
    )


class LearningMap(Base, TimestampMixin):
    """학습맵 트리 노드 (수학 1,821개)"""
    __tablename__ = "learning_maps"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learning_map_id: Mapped[str] = mapped_column(
        String(80), unique=True, nullable=False, index=True,
    )  # 2022-2025-MAT-MAT-03-1-MN1-01-01-00-00
    short_id: Mapped[Optional[str]] = mapped_column(String(30), nullable=True)  # 03-1-MN1-01-01
    revision_year: Mapped[int] = mapped_column(Integer, nullable=False)  # 2022
    publish_year: Mapped[int] = mapped_column(Integer, nullable=False)  # 2025
    subject_group: Mapped[str] = mapped_column(String(10), nullable=False)  # MAT
    subject_code: Mapped[str] = mapped_column(String(10), nullable=False)  # MAT
    school_level: Mapped[str] = mapped_column(String(5), nullable=False)  # E(초)/M(중)/H(고)
    grade: Mapped[int] = mapped_column(Integer, nullable=False)  # 3
    semester: Mapped[int] = mapped_column(Integer, nullable=False)  # 1
    map_number: Mapped[str] = mapped_column(String(10), nullable=False)  # MN1

    # 트리 구조 (Depth 1~4)
    depth1_number: Mapped[str] = mapped_column(String(10), nullable=False)  # 01
    depth1_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)  # 덧셈과 뺄셈
    depth2_number: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 01
    depth2_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    depth3_number: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # 01
    depth3_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    depth4_number: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    depth4_name: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)

    status: Mapped[str] = mapped_column(String(20), nullable=True)
    is_leaf: Mapped[bool] = mapped_column(Boolean, default=False)  # 최하위 노드 여부

    # Relationships
    standard_links: Mapped[list["LearningMapStandard"]] = relationship(
        back_populates="learning_map",
    )

    __table_args__ = (
        Index("ix_lm_grade_semester", "school_level", "grade", "semester"),
        Index("ix_lm_tree", "depth1_number", "depth2_number", "depth3_number"),
    )


class LearningMapStandard(Base):
    """학습맵 ↔ 표준체계 N:M 매핑"""
    __tablename__ = "learning_map_standards"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    learning_map_id: Mapped[int] = mapped_column(
        ForeignKey("learning_maps.id"), nullable=False, index=True,
    )
    standard_id: Mapped[int] = mapped_column(
        ForeignKey("curriculum_standards.id"), nullable=False, index=True,
    )

    # Relationships
    learning_map: Mapped["LearningMap"] = relationship(back_populates="standard_links")
    standard: Mapped["CurriculumStandard"] = relationship(back_populates="learning_map_links")

    __table_args__ = (
        Index("ix_lms_unique", "learning_map_id", "standard_id", unique=True),
    )
