"""Candidate generation and creator review endpoints."""

from datetime import datetime, timezone
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from .candidate_service import extract_candidate_windows
from .db import get_session
from .auth import enforce_access
from .models import CandidateRun, HighlightCandidate, Source, TranscriptionJob, TranscriptSegment, utc_now
from .schemas import CandidateRunCreate, CandidateRunRead, CandidateUpdate, HighlightCandidateRead

router = APIRouter(tags=["highlight candidates"], dependencies=[Depends(enforce_access)])
Session = Annotated[AsyncSession, Depends(get_session)]


@router.post(
    "/api/transcription-jobs/{job_id}/candidate-runs",
    response_model=CandidateRunRead,
    status_code=status.HTTP_201_CREATED,
)
async def create_candidate_run(
    job_id: UUID,
    payload: CandidateRunCreate,
    session: Session,
) -> CandidateRun:
    job = await session.scalar(
        select(TranscriptionJob).where(TranscriptionJob.id == job_id)
    )
    if job is None:
        raise HTTPException(404, "Transcription job not found.")
    if job.status != "complete":
        raise HTTPException(409, "A completed transcript is required to find candidate moments.")

    source = await session.scalar(
        select(Source).where(
            Source.id == job.source_id,
            Source.project_id == job.project_id,
            Source.expires_at > datetime.now(timezone.utc),
        )
    )
    if source is None:
        raise HTTPException(409, "The source was deleted or expired.")
    segments_result = await session.scalars(
        select(TranscriptSegment)
        .where(TranscriptSegment.job_id == job.id)
        .order_by(TranscriptSegment.ordinal)
    )
    segments = list(segments_result.all())
    drafts, total_candidates = extract_candidate_windows(
        segments,
        source_duration_ms=source.duration_seconds * 1000,
        min_duration_seconds=payload.min_duration_seconds,
        max_duration_seconds=payload.max_duration_seconds,
        candidate_limit=payload.candidate_limit,
    )
    if not drafts:
        raise HTTPException(
            422,
            "No transcript-aligned complete-sentence windows fit that duration range. Try a wider range or review the transcript punctuation.",
        )

    run = CandidateRun(
        project_id=job.project_id,
        source_id=job.source_id,
        transcription_job_id=job.id,
        min_duration_seconds=payload.min_duration_seconds,
        max_duration_seconds=payload.max_duration_seconds,
        candidate_limit=payload.candidate_limit,
        total_candidates=total_candidates,
        sampled_evenly=total_candidates > len(drafts),
    )
    session.add(run)
    await session.flush()
    session.add_all(
        HighlightCandidate(
            run_id=run.id,
            ordinal=ordinal,
            start_ms=draft.start_ms,
            end_ms=draft.end_ms,
            title=draft.title,
            transcript_excerpt=draft.transcript_excerpt,
            signals=draft.signals,
        )
        for ordinal, draft in enumerate(drafts)
    )
    await session.commit()
    result = await session.scalar(
        select(CandidateRun)
        .options(selectinload(CandidateRun.candidates).selectinload(HighlightCandidate.render_jobs))
        .where(CandidateRun.id == run.id)
    )
    if result is None:
        raise HTTPException(500, "Candidates were created but could not be loaded.")
    return result


@router.get(
    "/api/transcription-jobs/{job_id}/candidate-runs",
    response_model=list[CandidateRunRead],
)
async def list_candidate_runs(job_id: UUID, session: Session) -> list[CandidateRun]:
    job_exists = await session.scalar(
        select(TranscriptionJob.id).where(TranscriptionJob.id == job_id)
    )
    if job_exists is None:
        raise HTTPException(404, "Transcription job not found.")
    result = await session.scalars(
        select(CandidateRun)
        .options(selectinload(CandidateRun.candidates).selectinload(HighlightCandidate.render_jobs))
        .where(CandidateRun.transcription_job_id == job_id)
        .order_by(CandidateRun.created_at.desc())
    )
    return list(result.unique().all())


@router.patch(
    "/api/candidates/{candidate_id}",
    response_model=HighlightCandidateRead,
)
async def update_candidate(
    candidate_id: UUID,
    payload: CandidateUpdate,
    session: Session,
) -> HighlightCandidate:
    candidate = await session.scalar(
        select(HighlightCandidate)
        .options(selectinload(HighlightCandidate.run), selectinload(HighlightCandidate.render_jobs))
        .where(HighlightCandidate.id == candidate_id)
    )
    if candidate is None:
        raise HTTPException(404, "Candidate not found.")
    run = candidate.run
    source = await session.scalar(
        select(Source).where(
            Source.id == run.source_id,
            Source.expires_at > datetime.now(timezone.utc),
        )
    )
    if source is None:
        raise HTTPException(404, "The candidate source no longer exists or has expired.")

    editing = payload.title is not None or payload.summary is not None or payload.start_ms is not None
    if payload.title is not None:
        title = payload.title.strip()
        if not title:
            raise HTTPException(422, "Candidate title cannot be blank.")
        candidate.title = title
    if payload.summary is not None:
        candidate.summary = payload.summary.strip() or None

    if payload.caption_edits is not None:
        if len(payload.caption_edits) > 500:
            raise HTTPException(422, "A clip can save corrections for at most 500 transcript segments.")
        parsed_edits: dict[UUID, str] = {}
        for segment_id, text in payload.caption_edits.items():
            try:
                parsed_id = UUID(segment_id)
            except ValueError:
                raise HTTPException(422, "Caption corrections must reference transcript segment IDs.") from None
            parsed_edits[parsed_id] = text
        segment_ids = set((await session.scalars(select(TranscriptSegment.id).where(
            TranscriptSegment.job_id == run.transcription_job_id,
            TranscriptSegment.id.in_(parsed_edits.keys()),
        ))).all()) if parsed_edits else set()
        normalized_edits: dict[str, str] = {}
        for parsed_id, text in parsed_edits.items():
            if parsed_id not in segment_ids:
                raise HTTPException(422, "A caption correction references a segment outside this transcript.")
            if len(text) > 500:
                raise HTTPException(422, "Caption corrections must be 500 characters or fewer.")
            normalized_edits[str(parsed_id)] = " ".join(text.split())
        candidate.caption_edits = normalized_edits
        editing = True

    if payload.editor_settings is not None:
        candidate.editor_settings = payload.editor_settings.model_dump()
        editing = True

    if payload.start_ms is not None and payload.end_ms is not None:
        duration_ms = source.duration_seconds * 1000
        if payload.end_ms > duration_ms:
            raise HTTPException(422, "Candidate end time exceeds the source duration.")
        overlapping = await session.scalars(
            select(TranscriptSegment)
            .where(
                TranscriptSegment.job_id == run.transcription_job_id,
                TranscriptSegment.start_ms < payload.end_ms,
                TranscriptSegment.end_ms > payload.start_ms,
            )
            .order_by(TranscriptSegment.ordinal)
        )
        segments = list(overlapping.all())
        if not segments:
            raise HTTPException(422, "The edited range does not overlap any transcript segments.")
        candidate.start_ms = payload.start_ms
        candidate.end_ms = payload.end_ms
        candidate.transcript_excerpt = " ".join(segment.text.strip() for segment in segments).strip()
        candidate.signals = [
            "Creator-edited time range",
            "Excerpt uses full transcript segments overlapping the edited range; segment text may extend beyond the exact in/out points",
        ]

    if payload.status is not None:
        candidate.status = payload.status
    elif editing:
        candidate.status = "edited"
    candidate.updated_at = utc_now()
    await session.commit()
    await session.refresh(candidate)
    return candidate
