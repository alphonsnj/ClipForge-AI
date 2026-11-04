"""Private, bounded storage and FFmpeg helpers for local portrait drafts."""

import json
import math
import os
import re
import shutil
import subprocess
from pathlib import Path
from uuid import UUID

from fastapi import HTTPException

from .intake import ROOT
from .models import TranscriptSegment

OUTPUT_DIR = Path(os.getenv("RENDER_STORAGE_DIR", "data/outputs"))
if not OUTPUT_DIR.is_absolute():
    OUTPUT_DIR = (ROOT / OUTPUT_DIR).resolve()
MAX_RENDER_STORAGE_BYTES = int(os.getenv("MAX_RENDER_STORAGE_BYTES", str(2 * 1024 * 1024 * 1024)))
MAX_RENDER_FILE_BYTES = int(os.getenv("MAX_RENDER_FILE_BYTES", str(500 * 1024 * 1024)))
MAX_RENDER_DURATION_SECONDS = int(os.getenv("MAX_RENDER_DURATION_SECONDS", "180"))
RENDER_TIMEOUT_SECONDS = int(os.getenv("RENDER_TIMEOUT_SECONDS", "900"))
FFMPEG_BINARY = os.getenv("FFMPEG_BINARY", "ffmpeg")
FFPROBE_BINARY = os.getenv("FFPROBE_BINARY", "ffprobe")
FRAME_WIDTH = 720
FRAME_HEIGHT = 1280
FRAME_RATE = 30
MAX_CAPTION_BYTES = 2 * 1024 * 1024
PRESET_DIMENSIONS = {"9:16": (720, 1280), "1:1": (720, 720), "16:9": (1280, 720)}


def preset_dimensions(aspect_ratio: str) -> tuple[int, int]:
    try:
        return PRESET_DIMENSIONS[aspect_ratio]
    except KeyError:
        raise RenderFailure("invalid_preset", "Choose a supported local draft aspect ratio.") from None

if min(
    MAX_RENDER_STORAGE_BYTES,
    MAX_RENDER_FILE_BYTES,
    MAX_RENDER_DURATION_SECONDS,
    RENDER_TIMEOUT_SECONDS,
) <= 0:
    raise ValueError("Render storage, file, duration, and timeout limits must be positive.")


class RenderFailure(Exception):
    def __init__(self, code: str, message: str, retryable: bool = False) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.retryable = retryable


def ensure_output_dir() -> None:
    OUTPUT_DIR.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(OUTPUT_DIR, 0o700)


def safe_render_path(key: str) -> Path:
    if not re.fullmatch(r"[0-9a-f-]{36}\.(mp4|srt)", key):
        raise ValueError("Invalid render storage key")
    root = OUTPUT_DIR.resolve()
    candidate = (root / key).resolve()
    if candidate.parent != root:
        raise ValueError("Render key escapes output directory")
    return candidate


def unlink_render_key(key: str | None) -> None:
    if key:
        safe_render_path(key).unlink(missing_ok=True)


def prepare_render_directory(job_id: UUID) -> Path:
    ensure_output_dir()
    processing = OUTPUT_DIR / ".processing"
    processing.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(processing, 0o700)
    work_dir = processing / str(job_id)
    work_dir.mkdir(mode=0o700, exist_ok=True)
    os.chmod(work_dir, 0o700)
    return work_dir


def clean_render_directory(job_id: UUID) -> None:
    work_dir = OUTPUT_DIR / ".processing" / str(job_id)
    try:
        shutil.rmtree(work_dir)
    except FileNotFoundError:
        pass


def _srt_timestamp(milliseconds: int) -> str:
    hours, remainder = divmod(max(0, milliseconds), 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    seconds, fraction = divmod(remainder, 1_000)
    return f"{hours:02}:{minutes:02}:{seconds:02},{fraction:03}"


def _ass_timestamp(milliseconds: int) -> str:
    centiseconds = max(0, milliseconds) // 10
    hours, remainder = divmod(centiseconds, 360_000)
    minutes, remainder = divmod(remainder, 6_000)
    seconds, centiseconds = divmod(remainder, 100)
    return f"{hours}:{minutes:02}:{seconds:02}.{centiseconds:02}"


def caption_rows(
    segments: list[TranscriptSegment], start_ms: int, end_ms: int,
    overrides: dict[str, str] | None = None,
) -> list[tuple[int, int, str]]:
    rows: list[tuple[int, int, str]] = []
    for segment in segments:
        start = max(start_ms, segment.start_ms)
        end = min(end_ms, segment.end_ms)
        text = (overrides or {}).get(str(segment.id), segment.text).strip()
        if end > start and text:
            rows.append((start - start_ms, end - start_ms, text))
    return rows


def write_srt(rows: list[tuple[int, int, str]], path: Path) -> None:
    blocks = [
        f"{index}\n{_srt_timestamp(start)} --> {_srt_timestamp(end)}\n{text.replace(chr(13), '').strip()}"
        for index, (start, end, text) in enumerate(rows, 1)
    ]
    path.write_text("\n\n".join(blocks) + ("\n" if blocks else ""), encoding="utf-8")
    if path.stat().st_size > MAX_CAPTION_BYTES:
        path.unlink(missing_ok=True)
        raise RenderFailure("captions_too_large", "The caption sidecar exceeded the local size limit.")
    os.chmod(path, 0o600)


def _ass_escape(text: str) -> str:
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}").replace("\n", "\\N")


def write_ass(rows: list[tuple[int, int, str]], path: Path, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT) -> None:
    font_size = round(height / 32)
    side_margin = round(width * 0.072)
    bottom_margin = round(height * 0.133)
    header = """[Script Info]
ScriptType: v4.00+
WrapStyle: 2
ScaledBorderAndShadow: yes
PlayResX: {width}
PlayResY: {height}

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,Arial,{font_size},&H00FFFFFF,&H000000FF,&H00101010,&H99000000,1,0,0,0,100,100,0,0,3,0,0,2,{side_margin},{side_margin},{bottom_margin},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    events = [
        f"Dialogue: 0,{_ass_timestamp(start)},{_ass_timestamp(end)},Default,,0,0,0,,{_ass_escape(text)}"
        for start, end, text in rows
    ]
    header = header.format(width=width, height=height, font_size=font_size, side_margin=side_margin, bottom_margin=bottom_margin)
    path.write_text(header + "\n".join(events) + ("\n" if events else ""), encoding="utf-8-sig")
    os.chmod(path, 0o600)


def build_ffmpeg_command(
    source_path: Path,
    output_path: Path,
    *,
    start_ms: int,
    end_ms: int,
    caption_mode: str,
    width: int = FRAME_WIDTH,
    height: int = FRAME_HEIGHT,
    crop_mode: str = "fit_blur",
    focus_x: float = 0.5,
    focus_y: float = 0.5,
) -> list[str]:
    start_seconds = start_ms / 1000
    duration_seconds = (end_ms - start_ms) / 1000
    if crop_mode == "fill_crop":
        video_filter = (
            f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,"
            f"crop={width}:{height}:x='(iw-ow)*{focus_x:.4f}':y='(ih-oh)*{focus_y:.4f}',setsar=1,fps=30"
        )
    else:
        video_filter = (
        "[0:v]split=2[background][foreground];"
        f"[background]scale={width}:{height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height},boxblur=20:10[blurred];"
        f"[foreground]scale={width}:{height}:force_original_aspect_ratio=decrease[fit];"
        "[blurred][fit]overlay=(W-w)/2:(H-h)/2,setsar=1,fps=30"
        )
    if caption_mode == "burn_in":
        video_filter += ",subtitles=captions.ass"
    video_filter += ",format=yuv420p[v]"
    return [
        FFMPEG_BINARY,
        "-hide_banner",
        "-nostdin",
        "-y",
        "-v", "error",
        "-progress", "pipe:1",
        "-stats_period", "1",
        "-filter_complex_threads", "2",
        "-ss", f"{start_seconds:.3f}",
        "-i", str(source_path),
        "-t", f"{duration_seconds:.3f}",
        "-filter_complex", video_filter,
        "-map", "[v]",
        "-map", "0:a:0?",
        "-c:v", "libx264",
        "-preset", "veryfast",
        "-crf", "22",
        "-maxrate", "3M",
        "-bufsize", "6M",
        "-threads", "4",
        "-c:a", "aac",
        "-b:a", "128k",
        "-ar", "48000",
        "-movflags", "+faststart",
        "-f", "mp4",
        str(output_path),
    ]


def probe_render(path: Path, width: int = FRAME_WIDTH, height: int = FRAME_HEIGHT) -> tuple[int, int]:
    try:
        result = subprocess.run(
            [
                FFPROBE_BINARY,
                "-v", "error",
                "-show_entries", "format=duration,size:stream=codec_type,width,height",
                "-of", "json",
                str(path),
            ],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except FileNotFoundError as error:
        raise RenderFailure("ffprobe_unavailable", "Output verification needs FFprobe. Install FFmpeg and retry.") from error
    except subprocess.TimeoutExpired as error:
        raise RenderFailure("output_probe_timeout", "The rendered file could not be verified in time.", True) from error
    if result.returncode != 0:
        raise RenderFailure("invalid_render", "FFprobe could not read the rendered MP4.")
    try:
        metadata = json.loads(result.stdout)
        duration = float(metadata["format"]["duration"])
        size = int(metadata["format"]["size"])
        video = next(stream for stream in metadata.get("streams", []) if stream.get("codec_type") == "video")
    except (KeyError, ValueError, TypeError, StopIteration, json.JSONDecodeError) as error:
        raise RenderFailure("invalid_render", "The rendered MP4 is missing valid video metadata.") from error
    if (
        not math.isfinite(duration)
        or duration <= 0
        or video.get("width") != width
        or video.get("height") != height
    ):
        raise RenderFailure("invalid_render", "The rendered file did not match the portrait draft preset.")
    if size <= 0 or size > MAX_RENDER_FILE_BYTES:
        raise RenderFailure("render_size_limit", "The rendered file exceeded the local per-export size limit.")
    return round(duration * 1000), size
