# Milestone 3: highlight candidates

**Status: candidate generation and review controls implemented; quality evaluation pending.** This milestone creates transcript-aligned candidate windows and records creator decisions. It does not rank quality, predict virality, or generate AI titles/summaries.

## Candidate-window behavior

1. A creator chooses a minimum and maximum duration for a completed transcript and a maximum number of windows to return (1–100).
2. The generator finds transcript segment boundaries at the source beginning or after segment text ending in common sentence punctuation.
3. For each start boundary, it selects the earliest sentence-ending boundary that meets the requested minimum while staying within the maximum.
4. Each suggestion retains the original millisecond boundaries and complete overlapping transcript-segment text. The code never estimates word timing inside a segment.
5. If more windows qualify than the chosen limit, it samples them evenly across the source timeline. Display order is chronological, never a quality rank.
6. Every suggestion carries factual signals about its boundaries and duration. The creator can edit its title and range, then select or reject it. Edits and review status are durable.

## Data and API

- `candidate_runs` records the completed transcript, requested duration range, result limit, total eligible windows, and whether even sampling occurred.
- `highlight_candidates` records source time bounds, an editable working title, transcript excerpt, factual signal list, and status (`suggested`, `selected`, `edited`, or `rejected`). Source/job deletion cascades through the run to candidates.
- `POST /api/transcription-jobs/{job_id}/candidate-runs` generates windows for a completed transcript.
- `GET /api/transcription-jobs/{job_id}/candidate-runs` retrieves saved runs for that transcript.
- `PATCH /api/candidates/{candidate_id}` updates the title, summary, time range, or review status. Range edits rebuild the excerpt from full overlapping transcript segments and disclose that segment text may extend past the exact in/out points.

## Quality-evaluation gate

The blueprint identifies completeness, clarity, relevance, emphasis/novelty, and audio quality as human-review criteria. It does not give weights, target languages, a representative sample set, or a scoring scale. The implementation therefore records only observable boundary/duration signals and creator selections/rejections. It does not invent a composite score.

Before adding automated ranking, agree on target languages and permission-cleared source recordings, prepare reference expectations, and have independent reviewers use the proposed [evaluation rubric](candidate-evaluation-rubric.md) and [blank review sheet](candidate-evaluation-template.csv) to assess coherence and editability. Keep sample media outside Git. Stage 2 transcription runtime/quality benchmarking is still a prerequisite for interpreting downstream review results.

## Known limits

- Sentence boundaries depend on punctuation at transcript segment ends. Some languages, ASR output, or informal speech may omit punctuation and produce few/no suggestions.
- A transcript segment can contain more than one sentence; candidate edges remain at segment boundaries, so the window may include adjacent words or sentences.
- Candidate windows overlap and may be repetitive. Even sampling spreads returned windows over the source but does not imply better quality.
- Candidate titles are time labels; summaries are not generated. The creator can edit the title and range.
- No audio-quality score, semantic relevance score, novelty score, or virality estimate is computed.

This remains a local-development workflow without authentication. Do not expose the API, worker, or workspace to a network.
