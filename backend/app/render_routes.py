"""Creator-controlled local clip render and private download endpoints."""

from datetime import timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from fastapi.responses import FileResponse
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .db import get_session
from .auth import enforce_access
from .intake import safe_storage_path
from .models import CandidateRun, HighlightCandidate, RenderJob, Source, utc_now
from .rendering import (MAX_RENDER_DURATION_SECONDS, MAX_RENDER_FILE_BYTES,
                        MAX_RENDER_STORAGE_BYTES, OUTPUT_DIR, safe_render_path,
                        unlink_render_key, preset_dimensions)
from .schemas import RenderJobCreate, RenderJobRead

router = APIRouter(tags=["local clip rendering"], dependencies=[Depends(enforce_access)])
Session = Annotated[AsyncSession, Depends(get_session)]
ACTIVE = ("queued", "validating", "rendering")


def read_job(job: RenderJob) -> dict[str, object]:
    result = RenderJobRead.model_validate(job).model_dump()
    if job.status == "complete":
        result["download_url"] = f"/api/render-jobs/{job.id}/download"
        result["captions_url"] = f"/api/render-jobs/{job.id}/captions"
    return result


@router.post("/api/candidates/{candidate_id}/renders", response_model=RenderJobRead, status_code=202)
async def create_render(candidate_id: UUID, payload: RenderJobCreate, session: Session) -> dict[str, object]:
    candidate = await session.scalar(select(HighlightCandidate).options(selectinload(HighlightCandidate.run)).where(HighlightCandidate.id == candidate_id))
    if candidate is None:
        raise HTTPException(404, "Candidate not found.")
    if candidate.status not in {"selected", "edited"}:
        raise HTTPException(409, "Select or edit this candidate before rendering.")
    duration = candidate.end_ms - candidate.start_ms
    if duration <= 0 or duration > MAX_RENDER_DURATION_SECONDS * 1000:
        raise HTTPException(422, f"Render duration must be at most {MAX_RENDER_DURATION_SECONDS} seconds.")
    run = candidate.run
    source = await session.scalar(select(Source).where(Source.id == run.source_id, Source.expires_at > utc_now()))
    if source is None:
        raise HTTPException(409, "The candidate source has expired or was removed.")
    existing = await session.scalar(select(RenderJob).where(RenderJob.candidate_id == candidate.id, RenderJob.status.in_(ACTIVE)))
    if existing:
        return read_job(existing)
    used = await session.scalar(select(func.coalesce(func.sum(RenderJob.output_size_bytes), 0)).where(RenderJob.status == "complete"))
    reserved = await session.scalar(select(func.coalesce(func.sum(RenderJob.reserved_size_bytes), 0)).where(RenderJob.status.in_(ACTIVE)))
    reserve = min(MAX_RENDER_FILE_BYTES, max(16 * 1024 * 1024, duration * 1_500_000))
    if int(used or 0) + int(reserved or 0) + reserve > MAX_RENDER_STORAGE_BYTES:
        raise HTTPException(507, "Local render storage quota is full. Delete a project or clip and retry.")
    job = RenderJob(project_id=run.project_id, source_id=run.source_id, candidate_id=candidate.id,
                    status="queued", stage="queued", caption_mode=payload.caption_mode,
                    start_ms=candidate.start_ms, end_ms=candidate.end_ms,
                    aspect_ratio=(candidate.editor_settings or {}).get("aspect_ratio", "9:16"),
                    output_width=preset_dimensions((candidate.editor_settings or {}).get("aspect_ratio", "9:16"))[0],
                    output_height=preset_dimensions((candidate.editor_settings or {}).get("aspect_ratio", "9:16"))[1],
                    crop_mode=(candidate.editor_settings or {}).get("crop_mode", "fit_blur"),
                    focus_x=(candidate.editor_settings or {}).get("focus_x", 0.5),
                    focus_y=(candidate.editor_settings or {}).get("focus_y", 0.5),
                    caption_edits=candidate.caption_edits or {},
                    reserved_size_bytes=reserve, expires_at=source.expires_at)
    session.add(job)
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        raise HTTPException(409, "A render for this candidate is already queued.") from None
    await session.refresh(job)
    return read_job(job)


@router.post("/api/render-jobs/{job_id}/retry", response_model=RenderJobRead, status_code=202)
async def retry_render(job_id: UUID, session: Session) -> dict[str, object]:
    job = await session.get(RenderJob, job_id)
    if job is None:
        raise HTTPException(404, "Render job not found.")
    if not job.retryable:
        raise HTTPException(409, "This render cannot be retried.")
    job.status = "queued"; job.stage = "queued"; job.progress_percent = None
    job.retry_allowed = False; job.failure_code = None; job.failure_message = None
    job.finished_at = None
    await session.commit(); await session.refresh(job)
    return read_job(job)


@router.post("/api/render-jobs/{job_id}/cancel", response_model=RenderJobRead)
async def cancel_render(job_id: UUID, session: Session) -> dict[str, object]:
    job = await session.get(RenderJob, job_id)
    if job is None: raise HTTPException(404, "Render job not found.")
    if job.status in ACTIVE:
        job.status = "cancelled"; job.stage = "cancelled"; job.finished_at = utc_now()
        job.lease_token = None; job.lease_expires_at = None; job.reserved_size_bytes = 0
        await session.commit(); await session.refresh(job)
    return read_job(job)


async def _complete_job(job_id: UUID, session: AsyncSession) -> RenderJob:
    job = await session.scalar(select(RenderJob).where(RenderJob.id == job_id, RenderJob.status == "complete", RenderJob.expires_at > utc_now()))
    if job is None: raise HTTPException(404, "Completed render not found or expired.")
    return job


@router.get("/api/render-jobs/{job_id}/download")
async def download_render(job_id: UUID, session: Session) -> FileResponse:
    job = await _complete_job(job_id, session)
    try: path = safe_render_path(job.output_key or "")
    except ValueError: raise HTTPException(404, "Rendered file is unavailable.") from None
    if not path.is_file(): raise HTTPException(404, "Rendered file is unavailable.")
    return FileResponse(path, media_type="video/mp4", filename=f"clipforge-{job.id}.mp4", headers={"Cache-Control": "no-store"})


@router.get("/api/render-jobs/{job_id}/captions")
async def download_captions(job_id: UUID, session: Session) -> FileResponse:
    job = await _complete_job(job_id, session)
    try: path = safe_render_path(job.caption_key or "")
    except ValueError: raise HTTPException(404, "Caption file is unavailable.") from None
    if not path.is_file(): raise HTTPException(404, "Caption file is unavailable.")
    return FileResponse(path, media_type="application/x-subrip", filename=f"clipforge-{job.id}.srt", headers={"Cache-Control": "no-store"})
