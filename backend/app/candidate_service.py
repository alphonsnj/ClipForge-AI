"""Extract bounded, transcript-aligned windows without making quality claims."""

import re
from bisect import bisect_left
from dataclasses import dataclass
from typing import TypeVar

from .models import TranscriptSegment

TERMINAL_PUNCTUATION = re.compile(r"[.!?…。！？।॥][\"'”’)}\]]*\s*$")
T = TypeVar("T")


@dataclass(frozen=True)
class CandidateDraft:
    start_ms: int
    end_ms: int
    title: str
    transcript_excerpt: str
    signals: list[str]


def ends_at_sentence_punctuation(text: str) -> bool:
    return bool(TERMINAL_PUNCTUATION.search(text.strip()))


def _format_time(milliseconds: int) -> str:
    total_seconds = milliseconds // 1000
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"


def _evenly_spaced(items: list[T], limit: int) -> list[T]:
    if len(items) <= limit:
        return items
    if limit == 1:
        return [items[len(items) // 2]]
    indices = [round(index * (len(items) - 1) / (limit - 1)) for index in range(limit)]
    return [items[index] for index in indices]


def extract_candidate_windows(
    segments: list[TranscriptSegment],
    *,
    source_duration_ms: int,
    min_duration_seconds: int,
    max_duration_seconds: int,
    candidate_limit: int,
) -> tuple[list[CandidateDraft], int]:
    """Return chronological candidates and the total eligible window count.

    A candidate starts at the transcript opening or just after a segment ending
    with sentence punctuation. It ends at the earliest such segment that meets
    the requested minimum duration without exceeding the maximum. This is an
    extractive coverage pass, not a relevance or engagement ranking.
    """
    ordered = sorted(segments, key=lambda segment: (segment.start_ms, segment.ordinal))
    if not ordered:
        return [], 0

    sentence_ends = sorted(
        (
            min(segment.end_ms, source_duration_ms),
            index,
        )
        for index, segment in enumerate(ordered)
        if ends_at_sentence_punctuation(segment.text)
    )
    end_times = [end_time for end_time, _ in sentence_ends]
    end_indices = [index for _, index in sentence_ends]
    sentence_starts = [0]
    sentence_starts.extend(
        index + 1
        for index, segment in enumerate(ordered[:-1])
        if ends_at_sentence_punctuation(segment.text)
    )

    min_ms = min_duration_seconds * 1000
    max_ms = max_duration_seconds * 1000
    eligible: list[CandidateDraft] = []
    for start_index in sentence_starts:
        start = ordered[start_index]
        if start.start_ms >= source_duration_ms:
            continue
        lower_bound = start.start_ms + min_ms
        upper_bound = min(start.start_ms + max_ms, source_duration_ms)
        position = bisect_left(end_times, lower_bound)
        while position < len(end_indices):
            end_index = end_indices[position]
            end_ms = end_times[position]
            if end_ms > upper_bound:
                break
            if end_index >= start_index and end_ms > start.start_ms:
                selected = ordered[start_index : end_index + 1]
                excerpt = " ".join(segment.text.strip() for segment in selected).strip()
                if excerpt:
                    duration = (end_ms - start.start_ms) / 1000
                    start_reason = (
                        "Starts at the transcript opening"
                        if start_index == 0
                        else "Starts after a transcript segment ending with sentence punctuation"
                    )
                    eligible.append(
                        CandidateDraft(
                            start_ms=start.start_ms,
                            end_ms=end_ms,
                            title=f"Moment at {_format_time(start.start_ms)}",
                            transcript_excerpt=excerpt,
                            signals=[
                                start_reason,
                                "Ends at a transcript segment ending with sentence punctuation",
                                f"Duration {duration:.1f}s is within the requested {min_duration_seconds}–{max_duration_seconds}s range",
                                "Boundaries use transcript segment timestamps; timing inside a segment is not inferred",
                            ],
                        )
                    )
                break
            position += 1

    return _evenly_spaced(eligible, candidate_limit), len(eligible)
