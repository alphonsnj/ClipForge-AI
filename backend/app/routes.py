"""Project and source intake API."""

import asyncio
import logging
import re
from contextlib import suppress
from datetime import datetime, timedelta, timezone
from typing import Annotated
from uuid import UUID
from urllib.parse import parse_qs, urlparse

from fastapi import APIRouter, Depends, File, Form, HTTPException, Response, UploadFile, status
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .db import get_session
from .auth import current_user, enforce_access
from .intake import (
    MAX_MEDIA_STORAGE_BYTES,
    SOURCE_RETENTION_DAYS,
    ValidatedMedia,
    ensure_storage_dir,
    finalize_media,
    safe_storage_path,
    spool_and_validate,
    unlink_media,
)
from .models import CandidateRun, HighlightCandidate, Project, RenderJob, Source, TeamMembership, User, utc_now
from .schemas import ProjectCreate, ProjectRead, YouTubeReferenceCreate
from .rendering import unlink_render_key


def remove_source_renders(jobs: list[RenderJob]) -> None:
    for job in jobs:
        unlink_render_key(job.output_key)
        unlink_render_key(job.caption_key)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/projects", tags=["projects"], dependencies=[Depends(enforce_access)])
Session = Annotated[AsyncSession, Depends(get_session)]
UserDep = Annotated[User, Depends(current_user)]


def normalize_youtube_url(value: str) -> tuple[str, str]:
    """Accept common YouTube video URLs without making a network request."""
    try:
        parsed = urlparse(value.strip())
        host = (parsed.hostname or "").lower().rstrip(".")
        if (
            parsed.scheme not in {"http", "https"}
            or parsed.username
            or parsed.password
            or parsed.port is not None
        ):
            raise ValueError
        video_id = None
        if host in {"youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com", "youtube-nocookie.com", "www.youtube-nocookie.com"}:
            pieces = [part for part in parsed.path.split("/") if part]
            if parsed.path == "/watch":
                video_id = parse_qs(parsed.query).get("v", [None])[0]
            elif len(pieces) == 2 and pieces[0] in {"shorts", "embed", "live"}:
                video_id = pieces[1]
        elif host == "youtu.be":
            pieces = [part for part in parsed.path.split("/") if part]
            if len(pieces) == 1:
                video_id = pieces[0]
        if not video_id or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise ValueError
        return f"https://www.youtube.com/watch?v={video_id}", video_id
    except (ValueError, AttributeError):
        raise HTTPException(422, "Enter a valid YouTube video URL (watch, youtu.be, shorts, or live link).") from None


@router.put("/{project_id}/youtube-reference", response_model=ProjectRead)
async def save_youtube_reference(
    project_id: UUID,
    payload: YouTubeReferenceCreate,
    session: Session,
) -> Project:
    if not payload.rights_confirmed:
        raise HTTPException(400, "Confirm that you own this video or have permission to use it.")
    project = await session.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        raise HTTPException(404, "Project not found.")
    project.youtube_url, project.youtube_video_id = normalize_youtube_url(payload.url)
    project.youtube_rights_confirmed_at = utc_now()
    await session.commit()
    result = await session.scalar(
        select(Project)
        .options(
            selectinload(Project.sources),
            selectinload(Project.transcription_jobs),
            selectinload(Project.candidate_runs).selectinload(CandidateRun.candidates).selectinload(HighlightCandidate.render_jobs),
        )
        .where(Project.id == project_id)
    )
    if result is None:
        raise HTTPException(500, "The YouTube reference was saved but could not be loaded.")
    return result


@router.delete("/{project_id}/youtube-reference", status_code=status.HTTP_204_NO_CONTENT)
async def delete_youtube_reference(project_id: UUID, session: Session) -> Response:
    project = await session.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        raise HTTPException(404, "Project not found.")
    project.youtube_url = None
    project.youtube_video_id = None
    project.youtube_rights_confirmed_at = None
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("", response_model=list[ProjectRead])
async def list_projects(session: Session, user: UserDep) -> list[Project]:
    result = await session.scalars(
        select(Project)
        .join(TeamMembership, TeamMembership.team_id == Project.team_id)
        .where(TeamMembership.user_id == user.id)
        .options(
            selectinload(Project.sources),
            selectinload(Project.transcription_jobs),
            selectinload(Project.candidate_runs).selectinload(CandidateRun.candidates).selectinload(HighlightCandidate.render_jobs),
        )
        .order_by(Project.created_at.desc())
    )
    return list(result.unique().all())


@router.post("", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def create_project(payload: ProjectCreate, session: Session, user: UserDep) -> Project:
    name = " ".join(payload.name.split())
    if not name:
        raise HTTPException(422, "Project name cannot be blank.")
    membership_query = select(TeamMembership).where(TeamMembership.user_id == user.id, TeamMembership.role.in_(("owner", "editor")))
    if payload.team_id is not None:
        membership_query = membership_query.where(TeamMembership.team_id == payload.team_id)
    membership = await session.scalar(membership_query.order_by(TeamMembership.created_at).limit(1))
    if membership is None:
        raise HTTPException(403, "Choose a workspace where you have editor access.")
    project = Project(name=name, team_id=membership.team_id, created_by_user_id=user.id)
    session.add(project)
    await session.commit()
    created = await session.scalar(
        select(Project)
        .options(
            selectinload(Project.sources),
            selectinload(Project.transcription_jobs),
            selectinload(Project.candidate_runs).selectinload(CandidateRun.candidates).selectinload(HighlightCandidate.render_jobs),
        )
        .execution_options(populate_existing=True)
        .where(Project.id == project.id)
    )
    if created is None:
        raise HTTPException(500, "The project was created but could not be loaded.")
    return created


@router.get("/{project_id}", response_model=ProjectRead)
async def get_project(project_id: UUID, session: Session) -> Project:
    project = await session.scalar(
        select(Project)
        .options(
            selectinload(Project.sources),
            selectinload(Project.transcription_jobs),
            selectinload(Project.candidate_runs).selectinload(CandidateRun.candidates).selectinload(HighlightCandidate.render_jobs),
        )
        .where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(404, "Project not found.")
    return project


@router.post("/{project_id}/source", response_model=ProjectRead, status_code=status.HTTP_201_CREATED)
async def upload_source(
    project_id: UUID,
    session: Session,
    file: Annotated[UploadFile, File(...)],
    rights_confirmed: Annotated[bool, Form(...)],
) -> Project:
    if not rights_confirmed:
        await file.close()
        raise HTTPException(400, "Confirm that you own this video or have permission to process it.")
    project = await session.scalar(
        select(Project)
        .options(selectinload(Project.sources))
        .where(Project.id == project_id)
    )
    if project is None:
        await file.close()
        raise HTTPException(404, "Project not found.")
    if project.sources:
        await file.close()
        raise HTTPException(409, "This project already has a source video.")

    media: ValidatedMedia | None = None
    try:
        used_bytes = await session.scalar(select(func.coalesce(func.sum(Source.size_bytes), 0)))
        remaining_bytes = MAX_MEDIA_STORAGE_BYTES - int(used_bytes or 0)
        media = await spool_and_validate(file, remaining_bytes)
        finalize_media(media)
        now = utc_now()
        source = Source(
            project_id=project.id,
            original_filename=(file.filename or "video").replace("\\", "/").rsplit("/", 1)[-1][:255],
            storage_key=media.storage_key,
            media_format=media.media_format,
            size_bytes=media.size_bytes,
            duration_seconds=media.duration_seconds,
            rights_confirmed_at=now,
            expires_at=now + timedelta(days=SOURCE_RETENTION_DAYS),
        )
        session.add(source)
        await session.commit()
    except Exception:
        await session.rollback()
        if media is not None:
            media.temp_path.unlink(missing_ok=True)
            media.final_path.unlink(missing_ok=True)
        raise

    created = await session.scalar(
        select(Project)
        .options(
            selectinload(Project.sources),
            selectinload(Project.transcription_jobs),
            selectinload(Project.candidate_runs).selectinload(CandidateRun.candidates).selectinload(HighlightCandidate.render_jobs),
        )
        .execution_options(populate_existing=True)
        .where(Project.id == project.id)
    )
    if created is None:
        raise HTTPException(500, "The source was saved but the project could not be loaded.")
    return created


@router.delete("/{project_id}/source", status_code=status.HTTP_204_NO_CONTENT)
async def delete_source(project_id: UUID, session: Session) -> Response:
    """Permanently remove the project's source media and intake record."""
    project = await session.scalar(
        select(Project)
        .options(selectinload(Project.sources))
        .where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(404, "Project not found.")
    if not project.sources:
        return Response(status_code=status.HTTP_204_NO_CONTENT)
    source = project.sources[0]
    try:
        jobs = list((await session.scalars(select(RenderJob).where(RenderJob.source_id == source.id))).all())
        remove_source_renders(jobs)
        unlink_media(source.storage_key)
    except (OSError, ValueError) as error:
        logger.exception("Could not remove source %s", source.id)
        raise HTTPException(500, "The source could not be deleted. Try again.") from error
    await session.delete(source)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{project_id}/source/preview")
async def preview_source(project_id: UUID, session: Session) -> FileResponse:
    project = await session.scalar(select(Project).options(selectinload(Project.sources)).where(Project.id == project_id))
    if project is None or not project.sources:
        raise HTTPException(404, "Project source not found.")
    source = project.sources[0]
    if source.expires_at <= utc_now():
        raise HTTPException(404, "Project source has expired.")
    try:
        path = safe_storage_path(source.storage_key)
    except ValueError:
        raise HTTPException(404, "Project source is unavailable.") from None
    if not path.is_file():
        raise HTTPException(404, "Project source is unavailable.")
    content_type = "video/quicktime" if source.media_format.lower() == "mov" else "video/mp4"
    return FileResponse(path, media_type=content_type, filename=source.original_filename, headers={"Cache-Control": "no-store"})


@router.delete("/{project_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_project(project_id: UUID, session: Session) -> Response:
    project = await session.scalar(
        select(Project)
        .options(selectinload(Project.sources))
        .where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(404, "Project not found.")
    try:
        for source in project.sources:
            jobs = list((await session.scalars(select(RenderJob).where(RenderJob.source_id == source.id))).all())
            remove_source_renders(jobs)
            unlink_media(source.storage_key)
    except (OSError, ValueError) as error:
        logger.exception("Could not remove media while deleting project %s", project_id)
        raise HTTPException(500, "Project media could not be deleted. Try again.") from error
    await session.delete(project)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def expire_sources_once() -> None:
    from .db import SessionFactory

    ensure_storage_dir()
    async with SessionFactory() as session:
        expired = await session.scalars(
            select(Source).where(Source.expires_at <= datetime.now(timezone.utc))
        )
        sources = list(expired.all())
        removed: list[Source] = []
        for source in sources:
            try:
                jobs = list((await session.scalars(select(RenderJob).where(RenderJob.source_id == source.id))).all())
                remove_source_renders(jobs)
                safe_storage_path(source.storage_key).unlink(missing_ok=True)
                removed.append(source)
            except (OSError, ValueError):
                logger.exception("Could not expire source %s", source.id)
        for source in removed:
            await session.delete(source)
        if removed:
            await session.commit()


async def expiry_worker() -> None:
    while True:
        try:
            await expire_sources_once()
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Source expiry cleanup failed; it will retry")
        await asyncio.sleep(300)


async def stop_expiry_worker(task: asyncio.Task[None]) -> None:
    task.cancel()
    with suppress(asyncio.CancelledError):
        await task
