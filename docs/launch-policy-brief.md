# Launch policy brief (internal review draft)

This is a fact sheet for a future privacy/terms/acceptable-use review. It is not a public policy or legal advice. Do not publish it until the hosting model, jurisdiction, subprocessors, retention rules, and support contact are confirmed and qualified review is complete.

## Current local product facts

- ClipForge accepts direct MP4/MOV uploads after the user confirms ownership or permission. Current local limits are 500 MB per file, 60 minutes, 2 GB total source storage, and seven-day source retention. Users can delete a source or project sooner.
- The original, transcript, candidate edits, account/team records, job state, and render metadata are stored locally in the development setup. Media bytes and generated MP4/SRT files are stored in private local directories. A project/source deletion removes associated render files and database records; verify all deletion paths and backup implications before any shared-service promise.
- Transcription uses a locally running faster-whisper worker and FFmpeg. The first use downloads the pinned speech-model weights into the local model cache. The application does not send uploaded media to a hosted transcription API.
- PostgreSQL stores account email addresses, salted password hashes, session verifiers, workspace membership, invitations, project/source metadata, transcripts, candidate edits, and render/job records. Redis stores transient queue notifications and failed-login counters; rate-limit keys are keyed HMACs of peer addresses and expire after 15 minutes.
- Logs contain request IDs, route paths, method, status, duration, selected job lifecycle events, and exception class names on application recovery paths. Passwords, session tokens, source URLs, transcript text, and media bytes are not intentionally logged. Deployment log collection and retention are not configured here.
- YouTube URLs are stored only as references. No YouTube metadata or media bytes are fetched by this application.
- Current local database backups are unencrypted and omit media files, model weights, and Redis state. They are development restore-check archives, not a complete hosted-service backup.

## Decisions required before public policy drafting

- Hosting entity, contact address, processing/storage region, domain, and legal jurisdiction.
- Whether accounts remain invite-only; identity provider, email delivery, verification, account recovery, and support workflows.
- Retention for account records, transcripts, logs, job data, exports, and backups; deletion timing and backup expiration behavior.
- Production media/database providers, subprocessors, encryption, access logging, model-weight distribution, and incident contacts.
- Supported platforms, user rights/permissions responsibilities, acceptable-use boundaries, and response process for complaints or legal requests.
- Public support contact, policy effective date, and review/approval owner.

## Review checklist

1. Verify these implementation facts against the deployed configuration and data flows.
2. Complete the decisions above and document each provider and retention interval.
3. Have qualified counsel review privacy, terms, acceptable-use, copyright/rights language, and jurisdiction-specific obligations.
4. Test deletion across originals, intermediates, renders, database records, and backup expiration; record evidence and exceptions.
5. Publish the reviewed policies and support contact before accepting public users or media.
