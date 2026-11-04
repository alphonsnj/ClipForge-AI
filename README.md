# ClipForge AI

ClipForge AI is a local-first product for turning long-form video into reviewable short-form clips. Milestones 0–6 are implemented for local development. The current milestone is production-readiness work; the app is not deployed for shared or public use.

## Current milestone: production readiness

- Next.js landing page shell (`http://localhost:3000`)
- FastAPI liveness endpoint (`http://localhost:8000/health`)
- FastAPI dependency readiness endpoint (`http://localhost:8000/health/ready`)
- PostgreSQL 16 and Redis 7 with health checks and persistent local volumes; PostgreSQL is built locally with pinned gosu 1.20 source and a govulncheck gate
- Local project creation and private MP4/MOV upload with permission confirmation
- PostgreSQL migrations, file and duration limits, local storage quota, deletion, and seven-day source expiry
- Durable transcription jobs and timestamped transcript segments stored in PostgreSQL
- Separate Python worker for FFmpeg audio extraction and faster-whisper transcription
- Job status, retry, cancellation, language detection, and transcript inspection in the workspace
- Transcript-aligned candidate windows with duration controls, factual boundary signals, creator edits, and select/reject review
- Durable creator-triggered render jobs with bounded private MP4/SRT storage, cancellation/retry, progress, preview, and downloads
- Autosaved timeline/title edits, transcript caption corrections, local output presets, crop mode, and focus controls
- Local account setup/sign-in, project ownership by team, owner/editor/reviewer roles, one-time invitations, password changes, and session/CSRF checks

YouTube URL references are stored with projects, but YouTube video bytes are not fetched or processed; transcription still requires an authorized local MP4/MOV upload. Candidate windows are chronological and have no quality score until a human-reviewed sample set and rubric are agreed. Milestones 4 and 5 implement local rendering and a creator editor; Milestone 6 adds local accounts, team ownership, and editor/reviewer roles. See the [rendering](docs/milestone-4-rendering.md), [creator editor](docs/milestone-5-creator-editor.md), and [accounts/collaboration](docs/milestone-6-accounts-and-collaboration.md) notes. These accounts are still a local-development implementation: email delivery/recovery, MFA, an external identity provider, and production security operations remain open. The landing page's review panel is illustrative. Keep the API, worker, and workspace on the local machine; do not expose this scaffold to a network or submit secrets.

## Prerequisites

Target setup: Apple Silicon Mac with 16 GB unified memory, Node.js 22, Python 3.12, Docker Desktop, and FFmpeg/ffprobe. The worker defaults to faster-whisper `small` on CPU with int8 compute and one worker process. The provided backend configuration pins the model revision and PyAV version. Model weights are downloaded into `data/models/` on the first transcription request, not during setup.

Install Node and Python with Homebrew if needed:

```sh
brew install node@22 python@3.12
brew install ffmpeg
brew install --cask docker
```

Open Docker Desktop and wait for it to start. From the project root:

```sh
cp .env.example .env
cp backend/.env.example backend/.env
cp frontend/.env.example frontend/.env.local
docker compose up -d --build
```

Start the frontend in one terminal:

```sh
cd frontend
npm install
npm run dev
```

Start the API in a second terminal:

```sh
cd backend
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
set -a; source .env; set +a
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Start the transcription worker in a third terminal, using the same backend virtual environment and configuration:

```sh
cd backend
source .venv/bin/activate
set -a; source .env; set +a
python -m app.worker
```

Open `http://localhost:3000`. Create a project at `http://localhost:3000/workspace`. Intake accepts MP4/MOV, up to 500 MB, one hour long, with a 2 GB total local-media quota and one concurrent upload per API process. Sources are kept in the private `data/media/` directory and deleted after seven days; users can also delete a source or project sooner. You must affirm ownership or permission for each upload. Start one transcription worker only; it serializes model work for the 16 GB local target. The first transcription downloads the model weights, so allow time and disk space for that step. Liveness is available at `http://localhost:8000/health`; readiness checks PostgreSQL and Redis at `http://localhost:8000/health/ready`.

The first visit creates the initial workspace owner account. Additional people join through manually copied, 24-hour invitation links. Owners manage invitations; editors can make projects; reviewers can read and preview without changing project state. Run `alembic upgrade head` before opening the workspace. See [Milestone 6 account and role details](docs/milestone-6-accounts-and-collaboration.md).

Transcription jobs and transcript rows are durable in PostgreSQL. Redis wakes the worker, while PostgreSQL polling recovers queued jobs if Redis loses a notification. Completed transcript segments include start/end millisecond timestamps and detected language. Candidate runs preserve source boundaries and transcript excerpts, and record creator selection, rejection, and edits. They do not assign quality scores or estimate virality. A synthetic English transcription smoke passed; representative-language benchmarks and human candidate evaluation remain open. Keep target-language evaluation recordings permission-cleared and outside Git. See [Milestone 2 notes](docs/milestone-2-transcription.md), [Milestone 3 notes](docs/milestone-3-candidates.md), and the [validation log](docs/validation-log.md).

Stop local services with `docker compose down`. This keeps the development volumes. To intentionally remove local database/cache data, use `docker compose down -v`.

## Configuration

`.env.example` is for Compose. `backend/.env.example` configures the API, worker, model, and source-retention limits. `frontend/.env.example` contains the API base URL. These examples contain local development values only; use separate secret-managed configuration for any shared or production environment. Relative `MEDIA_STORAGE_DIR` paths resolve from the repository root.

## Roadmap

See the [implementation roadmap](docs/implementation-roadmap.md) for the staged scope, exit criteria, dependencies, and open decisions. Local backup/restore tooling, CI dependency/image scans, basic request/job event logs, and local operations/security-review notes have been added. Representative-media transcription and candidate evaluation, editor/browser review, and independent security review remain open. Local account controls do not satisfy public deployment requirements.

For a local database backup, run `scripts/db-backup.sh`. To verify an archive can be restored, run `scripts/db-restore-check.sh /path/to/clipforge-YYYYMMDDTHHMMSSZ.dump`; the script restores into a uniquely named temporary database and removes it afterward. These PostgreSQL archives include account and project data, are not encrypted by this local tooling, and do not include media files. Keep them private and out of Git. Production backups need encryption, access controls, retention rules, media coverage, and a documented restore objective.

YouTube URL references accept watch, youtu.be, shorts, and live links and are stored without network fetching. YouTube metadata access does not grant rights to download or process video bytes. Link-based video processing remains deferred until an authorized byte-access method is defined; use a permitted local file upload meanwhile.
