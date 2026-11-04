"""Add local accounts, teams, invitations, sessions, and project ownership."""

from typing import Sequence
from uuid import uuid4

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0009_accounts_and_teams"
down_revision: str | None = "0007_creator_editor_state"
branch_labels: Sequence[str] | None = None
depends_on: Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("password_hash", sa.String(255), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
    )
    op.create_table(
        "teams",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "team_memberships",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('owner', 'editor', 'reviewer')", name="ck_team_memberships_role"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("team_id", "user_id", name="uq_team_memberships_team_user"),
    )
    op.create_index("ix_team_memberships_team_id", "team_memberships", ["team_id"])
    op.create_index("ix_team_memberships_user_id", "team_memberships", ["user_id"])
    op.create_table(
        "auth_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("csrf_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_auth_sessions_user_id", "auth_sessions", ["user_id"])
    op.create_index("ix_auth_sessions_expires_at", "auth_sessions", ["expires_at"])
    op.create_table(
        "team_invitations",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("role", sa.String(16), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("role IN ('editor', 'reviewer')", name="ck_team_invitations_role"),
        sa.ForeignKeyConstraint(["team_id"], ["teams.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"), sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_team_invitations_team_id", "team_invitations", ["team_id"])
    op.create_index("ix_team_invitations_expires_at", "team_invitations", ["expires_at"])

    legacy_team_id = uuid4()
    teams = sa.table("teams", sa.column("id", postgresql.UUID(as_uuid=True)), sa.column("name", sa.String()))
    op.bulk_insert(teams, [{"id": legacy_team_id, "name": "Local workspace"}])
    op.add_column("projects", sa.Column("team_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("projects", sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True))
    projects = sa.table("projects", sa.column("team_id", postgresql.UUID(as_uuid=True)))
    op.execute(projects.update().values(team_id=legacy_team_id))
    op.alter_column("projects", "team_id", nullable=False)
    op.create_foreign_key("fk_projects_team_id_teams", "projects", "teams", ["team_id"], ["id"], ondelete="CASCADE")
    op.create_foreign_key("fk_projects_created_by_user_id_users", "projects", "users", ["created_by_user_id"], ["id"], ondelete="SET NULL")
    op.create_index("ix_projects_team_id", "projects", ["team_id"])
    op.create_index("ix_projects_created_by_user_id", "projects", ["created_by_user_id"])


def downgrade() -> None:
    op.drop_index("ix_projects_created_by_user_id", table_name="projects")
    op.drop_index("ix_projects_team_id", table_name="projects")
    op.drop_constraint("fk_projects_created_by_user_id_users", "projects", type_="foreignkey")
    op.drop_constraint("fk_projects_team_id_teams", "projects", type_="foreignkey")
    op.drop_column("projects", "created_by_user_id")
    op.drop_column("projects", "team_id")
    op.drop_index("ix_team_invitations_expires_at", table_name="team_invitations")
    op.drop_index("ix_team_invitations_team_id", table_name="team_invitations")
    op.drop_table("team_invitations")
    op.drop_index("ix_auth_sessions_expires_at", table_name="auth_sessions")
    op.drop_index("ix_auth_sessions_user_id", table_name="auth_sessions")
    op.drop_table("auth_sessions")
    op.drop_index("ix_team_memberships_user_id", table_name="team_memberships")
    op.drop_index("ix_team_memberships_team_id", table_name="team_memberships")
    op.drop_table("team_memberships")
    op.drop_table("teams")
    op.drop_table("users")
