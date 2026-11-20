# Hosted launch plan (provisional)

## Decision record

The owner requested preparation for a hosted launch and authorized conservative provisional defaults. No provider account, domain, infrastructure, or public service has been created.

| Decision | Provisional starting point | Must be confirmed before provisioning or public launch |
| --- | --- | --- |
| Launch scope | Invite-only private beta, single deployment, one worker. | Target user count, availability expectations, abuse/support process. |
| Hosting shape | One Linux VM running the hosted Compose stack; private application network; host/provider reverse proxy terminates HTTPS. | Provider, account owner, region, firewall, DNS, certificate management, and operator access. |
| Region | Prefer the region nearest the first users; India (Mumbai) is a planning candidate only if the intended first users are primarily in India. | Actual user geography and jurisdiction/privacy review. |
| Domain and routing | One HTTPS hostname; reverse proxy sends `/api/*` to the API and all other paths to Next.js on the same origin. `clipforge.example.invalid` is a reserved placeholder only. | Owned domain, DNS, proxy implementation, and exact proxy peer IP/CIDR. |
| Storage | Private persistent block volume shared by API and worker for originals, renders, and model weights. Database and Redis volumes stay on private networks. | Volume encryption, capacity/alerts, snapshots, backup provider, retention, and tested restore objectives. |
| Resource starting caps | Compose defaults: API 1 CPU/1 GiB, worker 4 CPU/6 GiB, PostgreSQL 2 CPU/2 GiB, Redis 1 CPU/512 MiB, frontend 1 CPU/1 GiB. | Benchmark permission-cleared representative media, host size, disk throughput, and provider limits before accepting users. These caps are unvalidated starting values. |
| User access | Invite-only. Bootstrap the first owner through the private CLI; public first-account registration is disabled in production. | Identity provider, verified email, recovery, MFA, invitation revocation, and audit requirements. |
| Exports | Downloadable drafts; provisional 9:16, 720×1280, 30 fps. No social-platform publishing integration. | Supported platforms, output resolutions, caption rules, and any platform-specific acceptance requirements. |
| Spend | No billable resources until the owner selects a provider and monthly cap. | Monthly cap, alerts, payment owner, and usage policy. |
| Support and policies | No public support address or policies are published. | Support contact, legal entity, privacy jurisdiction, counsel review, effective dates, and incident contact. |

## Package in this repository

- `compose.hosted.yaml` describes the app, worker, PostgreSQL, and Redis. PostgreSQL and Redis are private; API and frontend ports bind to host loopback for a host-level reverse proxy. Application data uses a persistent shared volume.
- `backend/Dockerfile` builds the API/worker image with FFmpeg and a non-root runtime user. `frontend/Dockerfile` builds the Next.js standalone image.
- The frontend can use same-origin relative API requests. Configure the public reverse proxy to send `/api/*` to port 8000 and the remaining website paths to port 3000.
- Production account registration is disabled. After migrations, create the first owner from a private terminal with `docker compose ... exec api python -m app.bootstrap_owner` before making the proxy public.
- `deploy/hosted.env.example` contains reserved-domain and secret placeholders and must not be used as-is. Copy it to an ignored local env file, generate unique secrets, URL-encode the PostgreSQL password in `DATABASE_URL`, and set the actual proxy peer IP/CIDR. Production startup rejects reserved domains and placeholder database/rate-limit secrets.

After replacing every sentinel and completing provider/host choices, the intended command sequence is:

```sh
umask 077
cp deploy/hosted.env.example .env
chmod 600 .env
# Replace every sentinel using a secret manager or a root-readable host file.
export COMPOSE_FILE=compose.hosted.yaml
docker compose config > /dev/null
docker compose build
docker compose run --rm migrate
docker compose up -d postgres redis api frontend worker
docker compose exec api python -m app.bootstrap_owner
```

The host reverse proxy must bind public ports 80/443 with TLS, send `/api/*` to `127.0.0.1:8000`, send other paths to `127.0.0.1:3000`, and forward client IP/proto headers only from the configured trusted proxy. Keep that proxy disabled until bootstrap and readiness checks pass. The existing backup scripts honor `COMPOSE_FILE`, so with the root `.env` present they can target the hosted stack; validate backup and restore on staging before relying on them.

## Initial deployment sequence after decisions are confirmed

1. Select provider, region, budget cap, domain, legal jurisdiction, and operator/support contacts.
2. Create a hardened Linux host, private firewall rules, encrypted persistent storage, off-host encrypted backups, monitoring, and a TLS reverse proxy. Keep PostgreSQL, Redis, and application ports private; only HTTPS ingress should be public.
3. Set production environment values in a secret manager or a root-readable host file outside the repository. Pin all base images by digest after selecting the host architecture and reviewing the image scans.
4. Build and inspect images; verify the proxy routes same-origin `/api/*` correctly and records no credentials, invite tokens, or media/transcript data.
5. Run PostgreSQL and Redis, run `migrate`, then API and worker. Create the first owner through the private bootstrap command. Confirm no public route can create an owner account before exposing HTTPS.
6. Run readiness, invitation/roles, upload, transcription, render, source deletion, project deletion, expiry, backup, and full restore checks on permission-cleared staging data.
7. Complete representative-media and human review, security/privacy/legal assessment, alert and incident drills, capacity checks, and deletion/backup-expiry evidence.
8. Open the invite-only beta only after each gate has a named owner and evidence.

## Current launch blockers

Provider, actual region, domain, budget cap, support contact, user geography, representative media/reviewers, email/MFA lifecycle, managed backup and alert services, legal review, and independent security assessment remain unselected or unevidenced. The single-node filesystem design is a private-beta scaffold; it does not provide high availability, horizontal scaling, or complete disaster recovery.
