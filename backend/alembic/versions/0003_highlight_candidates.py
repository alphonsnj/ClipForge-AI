"""Add transcript-aligned highlight candidate runs and review records.

Revision ID: 0003_highlight_candidates
Revises: 0002_transcription
Create Date: 2026-11-03
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0003_highlight_candidates"
down_revision: str | None = "0002_transcription"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "candidate_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("transcription_job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("min_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("max_duration_seconds", sa.Integer(), nullable=False),
        sa.Column("candidate_limit", sa.Integer(), nullable=False),
        sa.Column("total_candidates", sa.Integer(), nullable=False),
        sa.Column("sampled_evenly", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["transcription_job_id"], ["transcription_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("min_duration_seconds >= 1", name="ck_candidate_runs_min_duration_positive"),
        sa.CheckConstraint("max_duration_seconds >= min_duration_seconds", name="ck_candidate_runs_duration_range"),
        sa.CheckConstraint("max_duration_seconds <= 3600", name="ck_candidate_runs_max_duration"),
        sa.CheckConstraint("candidate_limit BETWEEN 1 AND 100", name="ck_candidate_runs_candidate_limit"),
        sa.CheckConstraint("total_candidates >= 0", name="ck_candidate_runs_total_nonnegative"),
    )
    op.create_index("ix_candidate_runs_project_id", "candidate_runs", ["project_id"])
    op.create_index("ix_candidate_runs_source_id", "candidate_runs", ["source_id"])
    op.create_index("ix_candidate_runs_transcription_job_id", "candidate_runs", ["transcription_job_id"])

    op.create_table(
        "highlight_candidates",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=120), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("transcript_excerpt", sa.Text(), nullable=False),
        sa.Column("signals", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["candidate_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("run_id", "ordinal", name="uq_highlight_candidates_run_ordinal"),
        sa.CheckConstraint("ordinal >= 0", name="ck_highlight_candidates_ordinal_nonnegative"),
        sa.CheckConstraint("start_ms >= 0", name="ck_highlight_candidates_start_nonnegative"),
        sa.CheckConstraint("end_ms > start_ms", name="ck_highlight_candidates_bounds"),
        sa.CheckConstraint(
            "status IN ('suggested', 'selected', 'edited', 'rejected')",
            name="ck_highlight_candidates_status",
        ),
    )
    op.create_index("ix_highlight_candidates_run_id", "highlight_candidates", ["run_id"])
    op.create_index("ix_highlight_candidates_status", "highlight_candidates", ["status"])


def downgrade() -> None:
    op.drop_index("ix_highlight_candidates_status", table_name="highlight_candidates")
    op.drop_index("ix_highlight_candidates_run_id", table_name="highlight_candidates")
    op.drop_table("highlight_candidates")
    op.drop_index("ix_candidate_runs_transcription_job_id", table_name="candidate_runs")
    op.drop_index("ix_candidate_runs_source_id", table_name="candidate_runs")
    op.drop_index("ix_candidate_runs_project_id", table_name="candidate_runs")
    op.drop_table("candidate_runs")
