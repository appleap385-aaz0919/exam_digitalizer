"""add learning_map_id to question_metadata + achievement fields

Revision ID: 003
Revises: 002
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # question_metadata에 학습맵/표준체계 연결 컬럼 추가
    op.add_column("question_metadata", sa.Column(
        "learning_map_id", sa.Integer,
        sa.ForeignKey("learning_maps.id"), nullable=True,
    ))
    op.add_column("question_metadata", sa.Column(
        "achievement_code", sa.String(30), nullable=True,
    ))
    op.add_column("question_metadata", sa.Column(
        "achievement_desc", sa.Text, nullable=True,
    ))
    op.add_column("question_metadata", sa.Column(
        "content_area", sa.String(100), nullable=True,
    ))
    op.add_column("question_metadata", sa.Column(
        "school_level", sa.String(5), nullable=True,
    ))
    op.create_index("ix_qmeta_learning_map_id", "question_metadata", ["learning_map_id"])


def downgrade() -> None:
    op.drop_index("ix_qmeta_learning_map_id", "question_metadata")
    op.drop_column("question_metadata", "school_level")
    op.drop_column("question_metadata", "content_area")
    op.drop_column("question_metadata", "achievement_desc")
    op.drop_column("question_metadata", "achievement_code")
    op.drop_column("question_metadata", "learning_map_id")
