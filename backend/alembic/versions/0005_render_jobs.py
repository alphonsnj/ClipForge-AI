"""Add durable 9:16 render jobs and private export metadata."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0005_render_jobs"
down_revision: str | None = "0004_youtube_references"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "render_jobs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("project_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("source_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("candidate_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("stage", sa.String(length=24), nullable=False),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("aspect_ratio", sa.String(length=8), nullable=False),
        sa.Column("output_width", sa.Integer(), nullable=False),
        sa.Column("output_height", sa.Integer(), nullable=False),
        sa.Column("caption_mode", sa.String(length=16), nullable=False),
        sa.Column("reserved_size_bytes", sa.Integer(), nullable=False),
        sa.Column("output_key", sa.String(length=80), nullable=True),
        sa.Column("caption_key", sa.String(length=80), nullable=True),
        sa.Column("output_size_bytes", sa.Integer(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("max_attempts", sa.Integer(), nullable=False),
        sa.Column("retry_allowed", sa.Boolean(), nullable=False),
        sa.Column("lease_token", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failure_code", sa.String(length=48), nullable=True),
        sa.Column("failure_message", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued', 'validating', 'rendering', 'complete', 'failed', 'cancelled')",
            name="ck_render_jobs_status",
        ),
        sa.CheckConstraint("caption_mode IN ('burn_in', 'sidecar')", name="ck_render_jobs_caption_mode"),
        sa.CheckConstraint("attempt_count >= 0 AND max_attempts >= 1", name="ck_render_jobs_attempts"),
        sa.CheckConstraint("reserved_size_bytes >= 0", name="ck_render_jobs_reservation_nonnegative"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["source_id"], ["sources.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["candidate_id"], ["highlight_candidates.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("output_key"),
        sa.UniqueConstraint("caption_key"),
    )
    op.create_index("ix_render_jobs_project_id", "render_jobs", ["project_id"])
    op.create_index("ix_render_jobs_source_id", "render_jobs", ["source_id"])
    op.create_index("ix_render_jobs_candidate_id", "render_jobs", ["candidate_id"])
    op.create_index("ix_render_jobs_status", "render_jobs", ["status"])
    op.create_index("ix_render_jobs_expires_at", "render_jobs", ["expires_at"])
    op.create_index(
        "uq_render_jobs_active_candidate",
        "render_jobs",
        ["candidate_id"],
        unique=True,
        postgresql_where=sa.text("status IN ('queued', 'validating', 'rendering')"),
    )


def downgrade() -> None:
    op.drop_index("uq_render_jobs_active_candidate", table_name="render_jobs")
    op.drop_index("ix_render_jobs_expires_at", table_name="render_jobs")
    op.drop_index("ix_render_jobs_status", table_name="render_jobs")
    op.drop_index("ix_render_jobs_candidate_id", table_name="render_jobs")
    op.drop_index("ix_render_jobs_source_id", table_name="render_jobs")
    op.drop_index("ix_render_jobs_project_id", table_name="render_jobs")
    op.drop_table("render_jobs")
