"""Snapshot clip in/out points on the durable render job."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0006_render_range_snapshot"
down_revision: str | None = "0005_render_jobs"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("render_jobs", sa.Column("start_ms", sa.Integer(), nullable=True))
    op.add_column("render_jobs", sa.Column("end_ms", sa.Integer(), nullable=True))
    op.execute("UPDATE render_jobs r SET start_ms = c.start_ms, end_ms = c.end_ms FROM highlight_candidates c WHERE c.id = r.candidate_id")
    op.alter_column("render_jobs", "start_ms", nullable=False)
    op.alter_column("render_jobs", "end_ms", nullable=False)
    op.create_check_constraint("ck_render_jobs_bounds", "render_jobs", "start_ms >= 0 AND end_ms > start_ms")


def downgrade() -> None:
    op.drop_constraint("ck_render_jobs_bounds", "render_jobs", type_="check")
    op.drop_column("render_jobs", "end_ms")
    op.drop_column("render_jobs", "start_ms")
