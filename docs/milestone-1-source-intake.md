# Milestone 1: source intake design

**Status: implemented; local synthetic-media workflow smoke-checked.** On 3 November 2026, PostgreSQL migrations through `0004_youtube_references` were applied. A generated 15-second MP4 passed the real FFprobe intake path, was stored and returned in the upload response, and was deleted through the API. YouTube URL registration, validation, rights confirmation, CORS preflight, and removal were exercised. Production-limit boundary cases and seven-day expiry timing still need dedicated verification. These settings remain easy to revise and must be reviewed before any shared or public deployment.

## Proposed local-development defaults

- Accept direct video uploads and allow a YouTube URL to be saved as a project reference. YouTube URL registration does not retrieve metadata or video bytes. Keep YouTube media processing disabled until a permitted byte-access method is defined, and direct creators to an authorized upload path.
- YouTube's current API Services Developer Policies prohibit downloading, importing, backing up, caching, or storing audiovisual copies through API services without prior written approval. Do not infer permission from URL ownership confirmation or API metadata access; review the official [developer policies](https://developers.google.com/youtube/terms/developer-policies) before changing this boundary.
- Accept MP4 and MOV containers. Validate the actual media container and duration with `ffprobe`; do not trust a browser-provided MIME type or filename.
- Limit each source to 500 MB and 60 minutes. Enforce the byte limit while streaming and reject over-limit duration after probing.
- Limit all stored source media to 2 GB total and allow one upload at a time per API process.
- Store originals under a private local data directory outside the web root. Generate opaque server-side IDs and filenames; never use a submitted name as a path.
- Retain originals for at most 7 days by default, with an immediate delete action. A background cleanup pass should remove expired bytes and associated source metadata, and report recoverable cleanup failures.
- Require an affirmative confirmation that the creator owns the video or has permission to process it.

These settings are active for local development. They are not public-service defaults or a substitute for deployment-specific policy decisions.

## Implementation sequence after policy confirmation

1. Add PostgreSQL project/source records and a migration. Store only metadata and a private storage key, never video bytes in PostgreSQL.
2. Add project creation and source-upload API contracts. Keep requests bounded and stream bytes to a temporary file rather than buffering a full upload in memory.
3. Validate size, extension allowlist, file signature/container, duration, and probe timeout. Reject malformed media, unsupported codecs if required, empty files, and failed probes with actionable messages.
4. Atomically move accepted files from a temporary name to an opaque ID-based object path, then commit metadata. Remove partial files if validation or the database transaction fails.
5. Add a local workspace UI for project creation, upload progress, rights confirmation, validation errors, source status, retention date, and deletion.
6. Add deletion and expiry cleanup with idempotent file removal, explicit status, and no guessable or public media URL.
7. Update setup documentation and demonstrate the complete local path with a synthetic or permission-cleared sample.

## Data and access boundaries

- The upload endpoint accepts media files only. The separate YouTube-reference endpoint validates and stores a canonical link without making a network request; it must never invoke a downloader.
- Original media is private local state, excluded from Git, prompts, and static asset serving.
- Use generated project/source identifiers and resolve file paths only beneath the configured storage root.
- Until accounts are implemented, keep this workflow local-development-only. Do not expose it as a shared or public upload service.
- A source deletion request should stop future work for that source, remove its bytes, and remove or tombstone its metadata according to the confirmed retention behavior.

## Acceptance criteria

- A permission-cleared supported video within both configured limits creates a project/source record and is stored outside the web root.
- An unsupported, malformed, oversized, over-duration, or unprobeable file is rejected without leaving a partial source or project orphan.
- The server ignores path components in client filenames, ignores the client-supplied MIME type, and checks the file signature and probed container.
- The user can delete a source; repeating the operation is safe and leaves no downloadable media.
- Expired-source cleanup is repeatable, reports failures, and does not remove a newer file that reused a client-supplied name.
- A YouTube URL can be saved and removed as a project reference; it cannot trigger byte downloading or platform circumvention.
- Setup instructions explain local storage, accepted formats, limits, retention, rights confirmation, and deletion.
