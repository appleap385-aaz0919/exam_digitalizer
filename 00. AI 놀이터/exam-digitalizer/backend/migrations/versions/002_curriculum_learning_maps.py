"""add curriculum_standards, learning_maps, learning_map_standards

Revision ID: 002
Revises: 001
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "curriculum_standards",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("standard_id", sa.String(30), nullable=False),
        sa.Column("revision_year", sa.Integer, nullable=False),
        sa.Column("subject_group", sa.String(50), nullable=False),
        sa.Column("subject", sa.String(50), nullable=False),
        sa.Column("grade_group", sa.String(20), nullable=False),
        sa.Column("content_area", sa.String(100), nullable=False),
        sa.Column("content_element_1", sa.String(200), nullable=True),
        sa.Column("content_element_2", sa.String(200), nullable=True),
        sa.Column("content_element_3", sa.String(200), nullable=True),
        sa.Column("achievement_code", sa.String(30), nullable=True),
        sa.Column("achievement_desc", sa.Text, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="사용"),
        sa.Column("knowledge_map_ids", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_cs_standard_id", "curriculum_standards", ["standard_id"], unique=True)
    op.create_index("ix_cs_subject", "curriculum_standards", ["subject"])
    op.create_index("ix_cs_subject_area", "curriculum_standards", ["subject", "content_area"])

    op.create_table(
        "learning_maps",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("learning_map_id", sa.String(80), nullable=False),
        sa.Column("short_id", sa.String(30), nullable=True),
        sa.Column("revision_year", sa.Integer, nullable=False),
        sa.Column("publish_year", sa.Integer, nullable=False),
        sa.Column("subject_group", sa.String(10), nullable=False),
        sa.Column("subject_code", sa.String(10), nullable=False),
        sa.Column("school_level", sa.String(5), nullable=False),
        sa.Column("grade", sa.Integer, nullable=False),
        sa.Column("semester", sa.Integer, nullable=False),
        sa.Column("map_number", sa.String(10), nullable=False),
        sa.Column("depth1_number", sa.String(10), nullable=False),
        sa.Column("depth1_name", sa.String(200), nullable=True),
        sa.Column("depth2_number", sa.String(10), nullable=True),
        sa.Column("depth2_name", sa.String(200), nullable=True),
        sa.Column("depth3_number", sa.String(10), nullable=True),
        sa.Column("depth3_name", sa.String(200), nullable=True),
        sa.Column("depth4_number", sa.String(10), nullable=True),
        sa.Column("depth4_name", sa.String(200), nullable=True),
        sa.Column("status", sa.String(20), nullable=True),
        sa.Column("is_leaf", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_lm_learning_map_id", "learning_maps", ["learning_map_id"], unique=True)
    op.create_index("ix_lm_grade_semester", "learning_maps", ["school_level", "grade", "semester"])
    op.create_index("ix_lm_tree", "learning_maps", ["depth1_number", "depth2_number", "depth3_number"])

    op.create_table(
        "learning_map_standards",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("learning_map_id", sa.Integer, sa.ForeignKey("learning_maps.id"), nullable=False),
        sa.Column("standard_id", sa.Integer, sa.ForeignKey("curriculum_standards.id"), nullable=False),
    )
    op.create_index("ix_lms_lm", "learning_map_standards", ["learning_map_id"])
    op.create_index("ix_lms_std", "learning_map_standards", ["standard_id"])
    op.create_index("ix_lms_unique", "learning_map_standards", ["learning_map_id", "standard_id"], unique=True)


def downgrade() -> None:
    op.drop_table("learning_map_standards")
    op.drop_table("learning_maps")
    op.drop_table("curriculum_standards")
