# Milestone 4: Local clip rendering

## Scope

This milestone adds creator-triggered local draft renders for selected or edited candidate ranges. The development preset is 9:16 portrait MP4 at 720 × 1280 and 30 fps, H.264/AAC. To avoid making an unreviewed crop, the complete source frame is fitted over a blurred, full-canvas background. Captions are burned in by default; every render also produces a downloadable SRT sidecar. A sidecar-only mode is available through the API. The default has no watermark.

These are provisional local-development defaults, not an approved platform delivery specification. Confirm platform dimensions, caption safe margins, watermark policy, and visual quality on representative footage before presenting it as a production export preset.

## Workflow and safeguards

1. A creator selects or edits a transcript-aligned candidate and requests a render.
2. The API verifies the source is still present, the candidate status and range are valid, and local quota is available, then creates a durable render job.
3. The existing single worker claims render jobs after transcription work, renews a lease, and runs FFmpeg outside the API process. PostgreSQL remains the source of truth; queued notifications may be polled without Redis delivery.
4. FFprobe verifies duration, output geometry, and file size before the output is published. MP4 and SRT files use private local storage and are served only by job UUID download routes.
5. Source expiry, source deletion, and project deletion also remove associated completed exports. Render cancellation/retry and progress are reflected in the workspace.

Local defaults: 180 seconds maximum per clip, 500 MB maximum per output, 2 GB aggregate completed output quota, and a 15 minute render timeout. Set `RENDER_STORAGE_DIR`, `MAX_RENDER_STORAGE_BYTES`, `MAX_RENDER_FILE_BYTES`, `MAX_RENDER_DURATION_SECONDS`, and `RENDER_TIMEOUT_SECONDS` to revise them. FFmpeg with `libx264`, AAC, and subtitle filter support plus FFprobe must be installed in the worker runtime. The output folder is chmod 0700 and files 0600 on POSIX systems.

## Required runtime setup

Apply Alembic migrations through `0007_creator_editor_state`, install FFmpeg/FFprobe in the worker environment, then restart API and worker. The UI preview and download endpoints require the API to be reachable from the browser. The repository's Compose file currently provisions Postgres and Redis only, so this milestone does not claim a complete containerized application runtime.

## Acceptance still required

- Verify render geometry, in/out timing, audio preservation, caption readability/escaping, and playback against representative user-authorized portrait, landscape, and caption-heavy media.
- Confirm the FFmpeg build has `subtitles` and `libx264`, then smoke-check burn-in and sidecar-only outputs.
- Review generated captions and edit candidate range/captions before publication; renders are drafts and do not publish to platforms.
- Confirm privacy/access controls before exposing the local-only service beyond the machine.
