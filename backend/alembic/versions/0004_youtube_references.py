"""Store user-submitted YouTube video references."""

from typing import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "0004_youtube_references"
down_revision: str | None = "0003_highlight_candidates"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("youtube_url", sa.String(length=255), nullable=True))
    op.add_column("projects", sa.Column("youtube_video_id", sa.String(length=11), nullable=True))
    op.add_column("projects", sa.Column("youtube_rights_confirmed_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "youtube_rights_confirmed_at")
    op.drop_column("projects", "youtube_video_id")
    op.drop_column("projects", "youtube_url")
