# Milestone 2: transcription

**Status: implementation complete; synthetic English smoke passed; representative-media benchmark pending.** The code defaults to faster-whisper `small`, CPU int8 inference, and a single local worker. A generated 14.15-second synthetic English clip completed end to end after pinning PyAV to `18.1.0`; see [validation log](validation-log.md). This single synthetic sample does not accept transcription quality or resource use for intended users/languages.

## Implemented workflow

1. The workspace requests a transcription job for a project with a current source.
2. PostgreSQL records the job before Redis is notified. The worker polls PostgreSQL as a recovery path, so Redis notifications are not the durable queue.
3. A PostgreSQL advisory lock prevents two local transcription workers from running at the same time. Each claimed job also has a renewable lease, so abandoned work can be reclaimed after a worker crash.
4. The worker resolves the source path under the private media root, uses FFmpeg to extract mono 16 kHz PCM audio into a private temporary directory, and loads faster-whisper only when the first job runs.
5. The worker fully consumes timestamped model segments, validates the resulting ranges, and stores them in one transaction. The job only becomes complete when the segment rows commit.
6. The workspace polls active jobs, presents the current stage and detected language, and lets the user inspect timestamped transcript text.
7. Retryable failures can be retried up to three attempts. Source deletion or expiry cascades to job and transcript records. Temporary audio is removed in a `finally` block.

## Local controls

- Model: `WHISPER_MODEL_ID=small`; the local example pins `WHISPER_MODEL_REVISION=536b0662742c02347bc0e980a01041f333bce120` for reproducible weights.
- Device and compute: `WHISPER_DEVICE=cpu`, `WHISPER_COMPUTE_TYPE=int8`, four CPU threads, beam size five.
- Model cache: `MODEL_CACHE_DIR=../data/models`, outside the web root and ignored by Git.
- PyAV is pinned to `18.1.0`. PyAV 19 removed an argument that faster-whisper 1.2.1 still passes, causing transcription to fail at audio decode; the smoke run caught and fixed this dependency mismatch.
- One worker process at a time; a PostgreSQL advisory lock enforces the single-worker limit.
- FFmpeg extraction timeout defaults to 900 seconds. Source duration remains capped at the Milestone 1 one-hour limit.
- Progress reports stage and heartbeat timestamps; transcription percentage is omitted because the model does not provide reliable determinate progress in this integration.

## API surface

- `POST /api/projects/{project_id}/transcription-jobs` queues a job; optional `language` accepts a short language code, with detection as the default.
- `GET /api/transcription-jobs/{job_id}` returns status, stage, attempts, timestamps, detected language, and safe failure guidance.
- `GET /api/transcription-jobs/{job_id}/transcript` returns ordered millisecond-bounded segments after completion.
- `POST /api/transcription-jobs/{job_id}/retry` retries a classified retryable failure.
- `POST /api/transcription-jobs/{job_id}/cancel` cancels queued or active work. An FFmpeg or model operation already underway is allowed to finish its current command/call; the result is discarded.

## Benchmark gate

Use at least three permission-cleared recordings representative of intended languages and audio conditions. Keep source files and reference transcripts outside Git. For each run, record model/revision, compute type, duration, wall time, peak process memory, real-time factor, detected language, and human-reviewed omissions/substitutions/name errors/timestamp usability. Compare `small` with `tiny` on identical samples. Use word error rate when an appropriate reference transcript exists; otherwise retain a reviewer rubric. Do not infer local performance from upstream benchmarks on unrelated hardware.

Accept the default only after the longest supported sample completes without exhausting memory and a reviewer considers the transcript timestamps usable and the text suitable for human correction. If it does not, select a smaller model or lower the local source/job limit and document the change. The synthetic smoke run is a technical path check, not a substitute for this acceptance set.

## Recovery behavior

- API commit succeeds while Redis is unavailable: the job remains in PostgreSQL and worker polling discovers it.
- Worker exits during a job: its lease expires; another worker process can reclaim the row on restart, subject to the three-attempt cap.
- Duplicate queue notifications: only a worker holding the database row lock and lease can progress the job.
- Source disappears or expires: the job is failed or removed by the source cascade; no transcript is committed.
- No audio or no detected speech: a clear non-retryable failure is recorded.
- Retryable extraction or unexpected runtime failure: a safe message and failure code are stored; project/source state remains intact.
- Cancellation during extraction or inference: the job is marked cancelled immediately, while the active process is allowed to finish its current command/call; its result is not persisted.

This workflow uses the local account and workspace access controls. It has not been reviewed for shared or public deployment; keep the local API and worker bound to the machine.
