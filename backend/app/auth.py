"""Cookie sessions, CSRF checks, and team-role authorization."""

import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import get_session
from .models import AuthSession, CandidateRun, HighlightCandidate, Project, RenderJob, TeamMembership, TranscriptionJob, User, utc_now

SESSION_COOKIE = "clipforge_session"
CSRF_COOKIE = "clipforge_csrf"
SESSION_DAYS = 14
Session = Annotated[AsyncSession, Depends(get_session)]


def token_digest(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def enforce_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    allowed = {item.strip() for item in os.getenv("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if item.strip()}
    if not origin or origin not in allowed:
        raise HTTPException(403, "The request origin could not be verified.")


def enforce_csrf(request: Request, context: "AuthContext") -> None:
    enforce_same_origin(request)
    csrf_cookie = request.cookies.get(CSRF_COOKIE, "")
    csrf_header = request.headers.get("x-csrf-token", "")
    if not csrf_cookie or not hmac.compare_digest(csrf_cookie, csrf_header) or not hmac.compare_digest(token_digest(csrf_cookie), context.session.csrf_hash):
        raise HTTPException(403, "The CSRF token could not be verified.")


@dataclass
class AuthContext:
    user: User
    session: AuthSession
    db: AsyncSession


async def auth_context(request: Request, db: Session) -> AuthContext:
    raw = request.cookies.get(SESSION_COOKIE)
    if not raw:
        raise HTTPException(401, "Sign in to continue.")
    auth_session = await db.scalar(select(AuthSession).where(
        AuthSession.token_hash == token_digest(raw),
        AuthSession.revoked_at.is_(None),
        AuthSession.expires_at > utc_now(),
    ))
    if auth_session is None:
        raise HTTPException(401, "Your session expired. Sign in again.")
    user = await db.get(User, auth_session.user_id)
    if user is None:
        raise HTTPException(401, "Your account is unavailable. Sign in again.")
    return AuthContext(user=user, session=auth_session, db=db)


async def current_user(context: Annotated[AuthContext, Depends(auth_context)]) -> User:
    return context.user


async def _team_for_path(request: Request, db: AsyncSession) -> UUID | None:
    parts = request.url.path.strip("/").split("/")
    if len(parts) < 3 or parts[0] != "api":
        return None
    resource, raw_id = parts[1], parts[2]
    try:
        resource_id = UUID(raw_id)
    except ValueError:
        return None
    if resource == "projects":
        return await db.scalar(select(Project.team_id).where(Project.id == resource_id))
    if resource == "transcription-jobs":
        return await db.scalar(select(Project.team_id).join(TranscriptionJob, TranscriptionJob.project_id == Project.id).where(TranscriptionJob.id == resource_id))
    if resource == "candidates":
        return await db.scalar(select(Project.team_id).join(CandidateRun, CandidateRun.project_id == Project.id).join(HighlightCandidate, HighlightCandidate.run_id == CandidateRun.id).where(HighlightCandidate.id == resource_id))
    if resource == "render-jobs":
        return await db.scalar(select(Project.team_id).join(RenderJob, RenderJob.project_id == Project.id).where(RenderJob.id == resource_id))
    return None


async def enforce_access(request: Request, context: Annotated[AuthContext, Depends(auth_context)]) -> None:
    if request.method not in {"GET", "HEAD", "OPTIONS"}:
        enforce_csrf(request, context)

    team_id = await _team_for_path(request, context.db)
    if team_id is None:
        return
    membership = await context.db.scalar(select(TeamMembership).where(
        TeamMembership.team_id == team_id,
        TeamMembership.user_id == context.user.id,
    ))
    if membership is None:
        raise HTTPException(404, "Project or job not found.")
    if request.method not in {"GET", "HEAD", "OPTIONS"} and membership.role == "reviewer":
        raise HTTPException(403, "Reviewer access is read-only.")
    if request.method == "DELETE" and membership.role != "owner":
        raise HTTPException(403, "Only a workspace owner can delete a project or source.")


async def require_owner(db: AsyncSession, team_id: UUID, user_id: UUID) -> TeamMembership:
    membership = await db.scalar(select(TeamMembership).where(
        TeamMembership.team_id == team_id,
        TeamMembership.user_id == user_id,
        TeamMembership.role == "owner",
    ))
    if membership is None:
        raise HTTPException(403, "Workspace owner access is required.")
    return membership
