"""initial schema

Revision ID: 001
Revises:
Create Date: 2025-04-01 00:00:00.000000

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # pgvector 확장 활성화
    op.execute("CREATE EXTENSION IF NOT EXISTS vector;")

    # ─── users ────────────────────────────────────────────────
    op.create_table(
        "users",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("last_login_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_users_email", "users", ["email"], unique=True)

    # ─── batches ──────────────────────────────────────────────
    op.create_table(
        "batches",
        sa.Column("id", sa.String(20), primary_key=True),
        sa.Column("original_hwp_path", sa.String(500), nullable=True),
        sa.Column("answer_sheet_path", sa.String(500), nullable=True),
        sa.Column("subject", sa.String(50), nullable=False, server_default="수학"),
        sa.Column("grade", sa.Integer, nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="UPLOADED"),
        sa.Column("total_questions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("uploaded_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # ─── question_groups ──────────────────────────────────────
    op.create_table(
        "question_groups",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("batch_id", sa.String(20), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("group_label", sa.String(50), nullable=True),
        sa.Column("passage_text", sa.Text, nullable=True),
        sa.Column("passage_html", sa.Text, nullable=True),
        sa.Column("group_type", sa.String(30), nullable=False, server_default="passage"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_question_groups_batch_id", "question_groups", ["batch_id"])

    # ─── questions ────────────────────────────────────────────
    op.create_table(
        "questions",
        sa.Column("pkey", sa.String(30), primary_key=True),
        sa.Column("batch_id", sa.String(20), sa.ForeignKey("batches.id"), nullable=False),
        sa.Column("seq_num", sa.Integer, nullable=False),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("current_stage", sa.String(30), nullable=False, server_default="PARSING"),
        sa.Column("reject_count", sa.Integer, nullable=False, server_default="0"),
        # v1.4 패치 #1
        sa.Column("confirmed_by", sa.Integer, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("confirmed_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_questions_batch_id", "questions", ["batch_id"])

    # ─── question_raw ─────────────────────────────────────────
    op.create_table(
        "question_raw",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pkey", sa.String(30), sa.ForeignKey("questions.pkey"), nullable=False),
        sa.Column("raw_text", sa.Text, nullable=True),
        sa.Column("raw_html", sa.Text, nullable=True),
        sa.Column("images", postgresql.JSONB, nullable=True),
        sa.Column("formulas", postgresql.JSONB, nullable=True),
        sa.Column("parse_source", sa.String(20), nullable=False, server_default="hwpml"),
        sa.Column("parse_score", sa.Float, nullable=True),
        sa.Column("parse_issues", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_question_raw_pkey", "question_raw", ["pkey"], unique=True)

    # ─── question_structured ──────────────────────────────────
    op.create_table(
        "question_structured",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pkey", sa.String(30), sa.ForeignKey("questions.pkey"), nullable=False),
        sa.Column("question_text", sa.Text, nullable=True),
        sa.Column("question_latex", sa.Text, nullable=True),
        sa.Column("choices", postgresql.JSONB, nullable=True),
        sa.Column("passage", sa.Text, nullable=True),
        sa.Column("images_processed", postgresql.JSONB, nullable=True),
        sa.Column("question_type", sa.String(20), nullable=True),
        sa.Column("group_id", sa.Integer, sa.ForeignKey("question_groups.id"), nullable=True),
        sa.Column("meta_score", sa.Float, nullable=True),
        sa.Column("meta_issues", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_question_structured_pkey", "question_structured", ["pkey"], unique=True)

    # ─── question_produced ────────────────────────────────────
    op.create_table(
        "question_produced",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pkey", sa.String(30), sa.ForeignKey("questions.pkey"), nullable=False),
        sa.Column("content_html", sa.Text, nullable=True),
        sa.Column("content_latex", sa.Text, nullable=True),
        sa.Column("answer_correct", postgresql.JSONB, nullable=True),
        sa.Column("answer_source", sa.String(20), nullable=False, server_default="answer_sheet"),
        sa.Column("render_html", sa.Text, nullable=True),
        sa.Column("xapi_config", postgresql.JSONB, nullable=True),  # v1.4 패치 #2
        sa.Column("prod_score", sa.Float, nullable=True),
        sa.Column("prod_issues", postgresql.JSONB, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_question_produced_pkey", "question_produced", ["pkey"], unique=True)

    # ─── question_metadata ────────────────────────────────────
    op.create_table(
        "question_metadata",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pkey", sa.String(30), sa.ForeignKey("questions.pkey"), nullable=False),
        sa.Column("subject", sa.String(50), nullable=True),
        sa.Column("grade", sa.Integer, nullable=True),
        sa.Column("unit", sa.String(100), nullable=True),
        sa.Column("difficulty", sa.String(10), nullable=True),
        sa.Column("bloom_level", sa.String(20), nullable=True),
        sa.Column("question_type", sa.String(20), nullable=True),
        sa.Column("is_multiple_answer", sa.Boolean, nullable=False, server_default="false"),  # v1.4 패치 #3
        sa.Column("tags", postgresql.JSONB, nullable=True),
        sa.Column("schema_version", sa.String(10), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_question_metadata_pkey", "question_metadata", ["pkey"], unique=True)
    # v1.3 복합 인덱스: 유사문항 검색 최적화
    op.create_index(
        "ix_qmeta_subject_grade_unit_diff",
        "question_metadata",
        ["subject", "grade", "unit", "difficulty"],
    )

    # ─── question_embeddings (pgvector HNSW) ──────────────────
    op.create_table(
        "question_embeddings",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pkey", sa.String(30), sa.ForeignKey("questions.pkey"), nullable=False),
        sa.Column("embedding", sa.String),  # vector(1536) — raw DDL로 처리
        sa.Column("embedding_model", sa.String(50), nullable=False, server_default="text-embedding-3-small"),
        sa.Column("embedded_text", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_question_embeddings_pkey", "question_embeddings", ["pkey"], unique=True)

    # vector 컬럼 타입을 올바르게 교체 + HNSW 인덱스 생성
    op.execute("ALTER TABLE question_embeddings ALTER COLUMN embedding TYPE vector(1536) USING embedding::vector(1536);")
    op.execute(
        "CREATE INDEX ix_qemb_hnsw ON question_embeddings USING hnsw (embedding vector_cosine_ops);"
    )

    # ─── pipeline_states ──────────────────────────────────────
    op.create_table(
        "pipeline_states",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("ref_id", sa.String(50), nullable=False),
        sa.Column("pipeline_level", sa.String(10), nullable=False),
        sa.Column("current_stage", sa.String(30), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("reject_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("last_agent", sa.String(50), nullable=True),
        sa.Column("last_score", sa.Float, nullable=True),
        sa.Column("reject_context", postgresql.JSONB, nullable=True),
        sa.Column("timeout_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_pipeline_states_ref_id", "pipeline_states", ["ref_id"])

    # ─── pipeline_history ─────────────────────────────────────
    op.create_table(
        "pipeline_history",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("ref_id", sa.String(50), nullable=False),
        sa.Column("pipeline_level", sa.String(10), nullable=False),
        sa.Column("from_stage", sa.String(30), nullable=True),
        sa.Column("to_stage", sa.String(30), nullable=False),
        sa.Column("agent", sa.String(50), nullable=True),
        sa.Column("action", sa.String(20), nullable=False),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("score_detail", postgresql.JSONB, nullable=True),
        sa.Column("version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("note", sa.Text, nullable=True),
    )
    op.create_index("ix_pipeline_history_ref_id", "pipeline_history", ["ref_id"])
    op.create_index("ix_pipeline_history_created_at", "pipeline_history", ["created_at"])

    # ─── exams ────────────────────────────────────────────────
    op.create_table(
        "exams",
        sa.Column("id", sa.String(30), primary_key=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("subject", sa.String(50), nullable=False, server_default="수학"),
        sa.Column("grade", sa.Integer, nullable=True),
        sa.Column("created_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("status", sa.String(30), nullable=False, server_default="EXAM_COMPOSE"),
        sa.Column("total_questions", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_points", sa.Integer, nullable=False, server_default="0"),
        sa.Column("time_limit_minutes", sa.Integer, nullable=True),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("preview_html_path", sa.String(500), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )

    # ─── exam_questions ───────────────────────────────────────
    op.create_table(
        "exam_questions",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("exam_id", sa.String(30), sa.ForeignKey("exams.id"), nullable=False),
        sa.Column("pkey", sa.String(30), sa.ForeignKey("questions.pkey"), nullable=False),
        sa.Column("seq_order", sa.Integer, nullable=False),
        sa.Column("points_auto", sa.Float, nullable=True),
        sa.Column("points_modified", sa.Float, nullable=True),
        sa.Column("points_current", sa.Float, nullable=False, server_default="0"),
        sa.Column("is_points_modified", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("exam_id", "seq_order", name="uq_exam_question_seq"),
        sa.UniqueConstraint("exam_id", "pkey", name="uq_exam_question_pkey"),
    )
    op.create_index("ix_exam_questions_exam_id", "exam_questions", ["exam_id"])

    # ─── classrooms ───────────────────────────────────────────
    op.create_table(
        "classrooms",
        sa.Column("id", sa.String(36), primary_key=True),  # UUID
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("teacher_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("invite_code", sa.String(20), nullable=False),
        sa.Column("grade", sa.Integer, nullable=True),
        sa.Column("subject", sa.String(50), nullable=True),
        sa.Column("invite_qr_path", sa.String(500), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_classrooms_teacher_id", "classrooms", ["teacher_id"])
    op.create_index("ix_classrooms_invite_code", "classrooms", ["invite_code"], unique=True)

    # ─── classroom_students ───────────────────────────────────
    op.create_table(
        "classroom_students",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("classroom_id", sa.String(36), sa.ForeignKey("classrooms.id"), nullable=False),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("student_number", sa.Integer, nullable=True),
        sa.Column("is_self_registered", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("classroom_id", "name", name="uq_classroom_student_name"),
    )
    op.create_index("ix_classroom_students_classroom_id", "classroom_students", ["classroom_id"])

    # ─── classroom_exams ──────────────────────────────────────
    op.create_table(
        "classroom_exams",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("classroom_id", sa.String(36), sa.ForeignKey("classrooms.id"), nullable=False),
        sa.Column("exam_id", sa.String(30), sa.ForeignKey("exams.id"), nullable=False),
        sa.Column("opens_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("closes_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("hwp_file_path", sa.String(500), nullable=True),
        sa.Column("exam_qr_path", sa.String(500), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="DEPLOY_REQUESTED"),
        sa.Column("time_limit_minutes", sa.Integer, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("deleted_at", sa.TIMESTAMP(timezone=True), nullable=True),
    )
    op.create_index("ix_classroom_exams_classroom_id", "classroom_exams", ["classroom_id"])
    op.create_index("ix_classroom_exams_exam_id", "classroom_exams", ["exam_id"])

    # ─── submissions ──────────────────────────────────────────
    op.create_table(
        "submissions",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("classroom_exam_id", sa.Integer, sa.ForeignKey("classroom_exams.id"), nullable=False),
        sa.Column("student_id", sa.Integer, sa.ForeignKey("classroom_students.id"), nullable=False),
        sa.Column("started_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("is_auto_submitted", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("status", sa.String(20), nullable=False, server_default="IN_PROGRESS"),
        sa.Column("total_score", sa.Float, nullable=True),
        sa.Column("session_id", sa.String(100), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_submissions_classroom_exam_id", "submissions", ["classroom_exam_id"])
    op.create_index("ix_submissions_student_id", "submissions", ["student_id"])

    # ─── submission_answers ───────────────────────────────────
    op.create_table(
        "submission_answers",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("submission_id", sa.BigInteger, sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("pkey", sa.String(30), sa.ForeignKey("questions.pkey"), nullable=False),
        sa.Column("seq_order", sa.Integer, nullable=False),
        sa.Column("answer_type", sa.String(30), nullable=False),
        sa.Column("value", sa.Text, nullable=True),
        sa.Column("is_correct", sa.Boolean, nullable=True),
        sa.Column("score", sa.Float, nullable=True),
        sa.Column("answered_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_submission_answers_submission_id", "submission_answers", ["submission_id"])

    # ─── grade_results ────────────────────────────────────────
    op.create_table(
        "grade_results",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("submission_id", sa.BigInteger, sa.ForeignKey("submissions.id"), nullable=False),
        sa.Column("total_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("max_score", sa.Float, nullable=False, server_default="0"),
        sa.Column("percentage", sa.Float, nullable=True),
        sa.Column("correct_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("total_count", sa.Integer, nullable=False, server_default="0"),
        sa.Column("score_detail", postgresql.JSONB, nullable=True),
        sa.Column("graded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("graded_by", sa.String(20), nullable=False, server_default="auto"),
        sa.Column("delivered_to_student_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("delivered_to_teacher_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.UniqueConstraint("submission_id", name="uq_grade_result_submission"),
    )

    # ─── answer_corrections ───────────────────────────────────
    op.create_table(
        "answer_corrections",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("pkey", sa.String(30), sa.ForeignKey("questions.pkey"), nullable=False),
        sa.Column("exam_id", sa.String(30), sa.ForeignKey("exams.id"), nullable=True),
        sa.Column("before_answer", postgresql.JSONB, nullable=True),
        sa.Column("after_answer", postgresql.JSONB, nullable=True),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("corrected_by", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("is_regraded", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("regraded_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_answer_corrections_pkey", "answer_corrections", ["pkey"])

    # ─── notifications ────────────────────────────────────────
    op.create_table(
        "notifications",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("body", sa.Text, nullable=True),
        sa.Column("ref_type", sa.String(30), nullable=True),
        sa.Column("ref_id", sa.String(50), nullable=True),
        sa.Column("is_read", sa.Boolean, nullable=False, server_default="false"),
        sa.Column("read_at", sa.TIMESTAMP(timezone=True), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_notifications_user_id", "notifications", ["user_id"])

    # ─── ai_execution_logs ────────────────────────────────────
    op.create_table(
        "ai_execution_logs",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column("agent", sa.String(50), nullable=False),
        sa.Column("ref_id", sa.String(50), nullable=True),
        sa.Column("model", sa.String(50), nullable=False),
        sa.Column("prompt_tokens", sa.Integer, nullable=True),
        sa.Column("completion_tokens", sa.Integer, nullable=True),
        sa.Column("total_tokens", sa.Integer, nullable=True),
        sa.Column("cost_usd", sa.Float, nullable=True),
        sa.Column("duration_ms", sa.Integer, nullable=True),
        sa.Column("status", sa.String(20), nullable=False, server_default="success"),
        sa.Column("error_message", sa.Text, nullable=True),
        sa.Column("request_hash", sa.String(64), nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_ai_execution_logs_agent", "ai_execution_logs", ["agent"])
    op.create_index("ix_ai_execution_logs_created_at", "ai_execution_logs", ["created_at"])

    # ─── meta_schemas ─────────────────────────────────────────
    op.create_table(
        "meta_schemas",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("subject", sa.String(50), nullable=False),
        sa.Column("version", sa.String(10), nullable=False, server_default="1.0"),
        sa.Column("schema_def", postgresql.JSONB, nullable=False),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
        sa.Column("description", sa.Text, nullable=True),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("ix_meta_schemas_subject", "meta_schemas", ["subject"])


def downgrade() -> None:
    # 역순으로 테이블 삭제
    tables_to_drop = [
        "meta_schemas",
        "ai_execution_logs",
        "notifications",
        "answer_corrections",
        "grade_results",
        "submission_answers",
        "submissions",
        "classroom_exams",
        "classroom_students",
        "classrooms",
        "exam_questions",
        "exams",
        "pipeline_history",
        "pipeline_states",
        "question_embeddings",
        "question_metadata",
        "question_produced",
        "question_structured",
        "question_raw",
        "questions",
        "question_groups",
        "batches",
        "users",
    ]
    for table in tables_to_drop:
        op.drop_table(table)

    op.execute("DROP EXTENSION IF EXISTS vector;")
