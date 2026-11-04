# Local operations runbook

This runbook applies to the single-machine development setup only. It is not a deployment runbook and does not establish production recovery targets.

For a deployment-oriented API process, use `python -m app.server` from `backend/`. Set `HOST`/`PORT` for the private application interface and `TRUSTED_PROXY_IPS` to the exact proxy IPs/CIDRs. It trusts loopback by default and disables Uvicorn access logs, whose default path can include query strings. Do not expose the development Compose services or assume this command alone makes the system production-ready.

## Start and check services

1. Start Docker Desktop.
2. From the repository root, run `docker compose up -d`.
3. Confirm PostgreSQL and Redis are healthy with `docker compose ps`.
4. In the backend environment, apply schema changes with `alembic upgrade head`.
5. Start the API, frontend, and one worker using the commands in the root README.
6. Check `http://localhost:8000/health` for API liveness and `http://localhost:8000/health/ready` for PostgreSQL and Redis readiness.
7. Correlate API requests by the `X-Request-ID` response header. API request completion and selected worker lifecycle events are JSON log lines. Request events omit query strings and bodies.

## Database backup and restore check

Create a private PostgreSQL archive with `scripts/db-backup.sh`. The destination defaults to the ignored `backups/` directory; an optional first argument selects another directory. The archive contains account, project, transcript, candidate, job, and export metadata held in PostgreSQL. It is not encrypted and contains sensitive user data.

Verify a local archive with `scripts/db-restore-check.sh /path/to/archive.dump`. The script creates a uniquely named temporary database, restores the archive, reports its Alembic revision, and drops that temporary database. It does not modify the configured application database. Keep the archive outside Git and remove it securely when no longer needed.

The local archive does not include source videos, generated renders, model weights, Redis data, environment files, or secrets. A production restore plan must choose encrypted storage, include required media, set retention and access rules, and prove recovery objectives with an end-to-end restore drill.

## Stop local services

- Stop database and queue containers while keeping data: `docker compose down`.
- Remove PostgreSQL and Redis development volumes only when you intend to erase all local database/cache state: `docker compose down -v`.
- Stop API, frontend, and worker processes in their respective terminals. Keep local media, outputs, and model cache directories private.

## Recovery notes

- If Redis is unavailable, durable jobs remain in PostgreSQL; the worker polls PostgreSQL as a recovery path.
- If a worker stops during processing, its lease can expire and the job can be reclaimed subject to the retry limit.
- If a source file is deleted or expires, create a new source before retrying the affected transcription/render flow.
- For database loss, restore a PostgreSQL archive into the configured database, then verify the Alembic revision and application readiness. The current archive may not match later schema or deployment formats; validate compatibility before restoring over important data.

For any shared or public service, write provider-specific on-call, incident, backup, restore, upgrade, and deletion procedures before opening access.
