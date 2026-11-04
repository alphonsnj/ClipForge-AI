# Local validation log

## 3 November 2026

### Environment

- Docker Desktop on Apple Silicon (`aarch64` containers), PostgreSQL 16, Redis 7.
- Python 3.12 in the API/worker container; host Python was 3.9.6 and was not used for the runtime check.
- Frontend typecheck/build initially ran on Node 26.5.0; a later repeated check under Node 22.23.4 is recorded below.
- FFmpeg and FFprobe 7.1.5 in the temporary smoke container.
- faster-whisper 1.2.1, `small`, CPU `int8`; model revision `536b0662742c02347bc0e980a01041f333bce120`.
- PyAV 18.1.0, pinned after the first run proved PyAV 19.0.2 incompatible with faster-whisper 1.2.1.

### Checks completed

- Applied Alembic revisions `0001_projects_sources` through `0004_youtube_references`; database reported `0004_youtube_references (head)`.
- API readiness returned healthy PostgreSQL and Redis checks.
- YouTube link registration accepted and normalized `youtu.be`; unrelated hosts, explicit ports, and non-HTTP schemes were rejected. Watch, short, shorts, live, and embed URL forms passed normalization checks. The CORS preflight for `PUT` returned the allowed method list.
- A generated 14.15-second English speech clip was encoded into a 15-second MP4. FFprobe validation accepted it, the API returned the persisted source on upload, and source/project deletion completed. This also verified the upload response refresh fix.
- The transcription job completed with three timestamped segments and detected English at 0.985 probability. The synthetic reference had 34 normalized tokens; the output had two token edit errors (`timestamps` rendered as `time stamps`), giving a smoke-only WER of 5.9%. A warm run took 2.004 seconds for 14.15 seconds of media (RTF 0.142).
- The combined API/worker smoke container peak was 1.32 GiB. It is not an isolated worker measurement and is not a capacity guarantee.
- The pinned `small` model cache (479 MB on disk) was copied to ignored `data/models/` and successfully loaded again with the pinned revision.
- Candidate generation returned three chronological windows for the transcript; candidate selection, title/range editing, excerpt rebuilding, and deletion were persisted.
- Frontend typecheck and production build, Python syntax compilation, and `git diff --check` passed.

### Limits of this evidence

This was one generated English voice sample, not representative creator media. It does not validate accents, multilingual speech, music/noisy audio, one-hour workloads, the 500 MB upload ceiling, seven-day expiry timing, or peak worker-only memory. The candidate window smoke confirms code paths only; the evaluation rubric still needs target-language samples and independent human reviewers. Keep the YouTube link as a reference; the app did not fetch its metadata or media bytes.

## 4 November 2026

### Checks completed

- Frontend dependency audit (`npm audit`): no known vulnerabilities.
- Backend dependency audit (`pip-audit` against `backend/requirements.txt` in Python 3.12): no known vulnerabilities.
- Local PostgreSQL custom-format backup and restore check: archive restored into a disposable database at Alembic revision `0009_accounts_and_teams`; the disposable database was removed and the active database remained at that revision with zero registered users.
- Added GitHub CI jobs for frontend typecheck/build and npm audit, backend syntax compilation and pip-audit, and CRITICAL/HIGH scans of the Compose PostgreSQL and Redis images. Added weekly Dependabot updates for npm, pip, Docker Compose images, and Actions. The latest PR run passed all four jobs at commit `f73d9a3286b806708e50d5086639d71879ef644f`.
- Added server-generated request IDs and JSON completion events containing method, path, status, and duration only. Added JSON worker lifecycle events for selected render and transcription outcomes; the FFmpeg failure event no longer logs source filenames or stderr.
- A Python 3.12 runtime smoke imported the API, verified the `X-Request-ID` response header, checked that the query string is absent from the structured request log, and confirmed the bounded local login limiter returns 429 after its configured failure threshold.
- GitHub workflow and Dependabot YAML syntax was checked locally; remote PR runs then exercised the CI jobs, including a build and scan of the custom PostgreSQL image.
- The runtime configuration guard accepted development mode, rejected production mode with development defaults, and accepted explicit PostgreSQL/Redis endpoints with HTTPS frontend/CORS origins and secure cookies.
- Backend syntax compilation, Compose config validation, backup/restore script syntax, CI YAML parsing, and repository whitespace checks passed.
- Frontend TypeScript checking and optimized production build passed; full `npm audit` and `pip-audit` both reported no known vulnerabilities at the time of the run.
- Repeated frontend typecheck and optimized build under Node.js `22.23.4`, matching the documented Node 22 line.
- FFmpeg smoke rendered a generated 4-second color/audio source using the application render helpers for 9:16, 1:1, and 16:9. Output geometries matched 720×1280, 720×720, and 1280×720; each output duration was 3.5 seconds. Burn-in captions were exercised on portrait and SRT sidecars on all presets. This verifies technical output generation only; no visual review on representative footage was done.
- Trivy 0.76.1 scanned the local Compose image tags. Redis had no HIGH/CRITICAL findings; PostgreSQL had no Alpine OS-package HIGH/CRITICAL findings and 26 generic Go stdlib findings in the embedded `gosu` binary. The exact findings are temporarily suppressed only for PURL `pkg:golang/stdlib@v1.24.6`, with an expiry of 4 February 2027, based on gosu's upstream scanner guidance. This does not establish call-path absence independently and is not a fix; reevaluation is required. GitHub's scheduled/pull-request scan has not run.
- Additional call-path review of the stock PostgreSQL image found `gosu` 1.19 (Go 1.24.6), which calls vulnerable `github.com/moby/sys/user` v0.1.0 functions for advisory GO-2026-6686; `govulncheck` v1.1.4 binary mode reported the finding. This is not covered by the Trivy exception. The later custom Compose image replaces this binary with pinned upstream gosu 1.20 and the patched v0.4.1 dependency; both source and built binary pass govulncheck.
- Added a reproducible Compose PostgreSQL image build: it compiles upstream gosu 1.20 from pinned commit `29b939aa5bd4dc588af765b8248f6e39150d2565` with Go 1.24.6 and `moby/sys/user` v0.4.1, and runs govulncheck in source and final-binary modes during the image build. Both local ARM64 checks passed with no reachable vulnerabilities; the binary reported version 1.20 and passed `gosu nobody true`. An isolated PostgreSQL container reached readiness and answered a SQL query; Trivy reported no unsuppressed HIGH/CRITICAL findings. Its 26 Go stdlib findings remain narrowly suppressed as documented. GitHub CI built and scanned this custom PostgreSQL image successfully on 4 November 2026. The running development database was not restarted; Compose will use the patched image at the next build/recreate.
- Workflow checkout/setup actions are pinned to commit SHAs checked against their published version refs. Trivy runs from a digest-pinned scanner container, and the exact ignore file was exercised locally with 26 suppressed results.
- Final repository checks passed: Python syntax compilation, Compose configuration validation, Ruby YAML parsing for CI/Dependabot/Trivy ignore config, shell syntax for backup scripts, and `git diff --check`.
- Replaced the process-local login failure list with a Redis-backed fixed-window counter. An isolated Python 3.12 smoke used two Redis clients to verify shared 10-failure lockout, 15-minute TTL, per-peer keyed address hashes, distinct keys per address, and fail-closed 503 behavior when Redis is unavailable. Production configuration now rejects the development hash key.
- Exercised the actual FastAPI login route with two sequential application lifespans against the running PostgreSQL and Redis services: ten invalid sign-ins returned 401 and the second API instance returned 429 for the shared peer address. The temporary Redis key was deleted after the check.

### Remaining evidence gaps

- The latest remote PR CI run passed frontend build/audit, backend compile/audit, and both image scans. Keep these checks enabled and review future failures.
- The dependency/image audits describe the state on this date and should be repeated. The Trivy YAML ignore format is experimental. Trivy did not identify the stock image's `gosu`/`moby/sys/user` call-path finding; the custom Compose image now runs govulncheck against pinned source and final binary during build.
- Request/job events do not yet provide exception redaction, metrics, alert routing, or a deployment runbook.
- No user-provided representative media, human candidate ratings, browser/editor review, production target platform decisions, or external security assessment were available for this validation.
