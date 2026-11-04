"""Private local media storage and bounded media probing."""

import asyncio
import json
import math
import os
import re
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, UploadFile

ROOT = Path(__file__).resolve().parents[2]
STORAGE_DIR = Path(os.getenv("MEDIA_STORAGE_DIR", "../data/media"))
if not STORAGE_DIR.is_absolute():
    STORAGE_DIR = (ROOT / STORAGE_DIR).resolve()
MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(500 * 1024 * 1024)))
MAX_MEDIA_STORAGE_BYTES = int(os.getenv("MAX_MEDIA_STORAGE_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_VIDEO_DURATION_SECONDS = int(os.getenv("MAX_VIDEO_DURATION_SECONDS", "3600"))
SOURCE_RETENTION_DAYS = int(os.getenv("SOURCE_RETENTION_DAYS", "7"))
FFPROBE_BINARY = os.getenv("FFPROBE_BINARY", "ffprobe")
UPLOAD_CHUNK_BYTES = 1024 * 1024
MULTIPART_OVERHEAD_BYTES = 1024 * 1024
UPLOAD_LOCK = asyncio.Semaphore(1)

if (
    MAX_UPLOAD_BYTES <= 0
    or MAX_MEDIA_STORAGE_BYTES <= 0
    or MAX_VIDEO_DURATION_SECONDS <= 0
    or SOURCE_RETENTION_DAYS < 1
):
    raise ValueError("Upload, storage, duration, and retention limits must be positive.")


@dataclass(frozen=True)
class ValidatedMedia:
    temp_path: Path
    final_path: Path
    storage_key: str
    media_format: str
    size_bytes: int
    duration_seconds: int


def request_body_limit() -> int:
    return MAX_UPLOAD_BYTES + MULTIPART_OVERHEAD_BYTES


def ensure_storage_dir() -> None:
    STORAGE_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(STORAGE_DIR, 0o700)


async def spool_and_validate(upload: UploadFile, remaining_storage_bytes: int) -> ValidatedMedia:
    filename = (upload.filename or "").replace("\\", "/").rsplit("/", 1)[-1].strip()
    suffix = Path(filename).suffix.lower()
    if suffix not in {".mp4", ".mov"}:
        raise HTTPException(415, "Upload an MP4 or MOV video file.")
    if remaining_storage_bytes <= 0:
        raise HTTPException(507, "Local media storage is full. Delete an existing source before uploading.")

    ensure_storage_dir()
    temp_dir = STORAGE_DIR / ".incoming"
    temp_dir.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(temp_dir, 0o700)
    file_descriptor, temp_name = tempfile.mkstemp(prefix="upload-", suffix=".part", dir=temp_dir)
    temp_path = Path(temp_name)
    size_bytes = 0

    try:
        with os.fdopen(file_descriptor, "wb") as destination:
            while chunk := await upload.read(UPLOAD_CHUNK_BYTES):
                size_bytes += len(chunk)
                if size_bytes > MAX_UPLOAD_BYTES:
                    limit_mb = MAX_UPLOAD_BYTES // (1024 * 1024)
                    raise HTTPException(413, f"This video exceeds the {limit_mb} MB upload limit.")
                if size_bytes > remaining_storage_bytes:
                    raise HTTPException(507, "This video exceeds the remaining local media storage quota.")
                destination.write(chunk)
        if size_bytes == 0:
            raise HTTPException(400, "The uploaded file is empty.")

        with temp_path.open("rb") as source_file:
            source_file.seek(4)
            if source_file.read(4) != b"ftyp":
                raise HTTPException(415, "The file content is not an MP4 or MOV video.")

        details = await asyncio.to_thread(_probe_media, temp_path)
        if details["duration"] > MAX_VIDEO_DURATION_SECONDS:
            limit_minutes = MAX_VIDEO_DURATION_SECONDS // 60
            raise HTTPException(413, f"This video is longer than the {limit_minutes} minute limit.")

        media_id = uuid4()
        storage_key = f"{media_id}{suffix}"
        final_path = STORAGE_DIR / storage_key
        return ValidatedMedia(
            temp_path=temp_path,
            final_path=final_path,
            storage_key=storage_key,
            media_format=suffix[1:],
            size_bytes=size_bytes,
            duration_seconds=details["duration"],
        )
    except Exception:
        temp_path.unlink(missing_ok=True)
        raise
    finally:
        await upload.close()


def _probe_media(path: Path) -> dict[str, int]:
    try:
        result = subprocess.run(
            [
                FFPROBE_BINARY,
                "-v", "error",
                "-protocol_whitelist", "file,pipe,crypto,data",
                "-show_entries", "format=format_name,duration:stream=codec_type",
                "-of", "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=15,
        )
    except FileNotFoundError as error:
        raise HTTPException(503, "Media validation is unavailable. Install FFmpeg and restart the API.") from error
    except subprocess.TimeoutExpired as error:
        raise HTTPException(422, "The video could not be inspected in time.") from error

    if result.returncode != 0:
        raise HTTPException(422, "The uploaded video could not be read.")
    try:
        metadata = json.loads(result.stdout)
        formats = set((metadata.get("format", {}).get("format_name") or "").split(","))
        duration = float(metadata.get("format", {}).get("duration", "nan"))
    except (ValueError, TypeError, json.JSONDecodeError) as error:
        raise HTTPException(422, "The uploaded video metadata is invalid.") from error

    if not formats.intersection({"mov", "mp4", "m4a", "3gp", "3g2", "mj2"}):
        raise HTTPException(415, "The file content is not an MP4 or MOV video.")
    if not any(stream.get("codec_type") == "video" for stream in metadata.get("streams", [])):
        raise HTTPException(415, "The uploaded file does not contain a video stream.")
    if not math.isfinite(duration) or duration <= 0:
        raise HTTPException(422, "The video duration could not be determined.")
    return {"duration": math.ceil(duration)}


def safe_storage_path(storage_key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f-]{36}\.(mp4|mov)", storage_key):
        raise ValueError("Invalid storage key")
    root = STORAGE_DIR.resolve()
    candidate = (root / storage_key).resolve()
    if candidate.parent != root:
        raise ValueError("Storage key escapes media directory")
    return candidate


def finalize_media(media: ValidatedMedia) -> None:
    os.chmod(media.temp_path, 0o600)
    os.replace(media.temp_path, media.final_path)


def unlink_media(storage_key: str) -> None:
    safe_storage_path(storage_key).unlink(missing_ok=True)
