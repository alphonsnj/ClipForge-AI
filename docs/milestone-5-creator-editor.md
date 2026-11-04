# Milestone 5: Creator editor

## Implemented workflow

- Preview the private source video in a composition-aware canvas with play/pause, a bounded playhead, and transcript-row seeking/highlighting.
- Edit clip title and in/out points using numeric controls and a compact timeline; changes autosave after a short pause and expose saved, saving, unsaved, or failed state.
- Correct each transcript segment used as a caption. Corrections are saved against transcript segment IDs, survive refresh, and are used by both the SRT sidecar and burned-in ASS captions. Empty correction text removes that caption row.
- Choose a local frame preset: 9:16 portrait 720 × 1280, 1:1 square 720 × 720, or 16:9 landscape 1280 × 720. Choose full-frame fit over blurred background or fill-and-crop; focus sliders adjust crop center. These are provisional local draft presets, not confirmed platform specifications.
- Render jobs snapshot the range, caption corrections, preset, crop mode, and focus coordinates when queued. Later editor changes do not alter an in-progress or retried render.

## API and persistence

Candidate edits are persisted through `PATCH /api/candidates/{candidate_id}`. Private source preview is served by `GET /api/projects/{project_id}/source/preview`; transcript segments remain in the existing transcript endpoint. Alembic migration `0007_creator_editor_state` adds candidate editor state and immutable render parameter snapshots.

## Acceptance still required

- Compare canvas preview composition to the rendered FFmpeg output across representative portrait, landscape, and square sources, including edge focus positions.
- Confirm seeking and playback behavior in supported browsers, including source range requests and long media. Verify editor controls with keyboard and mobile screen sizes.
- Human-review caption timing, line wrapping, legibility, and correction behavior across representative languages.
- Confirm platform output dimensions and safe-caption margins before replacing these local draft defaults.
