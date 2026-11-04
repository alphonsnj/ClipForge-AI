"""Validated API input and output models."""

from __future__ import annotations

from datetime import datetime
import re
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    team_id: UUID | None = None


class AccountCredentials(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    password: str = Field(min_length=12, max_length=128)

    @model_validator(mode="after")
    def normalize_email(self) -> "AccountCredentials":
        value = self.email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        self.email = value
        return self


class InvitationAccept(AccountCredentials):
    token: str = Field(min_length=32, max_length=128)


class TeamInvitationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    email: str = Field(min_length=3, max_length=320)
    role: Literal["editor", "reviewer"]

    @model_validator(mode="after")
    def normalize_email(self) -> "TeamInvitationCreate":
        value = self.email.strip().lower()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", value):
            raise ValueError("Enter a valid email address.")
        self.email = value
        return self


class TeamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=120)


class PasswordChange(BaseModel):
    model_config = ConfigDict(extra="forbid")
    current_password: str = Field(min_length=1, max_length=128)
    new_password: str = Field(min_length=12, max_length=128)


class YouTubeReferenceCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    rights_confirmed: bool


class SourceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    original_filename: str
    media_format: str
    size_bytes: int
    duration_seconds: int
    rights_confirmed_at: datetime
    created_at: datetime
    expires_at: datetime


class ProjectRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    team_id: UUID
    name: str
    youtube_url: str | None = None
    youtube_video_id: str | None = None
    youtube_rights_confirmed_at: datetime | None = None
    created_at: datetime
    sources: list[SourceRead]
    transcription_jobs: list["TranscriptionJobRead"] = Field(default_factory=list)
    candidate_runs: list["CandidateRunRead"] = Field(default_factory=list)


class TranscriptionJobCreate(BaseModel):
    language: str | None = Field(default=None, min_length=2, max_length=3, pattern=r"^[a-z]{2,3}$")


class TranscriptionJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    source_id: UUID
    status: str
    stage: str
    progress_percent: int | None
    attempt_count: int
    max_attempts: int
    model_id: str
    model_revision: str | None
    requested_language: str | None
    detected_language: str | None
    language_probability: float | None
    failure_code: str | None
    failure_message: str | None
    retryable: bool
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None
    finished_at: datetime | None


class TranscriptSegmentRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ordinal: int
    start_ms: int
    end_ms: int
    text: str


class CandidateRunCreate(BaseModel):
    min_duration_seconds: int = Field(ge=1, le=3600)
    max_duration_seconds: int = Field(ge=1, le=3600)
    candidate_limit: int = Field(ge=1, le=100)

    @model_validator(mode="after")
    def validate_duration_range(self) -> "CandidateRunCreate":
        if self.min_duration_seconds > self.max_duration_seconds:
            raise ValueError("Minimum duration must not exceed maximum duration.")
        return self


class CandidateUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=120)
    summary: str | None = Field(default=None, max_length=2000)
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=1)
    status: Literal["selected", "rejected"] | None = None
    caption_edits: dict[str, str] | None = None
    editor_settings: EditorSettings | None = None

    @model_validator(mode="after")
    def validate_patch(self) -> "CandidateUpdate":
        if all(value is None for value in (self.title, self.summary, self.start_ms, self.end_ms, self.status, self.caption_edits, self.editor_settings)):
            raise ValueError("Provide candidate edits, editor settings, or a review status to update.")
        if (self.start_ms is None) != (self.end_ms is None):
            raise ValueError("Provide both start_ms and end_ms when editing a candidate range.")
        if self.start_ms is not None and self.end_ms is not None and self.end_ms <= self.start_ms:
            raise ValueError("Candidate end time must be after its start time.")
        return self


class EditorSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    aspect_ratio: Literal["9:16", "1:1", "16:9"] = "9:16"
    crop_mode: Literal["fit_blur", "fill_crop"] = "fit_blur"
    focus_x: float = Field(default=0.5, ge=0, le=1)
    focus_y: float = Field(default=0.5, ge=0, le=1)


class HighlightCandidateRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    ordinal: int
    start_ms: int
    end_ms: int
    title: str
    summary: str | None
    transcript_excerpt: str
    signals: list[str]
    status: str
    created_at: datetime
    updated_at: datetime
    render_jobs: list["RenderJobRead"] = Field(default_factory=list)
    caption_edits: dict[str, str] = Field(default_factory=dict)
    editor_settings: dict[str, object] = Field(default_factory=dict)


class RenderJobCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    caption_mode: Literal["burn_in", "sidecar"] = "burn_in"


class RenderJobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: UUID
    candidate_id: UUID
    status: str
    stage: str
    progress_percent: int | None
    aspect_ratio: str
    output_width: int
    output_height: int
    caption_mode: str
    crop_mode: str
    focus_x: float
    focus_y: float
    caption_edits: dict[str, str]
    start_ms: int
    end_ms: int
    output_size_bytes: int | None
    duration_ms: int | None
    failure_message: str | None
    retryable: bool
    created_at: datetime
    updated_at: datetime
    expires_at: datetime
    @computed_field
    @property
    def download_url(self) -> str | None:
        return f"/api/render-jobs/{self.id}/download" if self.status == "complete" else None

    @computed_field
    @property
    def captions_url(self) -> str | None:
        return f"/api/render-jobs/{self.id}/captions" if self.status == "complete" else None


class CandidateRunRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    transcription_job_id: UUID
    min_duration_seconds: int
    max_duration_seconds: int
    candidate_limit: int
    total_candidates: int
    sampled_evenly: bool
    created_at: datetime
    candidates: list[HighlightCandidateRead]


ProjectRead.model_rebuild()
HighlightCandidateRead.model_rebuild()
CandidateUpdate.model_rebuild()
