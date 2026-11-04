"""Provider-neutral local accounts, owner invitations, and team membership."""

import asyncio
import hashlib
import hmac
import os
import re
import secrets
from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import (AuthContext, CSRF_COOKIE, SESSION_COOKIE, auth_context,
                   current_user, enforce_access, enforce_csrf, enforce_same_origin,
                   require_owner, token_digest)
from .db import get_session
from .models import (AuthSession, Project, Team, TeamInvitation, TeamMembership,
                     User, utc_now)
from .schemas import AccountCredentials, InvitationAccept, PasswordChange, TeamCreate, TeamInvitationCreate

router = APIRouter(tags=["accounts"])
team_router = APIRouter(prefix="/api/teams", tags=["teams"], dependencies=[Depends(enforce_access)])
Session = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]
ContextDep = Annotated[AuthContext, Depends(auth_context)]
MAX_LOGIN_FAILURES = 10
LOGIN_WINDOW_SECONDS = 900
_INCREMENT_LOGIN_FAILURE = """
local count = redis.call('INCR', KEYS[1])
if count == 1 then
  redis.call('EXPIRE', KEYS[1], ARGV[1])
end
return count
"""


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    derived = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**15, r=8, p=1, dklen=32, maxmem=128 * 1024 * 1024)
    return f"scrypt$32768$8$1${salt.hex()}${derived.hex()}"


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, n, r, p, salt_hex, digest_hex = encoded.split("$")
        if algorithm != "scrypt":
            return False
        derived = hashlib.scrypt(password.encode("utf-8"), salt=bytes.fromhex(salt_hex), n=int(n), r=int(r), p=int(p), dklen=len(bytes.fromhex(digest_hex)), maxmem=128 * 1024 * 1024)
        return hmac.compare_digest(derived.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD_HASH = hash_password("clipforge-dummy-password-never-valid")


def normalize_email(value: str) -> str:
    normalized = value.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", normalized):
        raise HTTPException(422, "Enter a valid email address.")
    return normalized


def _set_session_cookies(response: Response, session_token: str, csrf_token: str) -> None:
    secure = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
    max_age = 60 * 60 * 24 * 14
    response.set_cookie(SESSION_COOKIE, session_token, max_age=max_age, httponly=True, secure=secure, samesite="lax", path="/")
    response.set_cookie(CSRF_COOKIE, csrf_token, max_age=max_age, httponly=False, secure=secure, samesite="lax", path="/")


def _clear_session_cookies(response: Response) -> None:
    secure = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
    response.delete_cookie(SESSION_COOKIE, path="/", secure=secure, httponly=True, samesite="lax")
    response.delete_cookie(CSRF_COOKIE, path="/", secure=secure, httponly=False, samesite="lax")


async def _new_session(db: AsyncSession, user: User, response: Response) -> str:
    raw_session = secrets.token_urlsafe(32)
    csrf = secrets.token_urlsafe(32)
    db.add(AuthSession(user_id=user.id, token_hash=token_digest(raw_session), csrf_hash=token_digest(csrf), expires_at=utc_now() + timedelta(days=14)))
    await db.flush()
    _set_session_cookies(response, raw_session, csrf)
    return csrf


async def _account_payload(db: AsyncSession, user: User, csrf: str) -> dict[str, object]:
    rows = await db.execute(select(Team, TeamMembership.role).join(TeamMembership, TeamMembership.team_id == Team.id).where(TeamMembership.user_id == user.id).order_by(Team.name))
    return {"user": {"id": str(user.id), "email": user.email},
            "teams": [{"id": str(team.id), "name": team.name, "role": role} for team, role in rows.all()],
            "csrf_token": csrf}


def _login_failure_key(request: Request) -> str:
    address = request.client.host if request.client else "unknown"
    secret = os.getenv(
        "LOGIN_RATE_LIMIT_HASH_KEY",
        "clipforge-development-only-login-rate-key-change-before-deployment",
    ).encode("utf-8")
    digest = hmac.new(secret, address.encode("utf-8"), hashlib.sha256).hexdigest()
    return f"clipforge:auth:login-failures:{digest}"


async def _check_login_rate(redis: Redis, key: str) -> None:
    try:
        failures = int(await redis.get(key) or 0)
    except RedisError:
        raise HTTPException(503, "Sign-in is temporarily unavailable. Please try again shortly.") from None
    if failures >= MAX_LOGIN_FAILURES:
        raise HTTPException(429, "Too many sign-in attempts. Wait 15 minutes and try again.")


@router.get("/api/auth/status")
async def auth_status(session: Session) -> dict[str, bool]:
    count = await session.scalar(select(func.count(User.id)))
    return {"needs_setup": int(count or 0) == 0}


@router.post("/api/auth/register", status_code=status.HTTP_201_CREATED)
async def register_first_owner(payload: AccountCredentials, request: Request, response: Response, session: Session) -> dict[str, object]:
    enforce_same_origin(request)
    await session.execute(text("SELECT pg_advisory_xact_lock(1128813132, 6)"))
    count = await session.scalar(select(func.count(User.id)))
    if count:
        raise HTTPException(409, "The first workspace owner is already registered. Accept an invitation to join.")
    password_hash = await asyncio.to_thread(hash_password, payload.password)
    user = User(email=normalize_email(payload.email), password_hash=password_hash)
    session.add(user)
    try:
        await session.flush()
        team = await session.scalar(select(Team).where(~select(TeamMembership.id).where(TeamMembership.team_id == Team.id).exists()).order_by(Team.created_at).limit(1))
        if team is None:
            team = Team(name=f"{user.email.split('@', 1)[0]}'s workspace")
            session.add(team)
            await session.flush()
        else:
            team.name = f"{user.email.split('@', 1)[0]}'s workspace"
        session.add(TeamMembership(team_id=team.id, user_id=user.id, role="owner"))
        await session.execute(Project.__table__.update().where(Project.team_id == team.id, Project.created_by_user_id.is_(None)).values(created_by_user_id=user.id))
        csrf = await _new_session(session, user, response)
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "Account setup was already completed. Sign in instead.") from None
    return await _account_payload(session, user, csrf)


@router.post("/api/auth/login")
async def login(payload: AccountCredentials, request: Request, response: Response, session: Session) -> dict[str, object]:
    enforce_same_origin(request)
    redis: Redis | None = getattr(request.app.state, "redis", None)
    if redis is None:
        raise HTTPException(503, "Sign-in is temporarily unavailable. Please try again shortly.")
    failure_key = _login_failure_key(request)
    await _check_login_rate(redis, failure_key)
    email = normalize_email(payload.email)
    user = await session.scalar(select(User).where(User.email == email))
    valid = await asyncio.to_thread(verify_password, payload.password, user.password_hash if user else DUMMY_PASSWORD_HASH)
    if not user or not valid:
        try:
            failures = int(await redis.eval(_INCREMENT_LOGIN_FAILURE, 1, failure_key, LOGIN_WINDOW_SECONDS))
        except RedisError:
            raise HTTPException(503, "Sign-in is temporarily unavailable. Please try again shortly.") from None
        if failures > MAX_LOGIN_FAILURES:
            raise HTTPException(429, "Too many sign-in attempts. Wait 15 minutes and try again.")
        raise HTTPException(401, "Email or password is incorrect.")
    csrf = await _new_session(session, user, response)
    await session.commit()
    return await _account_payload(session, user, csrf)


@router.get("/api/auth/me")
async def who_am_i(context: ContextDep, request: Request) -> dict[str, object]:
    csrf = request.cookies.get(CSRF_COOKIE, "")
    if not csrf or not hmac.compare_digest(token_digest(csrf), context.session.csrf_hash):
        raise HTTPException(401, "Your session needs to be refreshed. Sign in again.")
    return await _account_payload(context.db, context.user, csrf)


@router.post("/api/auth/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, context: ContextDep, response: Response) -> Response:
    enforce_csrf(request, context)
    context.session.revoked_at = utc_now()
    await context.db.commit()
    _clear_session_cookies(response)
    return response


@router.post("/api/auth/invitations/accept")
async def accept_invitation(payload: InvitationAccept, request: Request, response: Response, session: Session) -> dict[str, object]:
    enforce_same_origin(request)
    invitation = await session.scalar(select(TeamInvitation).where(TeamInvitation.token_hash == token_digest(payload.token), TeamInvitation.accepted_at.is_(None), TeamInvitation.expires_at > utc_now()).with_for_update())
    if invitation is None or invitation.email != normalize_email(payload.email):
        raise HTTPException(400, "This invitation is invalid, expired, or does not match the email address.")
    user = await session.scalar(select(User).where(User.email == invitation.email))
    if user is None:
        user = User(email=invitation.email, password_hash=await asyncio.to_thread(hash_password, payload.password))
        session.add(user)
        try:
            await session.flush()
        except IntegrityError:
            await session.rollback()
            raise HTTPException(409, "An account with this email was created. Sign in and accept the invitation again.") from None
    elif not await asyncio.to_thread(verify_password, payload.password, user.password_hash):
        raise HTTPException(400, "This invitation is invalid, expired, or the account password is incorrect.")
    existing = await session.scalar(select(TeamMembership.id).where(TeamMembership.team_id == invitation.team_id, TeamMembership.user_id == user.id))
    if existing is None:
        session.add(TeamMembership(team_id=invitation.team_id, user_id=user.id, role=invitation.role))
    invitation.accepted_at = utc_now()
    csrf = await _new_session(session, user, response)
    await session.commit()
    return await _account_payload(session, user, csrf)


@router.post("/api/auth/password")
async def change_password(payload: PasswordChange, request: Request, response: Response, context: ContextDep) -> dict[str, object]:
    enforce_csrf(request, context)
    if not await asyncio.to_thread(verify_password, payload.current_password, context.user.password_hash):
        raise HTTPException(401, "Current password is incorrect.")
    context.user.password_hash = await asyncio.to_thread(hash_password, payload.new_password)
    await context.db.execute(AuthSession.__table__.update().where(AuthSession.user_id == context.user.id).values(revoked_at=utc_now()))
    csrf = await _new_session(context.db, context.user, response)
    await context.db.commit()
    return await _account_payload(context.db, context.user, csrf)


@team_router.get("/{team_id}/members")
async def list_team_members(team_id: UUID, session: Session, user: UserDep) -> list[dict[str, str]]:
    own = await session.scalar(select(TeamMembership.id).where(TeamMembership.team_id == team_id, TeamMembership.user_id == user.id))
    if own is None:
        raise HTTPException(404, "Workspace not found.")
    rows = await session.execute(select(User.email, TeamMembership.role, TeamMembership.id).join(TeamMembership, TeamMembership.user_id == User.id).where(TeamMembership.team_id == team_id).order_by(TeamMembership.created_at))
    return [{"email": email, "role": role, "membership_id": str(membership_id)} for email, role, membership_id in rows.all()]


@team_router.post("", status_code=status.HTTP_201_CREATED)
async def create_team(payload: TeamCreate, session: Session, user: UserDep) -> dict[str, object]:
    name = " ".join(payload.name.split())
    if not name:
        raise HTTPException(422, "Workspace name cannot be blank.")
    team = Team(name=name)
    session.add(team)
    await session.flush()
    session.add(TeamMembership(team_id=team.id, user_id=user.id, role="owner"))
    await session.commit()
    return {"id": str(team.id), "name": team.name, "role": "owner"}


@team_router.post("/{team_id}/invitations", status_code=201)
async def create_invitation(team_id: UUID, payload: TeamInvitationCreate, session: Session, user: UserDep) -> dict[str, object]:
    await require_owner(session, team_id, user.id)
    email = normalize_email(payload.email)
    existing_user = await session.scalar(select(TeamMembership.id).join(User, User.id == TeamMembership.user_id).where(TeamMembership.team_id == team_id, User.email == email))
    if existing_user:
        raise HTTPException(409, "This person already belongs to the workspace.")
    raw = secrets.token_urlsafe(32)
    invitation = TeamInvitation(team_id=team_id, email=email, role=payload.role, token_hash=token_digest(raw), expires_at=utc_now() + timedelta(hours=24), created_by_user_id=user.id)
    session.add(invitation)
    await session.commit()
    base = os.getenv("FRONTEND_BASE_URL", "http://localhost:3000").rstrip("/")
    return {"email": email, "role": payload.role, "expires_at": invitation.expires_at.isoformat(), "invite_url": f"{base}/workspace?invite={raw}"}


@team_router.delete("/{team_id}/members/{membership_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_team_member(team_id: UUID, membership_id: UUID, session: Session, user: UserDep) -> Response:
    await require_owner(session, team_id, user.id)
    member = await session.scalar(select(TeamMembership).where(TeamMembership.id == membership_id, TeamMembership.team_id == team_id).with_for_update())
    if member is None:
        raise HTTPException(404, "Workspace member not found.")
    if member.role == "owner":
        owner_count = await session.scalar(select(func.count(TeamMembership.id)).where(TeamMembership.team_id == team_id, TeamMembership.role == "owner"))
        if int(owner_count or 0) <= 1:
            raise HTTPException(409, "A workspace must keep at least one owner.")
    await session.delete(member)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
