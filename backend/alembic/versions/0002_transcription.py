"""Add durable transcription jobs and timestamped transcript segments.

Revision ID: 0002_transcription
Revises: 0001_projects_sources
Create Date: 2026-11-03
"""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002_transcription"
down_revision: str | None = "0001_projects_sources"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "transcription_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_allowed", sa.Boolean(), nullable=False),
        sa.Column("model_id", sa.String(length=80), nullable=False),
        sa.Column("model_revision", sa.String(length=120), nullable=True),
        sa.Column("requested_language", sa.String(length=12), nullable=True),
        sa.Column("detected_language", sa.String(length=12), nullable=True),
        sa.Column("language_probability", sa.Float(), nullable=True),
        sa.Column("failure_code", sa.String(length=48), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_transcription_jobs_project_id", "transcription_jobs", ["project_id"])
    op.create_index("ix_transcription_jobs_source_id", "transcription_jobs", ["source_id"])
    op.create_index("ix_transcription_jobs_status", "transcription_jobs", ["status"])
    op.create_index(
        "uq_transcription_jobs_active_source",
        "transcription_jobs",
        ["source_id"],
        unique=True,
        postgresql_where=sa.text(
            "status IN ('queued', 'validating', 'extracting', 'transcribing', 'saving')"
        ),
    )

    op.create_table(
        "transcript_segments",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ordinal", sa.Integer(), nullable=False),
        sa.Column("start_ms", sa.Integer(), nullable=False),
        sa.Column("end_ms", sa.Integer(), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.CheckConstraint("ordinal >= 0", name="ck_transcript_segments_ordinal_nonnegative"),
        sa.CheckConstraint("start_ms >= 0", name="ck_transcript_segments_start_nonnegative"),
        sa.CheckConstraint("end_ms > start_ms", name="ck_transcript_segments_bounds"),
        sa.ForeignKeyConstraint(["job_id"], ["transcription_jobs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("job_id", "ordinal", name="uq_transcript_segments_job_ordinal"),
    )
    op.create_index("ix_transcript_segments_job_id", "transcript_segments", ["job_id"])


def downgrade() -> None:
    op.drop_index("ix_transcript_segments_job_id", table_name="transcript_segments")
    op.drop_table("transcript_segments")
    op.drop_index("uq_transcription_jobs_active_source", table_name="transcription_jobs")
    op.drop_index("ix_transcription_jobs_status", table_name="transcription_jobs")
    op.drop_index("ix_transcription_jobs_source_id", table_name="transcription_jobs")
    op.drop_index("ix_transcription_jobs_project_id", table_name="transcription_jobs")
    op.drop_table("transcription_jobs")
