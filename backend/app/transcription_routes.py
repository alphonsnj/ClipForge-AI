"""Durable transcription job and transcript endpoints."""

import logging
import os
from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .db import get_session
from .auth import enforce_access
from .models import Project, Source, TranscriptionJob, TranscriptSegment
from .schemas import TranscriptionJobCreate, TranscriptionJobRead, TranscriptSegmentRead
from .worker import QUEUE_NAME

logger = logging.getLogger(__name__)
router = APIRouter(tags=["transcription"], dependencies=[Depends(enforce_access)])
Session = Annotated[AsyncSession, Depends(get_session)]
ACTIVE_STATUSES = ("queued", "validating", "extracting", "transcribing", "saving")


async def notify_worker(job_id: UUID) -> None:
    """Wake a worker; PostgreSQL polling remains the recovery path if Redis is down."""
    client: Redis | None = None
    try:
        client = Redis.from_url(
            os.getenv("REDIS_URL", "redis://localhost:6379/0"),
            socket_connect_timeout=1,
            socket_timeout=1,
            decode_responses=True,
        )
        await client.lpush(QUEUE_NAME, str(job_id))
    except (RedisError, OSError, ValueError):
        logger.warning("Could not notify worker for durable job %s; it will be found by polling", job_id)
    finally:
        if client is not None:
            try:
                await client.aclose()
            except Exception:
                logger.debug("Redis connection close failed after notification", exc_info=True)


@router.post(
    "/api/projects/{project_id}/transcription-jobs",
    response_model=TranscriptionJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_transcription_job(
    project_id: UUID,
    payload: TranscriptionJobCreate,
    session: Session,
) -> TranscriptionJob:
    project = await session.scalar(
        select(Project).options(selectinload(Project.sources)).where(Project.id == project_id)
    )
    if project is None:
        raise HTTPException(404, "Project not found.")
    now = datetime.now(timezone.utc)
    source = next((item for item in project.sources if item.expires_at > now), None)
    if source is None:
        raise HTTPException(409, "Add a current source video before starting transcription.")

    existing = await session.scalar(
        select(TranscriptionJob)
        .where(
            TranscriptionJob.source_id == source.id,
            TranscriptionJob.status.in_(ACTIVE_STATUSES),
        )
        .order_by(TranscriptionJob.created_at.desc())
    )
    if existing is not None:
        return existing

    job = TranscriptionJob(
        project_id=project.id,
        source_id=source.id,
        status="queued",
        stage="queued",
        attempt_count=0,
        max_attempts=3,
        model_id=os.getenv("WHISPER_MODEL_ID", "small"),
        model_revision=os.getenv("WHISPER_MODEL_REVISION") or None,
        requested_language=payload.language,
        retry_allowed=False,
    )
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        existing = await session.scalar(
            select(TranscriptionJob).where(
                TranscriptionJob.source_id == source.id,
                TranscriptionJob.status.in_(ACTIVE_STATUSES),
            )
        )
        if existing is None:
            raise HTTPException(409, "A transcription job could not be created. Try again.")
        job = existing
    else:
        await session.refresh(job)
    await notify_worker(job.id)
    return job


@router.get(
    "/api/transcription-jobs/{job_id}",
    response_model=TranscriptionJobRead,
)
async def get_transcription_job(job_id: UUID, session: Session) -> TranscriptionJob:
    job = await session.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Transcription job not found.")
    return job


@router.get(
    "/api/transcription-jobs/{job_id}/transcript",
    response_model=list[TranscriptSegmentRead],
)
async def get_transcript(job_id: UUID, session: Session) -> list[TranscriptSegment]:
    job = await session.get(TranscriptionJob, job_id)
    if job is None:
        raise HTTPException(404, "Transcription job not found.")
    if job.status != "complete":
        raise HTTPException(409, "The transcript is available after transcription completes.")
    result = await session.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.job_id == job.id)
        .order_by(TranscriptSegment.ordinal)
    )
    return list(result.all())


@router.post(
    "/api/transcription-jobs/{job_id}/retry",
    response_model=TranscriptionJobRead,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retry_transcription_job(job_id: UUID, session: Session) -> TranscriptionJob:
    job = await session.scalar(
        select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()
    )
    if job is None:
        raise HTTPException(404, "Transcription job not found.")
    if not job.retryable:
        raise HTTPException(409, "This job cannot be retried. Start a new job after fixing the source or configuration.")
    current_source = await session.scalar(
        select(Source.id).where(
            Source.id == job.source_id,
            Source.project_id == job.project_id,
            Source.expires_at > datetime.now(timezone.utc),
        )
    )
    if current_source is None:
        raise HTTPException(409, "The source was deleted or expired. Add a current source before retrying.")
    job.status = "queued"
    job.stage = "queued"
    job.progress_percent = None
    job.retry_allowed = False
    job.failure_code = None
    job.failure_message = None
    job.started_at = None
    job.finished_at = None
    job.lease_token = None
    job.lease_expires_at = None
    await session.commit()
    await session.refresh(job)
    await notify_worker(job.id)
    return job


@router.post(
    "/api/transcription-jobs/{job_id}/cancel",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_transcription_job(job_id: UUID, session: Session) -> Response:
    job = await session.scalar(
        select(TranscriptionJob).where(TranscriptionJob.id == job_id).with_for_update()
    )
    if job is None:
        raise HTTPException(404, "Transcription job not found.")
    if job.status not in ACTIVE_STATUSES:
        raise HTTPException(409, "Only an active transcription job can be cancelled.")
    job.status = "cancelled"
    job.stage = "cancelled"
    job.retry_allowed = False
    job.lease_token = None
    job.lease_expires_at = None
    job.finished_at = datetime.now(timezone.utc)
    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
