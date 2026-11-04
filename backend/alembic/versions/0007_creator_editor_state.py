"""Persist caption, crop, focus, and preset edits and snapshot them for renders."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0007_creator_editor_state"
down_revision: str | None = "0006_render_range_snapshot"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("highlight_candidates", sa.Column("caption_edits", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("highlight_candidates", sa.Column("editor_settings", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.add_column("render_jobs", sa.Column("crop_mode", sa.String(length=16), nullable=False, server_default="fit_blur"))
    op.add_column("render_jobs", sa.Column("focus_x", sa.Float(), nullable=False, server_default="0.5"))
    op.add_column("render_jobs", sa.Column("focus_y", sa.Float(), nullable=False, server_default="0.5"))
    op.add_column("render_jobs", sa.Column("caption_edits", sa.JSON(), nullable=False, server_default=sa.text("'{}'")))
    op.alter_column("highlight_candidates", "caption_edits", server_default=None)
    op.alter_column("highlight_candidates", "editor_settings", server_default=None)
    op.alter_column("render_jobs", "crop_mode", server_default=None)
    op.alter_column("render_jobs", "focus_x", server_default=None)
    op.alter_column("render_jobs", "focus_y", server_default=None)
    op.alter_column("render_jobs", "caption_edits", server_default=None)


def downgrade() -> None:
    op.drop_column("render_jobs", "caption_edits")
    op.drop_column("render_jobs", "focus_y")
    op.drop_column("render_jobs", "focus_x")
    op.drop_column("render_jobs", "crop_mode")
    op.drop_column("highlight_candidates", "editor_settings")
    op.drop_column("highlight_candidates", "caption_edits")
