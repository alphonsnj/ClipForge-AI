# Milestone 7: Production readiness

## Current decision

ClipForge is still a local-development application. The owner has requested hosted-launch preparation and authorized conservative provisional defaults, but no service has been provisioned or exposed. The provider, actual region, monthly budget, domain, public privacy/terms policy, support contact, and availability target remain unselected. The [hosted launch plan](hosted-launch-plan.md) records provisional architecture and decisions; resolve the owner and legal gates before provisioning or public access.

## Current posture

| Area | Current implementation | Production gate |
| --- | --- | --- |
| Network exposure | Compose binds PostgreSQL and Redis to loopback; API and frontend run separately for local development. A production-oriented Uvicorn entry point reads explicit trusted proxy IPs/CIDRs and disables query-string-bearing access logs. | Choose and document ingress/TLS, firewall rules, and the exact proxy addresses before deployment; run the API with `python -m app.server`. |
| Database and queue | PostgreSQL and Redis are persistent Compose services with health checks. | Define encrypted backups, retention, restore objectives, monitoring, upgrades, and Redis recovery behavior. Test restore from a backup before launch. |
| Media storage | Local filesystem storage with upload, duration, aggregate storage, render size, and retention limits. | Choose storage region/provider, encryption and access policy, capacity alerts, backup scope, deletion guarantees, and lifecycle cleanup verification. |
| Accounts | Local owner/editor/reviewer roles, hashed passwords and session verifiers, CSRF checks, invite-only enrollment, and shared Redis failed-login throttling. Throttle and limiter-outage events are logged without address, email, or credential fields. | Add verified email, password recovery, MFA policy, deployment-specific proxy addresses, alert routing, audit events, TLS-only cookies, session operations, and independent security review. See [Milestone 6](milestone-6-accounts-and-collaboration.md). |
| Job processing | API and worker code process CPU-intensive jobs and call FFmpeg/faster-whisper. | Set measured concurrency, CPU/memory/disk quotas, job timeouts, queue limits, retry policy, cancellation behavior, and worker isolation based on representative workloads. |
| Observability | Health and dependency-readiness endpoints exist. Request completion and selected worker lifecycle events are JSON logged; requests receive a server-generated correlation ID. Application recovery paths log only exception classes, not exception messages or tracebacks. A local operations runbook is present. | Configure framework/process log redaction, job-level metrics, alert routing, log access/retention, and error ownership. Do not log credentials, session tokens, source URLs with secrets, or transcript/media content. |
| Privacy and operations | Source retention defaults to seven days; local deletion controls exist. | Publish data processing, rights, retention, deletion, privacy, terms, acceptable-use, and support information. Define incident response and user-request handling. |
| Hosted deployment scaffold | Provider-neutral single-node Compose stack, non-root API/worker and frontend images, isolated database/Redis network, loopback-only app ports, and one-time private owner bootstrap are prepared. | Select a provider/region/domain and HTTPS ingress; validate actual proxy peer IP, secret delivery, host firewall, encrypted storage/backups, image digests, and measured resource limits. |

Local PostgreSQL backup and restore-check commands are available in `scripts/db-backup.sh` and `scripts/db-restore-check.sh`. The archive is custom-format PostgreSQL data, includes account/project records, is not encrypted by these scripts, and excludes local media, model files, and render outputs. It is a local restore drill aid, not a production backup service.

Setting `APP_ENV=production` now fails startup unless the application has an explicit PostgreSQL URL without a placeholder/local-only password, an explicit Redis/Redis-TLS endpoint, secure cookies, HTTPS frontend/CORS origins, and valid trusted proxy addresses. The production `/api/auth/register` endpoint is disabled; create the first owner through `python -m app.bootstrap_owner` from a private terminal. These controls block common deployment mistakes; they do not certify the rest of a deployment.

GitHub CI defines frontend typecheck/build and npm audit, backend syntax compilation and pip-audit, hosted Compose configuration validation, and high/critical image scans for PostgreSQL, Redis, API/worker, and Next.js. All six checks passed on commit `9cdd4f85b13b5fd14ec31d45f90566c8bfed12fc`; the first frontend-image scan found vulnerable npm packages bundled in the Node runtime, which were removed because the runtime only needs Node. This is a point-in-time scan, not a deployment approval. Dependabot is configured for npm, pip, Compose images, and GitHub Actions. Keep scheduled CI enabled and review future findings.

The source-level security review and local runbook are recorded in `security-review-2026-11-04.md` and `local-operations-runbook.md`. The [internal launch policy brief](launch-policy-brief.md) captures verified local data flows and the choices a reviewer needs. These documents describe local controls and open review items; none is a production sign-off or a public policy.

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
- Start the API with `python -m app.server`; configure `TRUSTED_PROXY_IPS` to the exact proxy IPs/CIDRs when deployed behind a proxy. Never trust arbitrary forwarded headers.
- Use `compose.hosted.yaml` as a provisional single-host package. Complete the owner, domain, provider, budget, TLS, secret, backup, monitoring, and review decisions in `hosted-launch-plan.md` before exposing it.
- Run the local restore-check command against a fresh database archive and record the restored migration revision; define encrypted production backup and media restore separately.
- Measure resource consumption and job durations using permission-cleared samples.
- Resolve or document findings from the CI dependency and container-image scans.
- Add security review coverage for authentication, access control, CSRF, source delivery, and deletion paths.

Do not claim production readiness until all acceptance gates have evidence. The local implementation has not been deployed or penetration-tested.
