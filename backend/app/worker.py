"""Single-process-friendly, database-backed transcription worker."""

import asyncio
import logging
import os
from dataclasses import dataclass
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import UUID, uuid4

from redis.asyncio import Redis
from redis.exceptions import RedisError
from sqlalchemy import or_, select, text, update
from sqlalchemy.orm import selectinload

from .db import SessionFactory, engine
from .intake import STORAGE_DIR, safe_storage_path
from .models import CandidateRun, HighlightCandidate, RenderJob, Source, TranscriptionJob, TranscriptSegment, utc_now
from .observability import emit_event, emit_failure
from .configuration import validate_runtime_configuration

logger = logging.getLogger("clipforge.worker")
QUEUE_NAME = "clipforge:transcription-jobs"
ACTIVE_STATUSES = ("validating", "extracting", "transcribing", "saving")
LEASE_SECONDS = int(os.getenv("JOB_LEASE_SECONDS", "90"))
HEARTBEAT_SECONDS = max(5, min(LEASE_SECONDS // 3, 25))
FFMPEG_BINARY = os.getenv("FFMPEG_BINARY", "ffmpeg")
FFMPEG_TIMEOUT_SECONDS = int(os.getenv("FFMPEG_TIMEOUT_SECONDS", "900"))
WHISPER_MODEL_ID = os.getenv("WHISPER_MODEL_ID", "small")
WHISPER_MODEL_REVISION = os.getenv("WHISPER_MODEL_REVISION") or None
WHISPER_DEVICE = os.getenv("WHISPER_DEVICE", "cpu")
WHISPER_COMPUTE_TYPE = os.getenv("WHISPER_COMPUTE_TYPE", "int8")
WHISPER_BEAM_SIZE = int(os.getenv("WHISPER_BEAM_SIZE", "5"))
MODEL_CACHE_DIR = Path(os.getenv("MODEL_CACHE_DIR", str(STORAGE_DIR.parent / "models"))).resolve()

_model: Any | None = None
_model_key: tuple[str, str | None] | None = None


class JobFailure(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


class LeaseLost(Exception):
    """The job was cancelled, deleted, or reclaimed by another worker."""


@dataclass(frozen=True)
class ClaimedJob:
    id: UUID
    project_id: UUID
    source_id: UUID
    lease_token: UUID
    requested_language: str | None
    model_id: str
    model_revision: str | None
    attempt_count: int
    max_attempts: int


async def claim_next_job() -> ClaimedJob | None:
    now = utc_now()
    async with SessionFactory() as session:
        statement = (
            select(TranscriptionJob)
            .join(Source, Source.id == TranscriptionJob.source_id)
            .where(
                Source.expires_at > now,
                or_(
                    TranscriptionJob.status == "queued",
                    (
                        TranscriptionJob.status.in_(ACTIVE_STATUSES)
                        & (TranscriptionJob.lease_expires_at < now)
                    ),
                ),
            )
            .order_by(TranscriptionJob.created_at)
            .with_for_update(skip_locked=True)
            .limit(1)
        )
        job = await session.scalar(statement)
        if job is None:
            await session.rollback()
            return None

        if job.status != "queued" and job.attempt_count >= job.max_attempts:
            job.status = "failed"
            job.stage = "failed"
            job.failure_code = "worker_lost"
            job.failure_message = "The worker stopped repeatedly before completing this job. Check worker health, then start a new job."
            job.retry_allowed = False
            job.lease_token = None
            job.lease_expires_at = None
            job.finished_at = now
            await session.commit()
            return None

        token = uuid4()
        job.status = "validating"
        job.stage = "validating"
        job.progress_percent = None
        job.attempt_count += 1
        job.retry_allowed = False
        job.failure_code = None
        job.failure_message = None
        job.lease_token = token
        job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        job.started_at = job.started_at or now
        job.finished_at = None
        await session.commit()
        return ClaimedJob(
            id=job.id,
            project_id=job.project_id,
            source_id=job.source_id,
            lease_token=token,
            requested_language=job.requested_language,
            model_id=job.model_id,
            model_revision=job.model_revision,
            attempt_count=job.attempt_count,
            max_attempts=job.max_attempts,
        )


@dataclass(frozen=True)
class ClaimedRenderJob:
    id: UUID
    project_id: UUID
    source_id: UUID
    candidate_id: UUID
    lease_token: UUID
    attempt_count: int
    max_attempts: int


async def claim_next_render_job() -> ClaimedRenderJob | None:
    now = utc_now()
    async with SessionFactory() as session:
        job = await session.scalar(select(RenderJob).join(Source, Source.id == RenderJob.source_id).where(
            Source.expires_at > now, RenderJob.expires_at > now,
            or_(RenderJob.status == "queued", (RenderJob.status.in_(("validating", "rendering")) & (RenderJob.lease_expires_at < now))),
        ).order_by(RenderJob.created_at).with_for_update(skip_locked=True).limit(1))
        if job is None:
            await session.rollback(); return None
        if job.status != "queued" and job.attempt_count >= job.max_attempts:
            job.status = "failed"; job.stage = "failed"; job.failure_code = "worker_lost"
            job.failure_message = "The render worker stopped repeatedly. Retry after checking worker health."
            job.retry_allowed = False; job.lease_token = None; job.lease_expires_at = None; job.finished_at = now
            await session.commit(); return None
        token = uuid4(); job.status = "validating"; job.stage = "validating"
        job.attempt_count += 1; job.retry_allowed = False; job.failure_code = None; job.failure_message = None
        job.lease_token = token; job.lease_expires_at = now + timedelta(seconds=LEASE_SECONDS)
        job.started_at = job.started_at or now; job.finished_at = None
        await session.commit()
        return ClaimedRenderJob(job.id, job.project_id, job.source_id, job.candidate_id, token, job.attempt_count, job.max_attempts)


async def update_render_job(job: ClaimedRenderJob, *, status: str | None = None, stage: str | None = None,
                            progress: int | None = None, failure_code: str | None = None,
                            failure_message: str | None = None, retry_allowed: bool | None = None,
                            finished: bool = False, **extra: object) -> bool:
    values: dict[str, object] = {"updated_at": utc_now(), "lease_expires_at": None if finished else utc_now() + timedelta(seconds=LEASE_SECONDS)}
    if status is not None: values["status"] = status
    if stage is not None: values["stage"] = stage
    if progress is not None: values["progress_percent"] = progress
    if failure_code is not None: values["failure_code"] = failure_code
    if failure_message is not None: values["failure_message"] = failure_message
    if retry_allowed is not None: values["retry_allowed"] = retry_allowed
    values.update(extra)
    if finished: values.update(finished_at=utc_now(), lease_token=None)
    async with SessionFactory() as session:
        result = await session.execute(update(RenderJob).where(RenderJob.id == job.id, RenderJob.lease_token == job.lease_token,
            RenderJob.status.in_(("validating", "rendering"))).values(**values))
        await session.commit(); return result.rowcount == 1


async def process_render_job(job: ClaimedRenderJob) -> None:
    import shutil
    from .rendering import (MAX_RENDER_DURATION_SECONDS, OUTPUT_DIR, RenderFailure,
                            build_ffmpeg_command, caption_rows, clean_render_directory,
                            prepare_render_directory, probe_render, safe_render_path,
                            write_ass, write_srt)
    work_dir = prepare_render_directory(job.id)
    process: asyncio.subprocess.Process | None = None
    pulse_stop = asyncio.Event()
    async def pulse() -> None:
        while True:
            try: await asyncio.wait_for(pulse_stop.wait(), timeout=HEARTBEAT_SECONDS); return
            except TimeoutError:
                if not await update_render_job(job): return
    heartbeat_render = asyncio.create_task(pulse())
    final_video_key, final_caption_key = f"{uuid4()}.mp4", f"{uuid4()}.srt"
    try:
        async with SessionFactory() as session:
            source = await session.scalar(select(Source).where(Source.id == job.source_id, Source.project_id == job.project_id, Source.expires_at > utc_now()))
            candidate = await session.scalar(select(HighlightCandidate).options(selectinload(HighlightCandidate.run)).join(CandidateRun).where(HighlightCandidate.id == job.candidate_id, CandidateRun.source_id == job.source_id))
            if source is None or candidate is None: raise RenderFailure("source_unavailable", "The source or selected candidate is unavailable.")
            transcription_id = candidate.run.transcription_job_id
            segments = list((await session.scalars(select(TranscriptSegment).where(TranscriptSegment.job_id == transcription_id).order_by(TranscriptSegment.start_ms))).all())
            render_record = await session.get(RenderJob, job.id)
            if render_record is None: raise RenderFailure("render_unavailable", "The render request was removed.")
            start_ms, end_ms, caption_mode = render_record.start_ms, render_record.end_ms, render_record.caption_mode
            width, height = render_record.output_width, render_record.output_height
            crop_mode, focus_x, focus_y = render_record.crop_mode, render_record.focus_x, render_record.focus_y
            caption_edits = render_record.caption_edits or {}
            source_path = safe_storage_path(source.storage_key)
            expiry = source.expires_at
        if end_ms <= start_ms or end_ms - start_ms > MAX_RENDER_DURATION_SECONDS * 1000: raise RenderFailure("duration_limit", "Candidate duration exceeds the local rendering limit.")
        if not source_path.is_file(): raise RenderFailure("source_missing", "The local source file is missing.")
        if not await update_render_job(job, status="rendering", stage="rendering", progress=1): return
        rows = caption_rows(segments, start_ms, end_ms, caption_edits)
        srt_path, ass_path, output_path = work_dir / "captions.srt", work_dir / "captions.ass", work_dir / "render.mp4"
        write_srt(rows, srt_path); write_ass(rows, ass_path, width, height)
        command = build_ffmpeg_command(source_path, output_path, start_ms=start_ms, end_ms=end_ms,
                                       caption_mode=caption_mode, width=width, height=height,
                                       crop_mode=crop_mode, focus_x=focus_x, focus_y=focus_y)
        process = await asyncio.create_subprocess_exec(*command, cwd=work_dir, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        async def monitor() -> None:
            assert process and process.stdout
            while line := await process.stdout.readline():
                key, _, value = line.decode(errors="replace").strip().partition("=")
                if key == "out_time_ms":
                    percent = min(99, max(1, int(int(value) / max(1, (end_ms-start_ms)*10))))
                    if not await update_render_job(job, status="rendering", stage="rendering", progress=percent):
                        process.terminate(); return
        try:
            await asyncio.wait_for(asyncio.gather(process.wait(), monitor()), timeout=int(os.getenv("RENDER_TIMEOUT_SECONDS", "900")))
        except TimeoutError:
            process.kill(); await process.wait(); raise RenderFailure("render_timeout", "Rendering took too long. Retry the job.", True)
        if process.returncode != 0: raise RenderFailure("ffmpeg_failed", "FFmpeg could not render this candidate. Confirm FFmpeg includes H.264 and subtitle support.", True)
        duration_ms, size_bytes = await asyncio.to_thread(probe_render, output_path, width, height)
        ensure_render_quota = size_bytes <= int(os.getenv("MAX_RENDER_FILE_BYTES", str(500*1024*1024)))
        if not ensure_render_quota: raise RenderFailure("render_size_limit", "The rendered file exceeded the local per-export size limit.")
        from .rendering import ensure_output_dir
        ensure_output_dir(); video_dest = safe_render_path(final_video_key); caption_dest = safe_render_path(final_caption_key)
        os.chmod(output_path, 0o600); os.chmod(srt_path, 0o600)
        shutil.move(str(output_path), video_dest); shutil.copy2(srt_path, caption_dest); os.chmod(caption_dest, 0o600)
        async with SessionFactory() as session:
            result = await session.execute(update(RenderJob).where(RenderJob.id == job.id, RenderJob.lease_token == job.lease_token, RenderJob.status == "rendering", RenderJob.expires_at > utc_now()).values(
                status="complete", stage="complete", progress_percent=100, output_key=final_video_key, caption_key=final_caption_key,
                output_size_bytes=size_bytes, duration_ms=duration_ms, reserved_size_bytes=0, finished_at=utc_now(), updated_at=utc_now(), lease_token=None, lease_expires_at=None))
            await session.commit()
            if result.rowcount != 1: raise LeaseLost("Render lease was lost")
        emit_event(logger, "render.completed", job_id=str(job.id))
    except LeaseLost:
        safe_render_path(final_video_key).unlink(missing_ok=True); safe_render_path(final_caption_key).unlink(missing_ok=True)
    except Exception as error:
        from .rendering import RenderFailure
        retryable = error.retryable if isinstance(error, RenderFailure) else True
        code = error.code if isinstance(error, RenderFailure) else "render_error"
        message = error.message if isinstance(error, RenderFailure) else "Rendering failed unexpectedly. Retry the render."
        emit_event(logger, "render.failed", job_id=str(job.id))
        await update_render_job(job, status="failed", stage="failed", failure_code=code, failure_message=message,
                                retry_allowed=retryable, finished=True, reserved_size_bytes=0)
        safe_render_path(final_video_key).unlink(missing_ok=True); safe_render_path(final_caption_key).unlink(missing_ok=True)
    finally:
        if process and process.returncode is None:
            process.kill(); await process.wait()
        pulse_stop.set(); await heartbeat_render; clean_render_directory(job.id)


async def update_job(
    job: ClaimedJob,
    *,
    status: str | None = None,
    stage: str | None = None,
    progress_percent: int | None = None,
    detected_language: str | None = None,
    language_probability: float | None = None,
    failure_code: str | None = None,
    failure_message: str | None = None,
    retry_allowed: bool | None = None,
    finished: bool = False,
) -> bool:
    now = utc_now()
    values: dict[str, object] = {
        "updated_at": now,
        "lease_expires_at": None if finished else now + timedelta(seconds=LEASE_SECONDS),
    }
    if status is not None:
        values["status"] = status
    if stage is not None:
        values["stage"] = stage
    if progress_percent is not None:
        values["progress_percent"] = progress_percent
    if detected_language is not None:
        values["detected_language"] = detected_language
    if language_probability is not None:
        values["language_probability"] = language_probability
    if failure_code is not None:
        values["failure_code"] = failure_code
    if failure_message is not None:
        values["failure_message"] = failure_message
    if retry_allowed is not None:
        values["retry_allowed"] = retry_allowed
    if finished:
        values["finished_at"] = now
        values["lease_token"] = None

    async with SessionFactory() as session:
        result = await session.execute(
            update(TranscriptionJob)
            .where(
                TranscriptionJob.id == job.id,
                TranscriptionJob.lease_token == job.lease_token,
                TranscriptionJob.status.in_(ACTIVE_STATUSES),
            )
            .values(**values)
        )
        await session.commit()
        return result.rowcount == 1


async def heartbeat(job: ClaimedJob, stop: asyncio.Event) -> None:
    while not stop.is_set():
        try:
            await asyncio.wait_for(stop.wait(), timeout=HEARTBEAT_SECONDS)
            return
        except TimeoutError:
            if not await update_job(job):
                return


def load_model(model_id: str, model_revision: str | None) -> Any:
    global _model, _model_key
    model_key = (model_id, model_revision)
    if _model_key != model_key:
        from faster_whisper import WhisperModel

        _model = None
        MODEL_CACHE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
        os.chmod(MODEL_CACHE_DIR, 0o700)
        logger.info(
            "Loading speech model %s (revision=%s, device=%s, compute=%s)",
            model_id,
            model_revision or "default",
            WHISPER_DEVICE,
            WHISPER_COMPUTE_TYPE,
        )
        _model = WhisperModel(
            model_id,
            device=WHISPER_DEVICE,
            compute_type=WHISPER_COMPUTE_TYPE,
            download_root=str(MODEL_CACHE_DIR),
            revision=model_revision,
            cpu_threads=max(1, int(os.getenv("WHISPER_CPU_THREADS", "4"))),
        )
        _model_key = model_key
    return _model


def transcribe_audio(
    audio_path: Path,
    model_id: str,
    model_revision: str | None,
    requested_language: str | None,
    duration_seconds: int,
) -> tuple[str | None, float | None, list[tuple[int, int, str]]]:
    model = load_model(model_id, model_revision)
    segments, info = model.transcribe(
        str(audio_path),
        beam_size=WHISPER_BEAM_SIZE,
        language=requested_language,
        condition_on_previous_text=False,
        vad_filter=True,
    )
    duration_ms = duration_seconds * 1000
    rows: list[tuple[int, int, str]] = []
    for segment in segments:
        text = segment.text.strip()
        start_ms = max(0, round(float(segment.start) * 1000))
        end_ms = min(duration_ms, round(float(segment.end) * 1000))
        if text and end_ms > start_ms:
            rows.append((start_ms, end_ms, text))
    if not rows:
        raise JobFailure("no_speech", "No speech was detected in this source.")
    probability = float(info.language_probability) if info.language_probability is not None else None
    return info.language, probability, rows


async def extract_audio(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(target_path.parent, 0o700)
    command = [
        FFMPEG_BINARY,
        "-nostdin",
        "-hide_banner",
        "-v",
        "error",
        "-y",
        "-i",
        str(source_path),
        "-map",
        "0:a:0",
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-c:a",
        "pcm_s16le",
        "-f",
        "wav",
        str(target_path),
    ]
    try:
        process = await asyncio.create_subprocess_exec(
            *command,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as error:
        raise JobFailure("ffmpeg_unavailable", "Audio extraction is unavailable. Install FFmpeg.") from error
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), timeout=FFMPEG_TIMEOUT_SECONDS)
    except TimeoutError as error:
        process.kill()
        await process.wait()
        raise JobFailure("audio_timeout", "Audio extraction took too long. Retry the job.", True) from error
    if process.returncode != 0:
        message = (stderr or b"").decode("utf-8", errors="replace").strip().lower()
        if "does not contain any stream" in message or "matches no streams" in message:
            raise JobFailure("no_audio", "This video does not contain an audio track.")
        emit_event(logger, "transcription.audio_extraction_failed")
        raise JobFailure("audio_extraction_failed", "Audio could not be extracted from this video.")
    if not target_path.is_file() or target_path.stat().st_size <= 44:
        raise JobFailure("no_audio", "This video does not contain usable audio.")
    os.chmod(target_path, 0o600)


async def heartbeat_task(job: ClaimedJob, stop: asyncio.Event) -> None:
    try:
        await heartbeat(job, stop)
    except Exception as error:
        emit_failure(logger, "transcription.lease_renewal.failed", error)


async def process_job(job: ClaimedJob) -> None:
    audio_path = STORAGE_DIR / ".processing" / f"{job.id}.wav"
    stop_heartbeat = asyncio.Event()
    pulse = asyncio.create_task(heartbeat_task(job, stop_heartbeat))
    try:
        async with SessionFactory() as session:
            source = await session.scalar(
                select(Source).where(
                    Source.id == job.source_id,
                    Source.project_id == job.project_id,
                    Source.expires_at > utc_now(),
                )
            )
            if source is None:
                raise JobFailure("source_unavailable", "The source was deleted or has expired.")
            source_path = safe_storage_path(source.storage_key)
            duration_seconds = source.duration_seconds
            if not source_path.is_file():
                raise JobFailure("source_missing", "The local source file is missing.")

        if not await update_job(job, status="extracting", stage="extracting"):
            return
        await extract_audio(source_path, audio_path)

        if not await update_job(job, status="transcribing", stage="transcribing"):
            return
        detected_language, probability, rows = await asyncio.to_thread(
            transcribe_audio,
            audio_path,
            job.model_id,
            job.model_revision,
            job.requested_language,
            duration_seconds,
        )

        if not await update_job(
            job,
            status="saving",
            stage="saving",
            detected_language=detected_language,
            language_probability=probability,
        ):
            return

        async with SessionFactory() as session:
            async with session.begin():
                result = await session.execute(
                    update(TranscriptionJob)
                    .where(
                        TranscriptionJob.id == job.id,
                        TranscriptionJob.lease_token == job.lease_token,
                        TranscriptionJob.status == "saving",
                    )
                    .values(
                        status="complete",
                        stage="complete",
                        progress_percent=100,
                        finished_at=utc_now(),
                        updated_at=utc_now(),
                        lease_token=None,
                        lease_expires_at=None,
                    )
                )
                if result.rowcount != 1:
                    raise LeaseLost("Job is no longer owned by this worker")
                session.add_all(
                    TranscriptSegment(
                        job_id=job.id,
                        ordinal=ordinal,
                        start_ms=start_ms,
                        end_ms=end_ms,
                        text=text,
                    )
                    for ordinal, (start_ms, end_ms, text) in enumerate(rows)
                )
        emit_event(logger, "transcription.completed", job_id=str(job.id), segment_count=len(rows))
    except LeaseLost:
        emit_event(logger, "transcription.results_discarded", job_id=str(job.id))
    except JobFailure as error:
        await update_job(
            job,
            status="failed",
            stage="failed",
            failure_code=error.code,
            failure_message=error.message,
            retry_allowed=error.retryable,
            finished=True,
        )
        emit_event(logger, "transcription.failed", job_id=str(job.id), failure_code=error.code)
    except Exception as error:
        emit_failure(logger, "transcription.failed_unexpectedly", error)
        await update_job(
            job,
            status="failed",
            stage="failed",
            failure_code="processing_error",
            failure_message="Transcription failed unexpectedly. Retry the job.",
            retry_allowed=True,
            finished=True,
        )
    finally:
        stop_heartbeat.set()
        await pulse
        audio_path.unlink(missing_ok=True)


async def run_worker() -> None:
    async with engine.connect() as lock_connection:
        lock_acquired = await lock_connection.scalar(
            text("SELECT pg_try_advisory_lock(1128813132, 2)")
        )
        if not lock_acquired:
            logger.error("Another ClipForge transcription worker is already running")
            return
        redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
        redis = Redis.from_url(redis_url, socket_connect_timeout=2, decode_responses=True)
        emit_event(logger, "worker.started", model_load="on_first_job")
        try:
            while True:
                try:
                    job = await claim_next_job()
                    if job is not None:
                        try:
                            await process_job(job)
                        except Exception as error:
                            emit_failure(logger, "worker.job_recovered", error)
                        continue
                    render_job = await claim_next_render_job()
                    if render_job is not None:
                        try:
                            await process_render_job(render_job)
                        except Exception as error:
                            emit_failure(logger, "worker.render_recovered", error)
                        continue
                    try:
                        await redis.blpop(QUEUE_NAME, timeout=5)
                    except RedisError:
                        logger.warning("Redis is unavailable; polling PostgreSQL for queued jobs")
                        await asyncio.sleep(5)
                except asyncio.CancelledError:
                    raise
                except Exception as error:
                    emit_failure(logger, "worker.loop_transient_failure", error)
                    await asyncio.sleep(5)
        finally:
            await redis.aclose()
            await lock_connection.execute(text("SELECT pg_advisory_unlock(1128813132, 2)"))


def main() -> None:
    validate_runtime_configuration()
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO").upper(),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(run_worker())
    except KeyboardInterrupt:
        emit_event(logger, "worker.stopped")


if __name__ == "__main__":
    main()
