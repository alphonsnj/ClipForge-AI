"""Source intake records."""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    created_by_user_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    youtube_url: Mapped[str | None] = mapped_column(String(255), nullable=True)
    youtube_video_id: Mapped[str | None] = mapped_column(String(11), nullable=True)
    youtube_rights_confirmed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    sources: Mapped[list["Source"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    transcription_jobs: Mapped[list["TranscriptionJob"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )
    candidate_runs: Mapped[list["CandidateRun"]] = relationship(
        back_populates="project", cascade="all, delete-orphan", passive_deletes=True
    )


class User(Base):
    __tablename__ = "users"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    email: Mapped[str] = mapped_column(String(320), nullable=False, unique=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Team(Base):
    __tablename__ = "teams"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TeamMembership(Base):
    __tablename__ = "team_memberships"
    __table_args__ = (
        UniqueConstraint("team_id", "user_id", name="uq_team_memberships_team_user"),
        CheckConstraint("role IN ('owner', 'editor', 'reviewer')", name="ck_team_memberships_role"),
    )
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class AuthSession(Base):
    __tablename__ = "auth_sessions"
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    csrf_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class TeamInvitation(Base):
    __tablename__ = "team_invitations"
    __table_args__ = (CheckConstraint("role IN ('editor', 'reviewer')", name="ck_team_invitations_role"),)
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    team_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("teams.id", ondelete="CASCADE"), nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(320), nullable=False)
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    token_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    accepted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by_user_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Source(Base):
    __tablename__ = "sources"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    original_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(80), nullable=False, unique=True)
    media_format: Mapped[str] = mapped_column(String(8), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    rights_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    project: Mapped[Project] = relationship(back_populates="sources")


class TranscriptionJob(Base):
    __tablename__ = "transcription_jobs"
    __table_args__ = (
        Index(
            "uq_transcription_jobs_active_source",
            "source_id",
            unique=True,
            postgresql_where=text(
                "status IN ('queued', 'validating', 'extracting', 'transcribing', 'saving')"
            ),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    model_id: Mapped[str] = mapped_column(String(80), nullable=False)
    model_revision: Mapped[str | None] = mapped_column(String(120), nullable=True)
    requested_language: Mapped[str | None] = mapped_column(String(12), nullable=True)
    detected_language: Mapped[str | None] = mapped_column(String(12), nullable=True)
    language_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    project: Mapped[Project] = relationship(back_populates="transcription_jobs")
    segments: Mapped[list["TranscriptSegment"]] = relationship(
        back_populates="job", cascade="all, delete-orphan", passive_deletes=True,
        order_by="TranscriptSegment.ordinal",
    )
    candidate_runs: Mapped[list["CandidateRun"]] = relationship(
        back_populates="transcription_job", cascade="all, delete-orphan", passive_deletes=True
    )

    @property
    def retryable(self) -> bool:
        return (
            self.status == "failed"
            and self.retry_allowed
            and self.attempt_count < self.max_attempts
        )


class TranscriptSegment(Base):
    __tablename__ = "transcript_segments"
    __table_args__ = (
        UniqueConstraint("job_id", "ordinal", name="uq_transcript_segments_job_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_transcript_segments_ordinal_nonnegative"),
        CheckConstraint("start_ms >= 0", name="ck_transcript_segments_start_nonnegative"),
        CheckConstraint("end_ms > start_ms", name="ck_transcript_segments_bounds"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("transcription_jobs.id", ondelete="CASCADE"), nullable=False,
        index=True,
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    job: Mapped[TranscriptionJob] = relationship(back_populates="segments")


class CandidateRun(Base):
    __tablename__ = "candidate_runs"
    __table_args__ = (
        CheckConstraint("min_duration_seconds >= 1", name="ck_candidate_runs_min_duration_positive"),
        CheckConstraint("max_duration_seconds >= min_duration_seconds", name="ck_candidate_runs_duration_range"),
        CheckConstraint("max_duration_seconds <= 3600", name="ck_candidate_runs_max_duration"),
        CheckConstraint("candidate_limit BETWEEN 1 AND 100", name="ck_candidate_runs_candidate_limit"),
        CheckConstraint("total_candidates >= 0", name="ck_candidate_runs_total_nonnegative"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    transcription_job_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("transcription_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    min_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    max_duration_seconds: Mapped[int] = mapped_column(Integer, nullable=False)
    candidate_limit: Mapped[int] = mapped_column(Integer, nullable=False)
    total_candidates: Mapped[int] = mapped_column(Integer, nullable=False)
    sampled_evenly: Mapped[bool] = mapped_column(nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    project: Mapped[Project] = relationship(back_populates="candidate_runs")
    transcription_job: Mapped[TranscriptionJob] = relationship(back_populates="candidate_runs")
    candidates: Mapped[list["HighlightCandidate"]] = relationship(
        back_populates="run", cascade="all, delete-orphan", passive_deletes=True,
        order_by="HighlightCandidate.ordinal",
    )


class HighlightCandidate(Base):
    __tablename__ = "highlight_candidates"
    __table_args__ = (
        UniqueConstraint("run_id", "ordinal", name="uq_highlight_candidates_run_ordinal"),
        CheckConstraint("ordinal >= 0", name="ck_highlight_candidates_ordinal_nonnegative"),
        CheckConstraint("start_ms >= 0", name="ck_highlight_candidates_start_nonnegative"),
        CheckConstraint("end_ms > start_ms", name="ck_highlight_candidates_bounds"),
        CheckConstraint(
            "status IN ('suggested', 'selected', 'edited', 'rejected')",
            name="ck_highlight_candidates_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("candidate_runs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, nullable=False)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    title: Mapped[str] = mapped_column(String(120), nullable=False)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    transcript_excerpt: Mapped[str] = mapped_column(Text, nullable=False)
    signals: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list)
    caption_edits: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    editor_settings: Mapped[dict[str, object]] = mapped_column(JSON, nullable=False, default=dict)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="suggested", index=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )

    run: Mapped[CandidateRun] = relationship(back_populates="candidates")
    render_jobs: Mapped[list["RenderJob"]] = relationship(
        back_populates="candidate", cascade="all, delete-orphan", passive_deletes=True,
        order_by="RenderJob.created_at.desc()",
    )


class RenderJob(Base):
    """A durable local render request and the private output records it creates."""

    __tablename__ = "render_jobs"
    __table_args__ = (
        CheckConstraint(
            "status IN ('queued', 'validating', 'rendering', 'complete', 'failed', 'cancelled')",
            name="ck_render_jobs_status",
        ),
        CheckConstraint("caption_mode IN ('burn_in', 'sidecar')", name="ck_render_jobs_caption_mode"),
        CheckConstraint("attempt_count >= 0 AND max_attempts >= 1", name="ck_render_jobs_attempts"),
        CheckConstraint("reserved_size_bytes >= 0", name="ck_render_jobs_reservation_nonnegative"),
        CheckConstraint("start_ms >= 0 AND end_ms > start_ms", name="ck_render_jobs_bounds"),
        Index(
            "uq_render_jobs_active_candidate",
            "candidate_id",
            unique=True,
            postgresql_where=text("status IN ('queued', 'validating', 'rendering')"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    project_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("sources.id", ondelete="CASCADE"), nullable=False, index=True
    )
    candidate_id: Mapped[UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("highlight_candidates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="queued", index=True)
    stage: Mapped[str] = mapped_column(String(24), nullable=False, default="queued")
    progress_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    aspect_ratio: Mapped[str] = mapped_column(String(8), nullable=False, default="9:16")
    output_width: Mapped[int] = mapped_column(Integer, nullable=False, default=720)
    output_height: Mapped[int] = mapped_column(Integer, nullable=False, default=1280)
    caption_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="burn_in")
    crop_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="fit_blur")
    focus_x: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    focus_y: Mapped[float] = mapped_column(Float, nullable=False, default=0.5)
    caption_edits: Mapped[dict[str, str]] = mapped_column(JSON, nullable=False, default=dict)
    start_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    end_ms: Mapped[int] = mapped_column(Integer, nullable=False)
    reserved_size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    output_key: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    caption_key: Mapped[str | None] = mapped_column(String(80), nullable=True, unique=True)
    output_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    attempt_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    retry_allowed: Mapped[bool] = mapped_column(nullable=False, default=False)
    lease_token: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    failure_code: Mapped[str | None] = mapped_column(String(48), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now()
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    candidate: Mapped[HighlightCandidate] = relationship(back_populates="render_jobs")

    @property
    def retryable(self) -> bool:
        return self.status == "failed" and self.retry_allowed and self.attempt_count < self.max_attempts
