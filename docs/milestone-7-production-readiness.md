# Milestone 7: Production readiness

## Current decision

ClipForge is still a local-development application. This milestone begins with a readiness assessment and a launch gate, not a public deployment. The repository does not yet define a hosting provider, storage region, operating budget, public privacy/terms policy, support contact, or availability target. Those choices affect architecture and must be recorded before provisioning or exposing a service.

## Current posture

| Area | Current implementation | Production gate |
| --- | --- | --- |
| Network exposure | Compose binds PostgreSQL and Redis to loopback; API and frontend run separately for local development. | Define private network boundaries, ingress/TLS, firewall rules, and trusted proxy behavior before deployment. |
| Database and queue | PostgreSQL and Redis are persistent Compose services with health checks. | Define encrypted backups, retention, restore objectives, monitoring, upgrades, and Redis recovery behavior. Test restore from a backup before launch. |
| Media storage | Local filesystem storage with upload, duration, aggregate storage, render size, and retention limits. | Choose storage region/provider, encryption and access policy, capacity alerts, backup scope, deletion guarantees, and lifecycle cleanup verification. |
| Accounts | Local owner/editor/reviewer roles, hashed passwords and session verifiers, CSRF checks, and invite-only enrollment. | Add verified email, password recovery, MFA policy, distributed throttling, audit events, TLS-only cookies, session operations, and independent security review. See [Milestone 6](milestone-6-accounts-and-collaboration.md). |
| Job processing | API and worker code process CPU-intensive jobs and call FFmpeg/faster-whisper. | Set measured concurrency, CPU/memory/disk quotas, job timeouts, queue limits, retry policy, cancellation behavior, and worker isolation based on representative workloads. |
| Observability | Health and dependency-readiness endpoints exist. Request completion and selected worker lifecycle events are JSON logged; requests receive a server-generated correlation ID. A local operations runbook is present. | Add centralized redaction for exception traces, job-level metrics, alerting, and error ownership. Do not log credentials, session tokens, source URLs with secrets, or transcript/media content. |
| Privacy and operations | Source retention defaults to seven days; local deletion controls exist. | Publish data processing, rights, retention, deletion, privacy, terms, acceptable-use, and support information. Define incident response and user-request handling. |

Local PostgreSQL backup and restore-check commands are available in `scripts/db-backup.sh` and `scripts/db-restore-check.sh`. The archive is custom-format PostgreSQL data, includes account/project records, is not encrypted by these scripts, and excludes local media, model files, and render outputs. It is a local restore drill aid, not a production backup service.

Setting `APP_ENV=production` now fails startup unless the application has an explicit PostgreSQL URL without the local-only password, an explicit Redis/Redis-TLS endpoint, secure cookies, and HTTPS frontend/CORS origins. This blocks common development defaults; it does not certify the rest of a deployment.

GitHub CI now defines frontend typecheck/build and npm audit, backend syntax compilation and pip-audit, and high/critical vulnerability scans of the PostgreSQL and Redis Compose images. Dependabot is configured for npm, pip, Compose images, and GitHub Actions. These jobs have not run on GitHub because the workflow changes have not been pushed.

The source-level security review and local runbook are recorded in `security-review-2026-11-04.md` and `local-operations-runbook.md`. They describe local controls and open review items; neither is a production sign-off.

## Acceptance gates

1. Record hosting, storage region, domain, ingress/TLS, privacy jurisdiction, budget, support contact, availability target, and launch scope.
2. Replace every development secret and local-only default with deployment-managed secrets; verify startup fails safely when required secrets are absent.
3. Demonstrate least-privilege network access for the API, worker, database, queue, and private media store.
4. Measure resource use and completion times on permission-cleared representative media; set and enforce upload, storage, queue, concurrency, CPU, memory, disk, and timeout limits.
5. Produce encrypted, access-controlled database and media backups; execute a restore drill and document recovery time and data-loss bounds.
6. Provide service and job observability, alert routing, log redaction, incident response, and routine upgrade procedures.
7. Complete authentication and authorization review, dependency/image scanning, privacy review, and deletion verification across originals, intermediates, transcripts, previews, exports, and backups.
8. Publish reviewed privacy, terms, acceptable-use, retention/deletion, and support policies before accepting public users or media.

## Safe work that can proceed before deployment choices

- Extend request/job events with centralized exception redaction, metrics, and alert routing.
- Run the local restore-check command against a fresh database archive and record the restored migration revision; define encrypted production backup and media restore separately.
- Measure resource consumption and job durations using permission-cleared samples.
- Resolve or document findings from the CI dependency and container-image scans.
- Add security review coverage for authentication, access control, CSRF, source delivery, and deletion paths.

Do not claim production readiness until all acceptance gates have evidence. The local implementation has not been deployed or penetration-tested.
