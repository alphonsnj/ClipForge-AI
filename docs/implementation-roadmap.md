# ClipForge AI implementation roadmap

This roadmap translates the product blueprint into deliverable stages. Milestones 0–6 are implemented for local development, including local source intake, YouTube references, transcription, candidate review, FFmpeg rendering, the creator editor, and local accounts with workspace roles. Synthetic source/transcription smoke checks passed; invitation/role/CSRF/password-rotation smoke checks also passed. The local backup restore drill passed. Frontend and backend dependency audits found no known vulnerabilities on 4 November 2026; local PostgreSQL/Redis image scans were also triaged on that date, with a temporary package-scoped exception for embedded `gosu` standard-library findings. A separate `govulncheck` review found the PostgreSQL image's `gosu` 1.19 bundles a reachable, moderate `moby/sys/user` advisory; require an image with the patched dependency before shared/public use. See `security-review-2026-11-04.md`. Node 22 frontend build/typecheck and synthetic render checks passed. Representative-media benchmarking, human candidate evaluation, browser-specific editor review, and the acceptance checks in `milestone-4-rendering.md` and `milestone-5-creator-editor.md` remain open. Milestone 6 is not production-ready: external identity, verified email/recovery, MFA, distributed rate limiting, and independent security review remain open. See `milestone-6-accounts-and-collaboration.md`.

## Product direction

ClipForge AI is a web product for creators and small content teams. It helps turn long recordings into short, reviewable social clips by transcribing speech, surfacing coherent moments, rendering editable drafts, and letting a creator approve exports. AI output remains a suggestion, and the creator controls edits and publication.

The first technical shape is a Next.js 15 / React 19 web client, FastAPI on Python 3.12, PostgreSQL for durable application and job state, Redis for queue coordination, and a Python worker orchestrating FFmpeg and speech/text models. Local development uses Docker Compose for PostgreSQL 16 and Redis 7. Media processing belongs in workers, not in API request handlers.

## Staged delivery

| Stage | Scope | Exit criteria | Main dependency or decision |
| --- | --- | --- | --- |
| 0. Foundation | Public landing page shell, FastAPI health routes, Compose services, local configuration examples, setup guide. | Clean local setup; PostgreSQL and Redis healthy; API liveness and dependency readiness work; landing page builds; no media or model processing. | Complete before product workflows. |
| 1. Source intake | Local project creation, YouTube URL reference validation/storage, direct-upload validation, private file storage, permission confirmation, retention, and deletion. | Valid and invalid inputs produce clear outcomes; media remains outside the web root; project/source deletion and expiry cleanup work. | Current local defaults: MP4/MOV, 500 MB per file, 60 minutes, 2 GB total local storage, one upload at a time, local storage, and seven-day expiry. YouTube links are references only and cause no network fetch. YouTube bytes require an authorized method; metadata access alone is not permission to download. |
| 2. Transcription | Background job records, staged progress, audio extraction, timestamped transcription, retry and failure recovery. | Representative permission-cleared recordings transcribe; transcript segments and timestamps can be inspected; stage failures preserve project state and allow safe retry. | Code uses faster-whisper small, CPU int8, one worker, and a lazy model download. Benchmark on target-language samples and record memory/runtime before accepting the milestone. |
| 3. Highlight candidates | Coherent segment assembly, transparent ranking signals, candidate explanations, selection and rejection. | Human reviewers judge candidate coherence against an agreed sample set; every candidate has source boundaries and transcript excerpt; edits and rejection are recorded. | Transcript-aligned candidate windows and review controls are implemented. Quality scoring remains gated on an agreed evaluation rubric and sample set; use completeness, clarity, relevance, emphasis/novelty, and audio quality without claiming a universal virality score. |
| 4. Clip rendering | Selected-range trimming, 9:16 output preset, safe-margin captions, preview, downloadable export. | Selected ranges render repeatably; captions are readable and correctable; output and caption sidecar/burn-in options match the supported product choice. | Verify FFmpeg codecs and output sizes on representative source media; confirm target platform resolutions and watermark policy. |
| 5. Creator editor | Timeline range edits, caption corrections, presets, crop/focus controls, autosave and saved state. | Refresh preserves edits; preview seeking tracks transcript timestamps; preview composition and final render agree; keyboard and mobile review remain usable. | Build on stable candidate, transcript, and render parameter contracts from stages 2–4. |
| 6. Accounts and collaboration | Local accounts, ownership checks, team spaces, invitations, editor and reviewer access. | Local access checks cover project/source/transcription/candidate/render operations; role rules, session handling, and CSRF checks are implemented and smoke-checked. | Implemented for local development. Before shared deployment, choose the identity provider and collaboration policy; add email verification/recovery, MFA, distributed rate limiting, audit logging, and a security review. See `milestone-6-accounts-and-collaboration.md`. |
| 7. Production readiness | Observability, quotas, resource limits, backup/restore, security review, privacy and acceptable-use policy, deployment runbooks and cost controls. | Operators can see job state and failures, restore durable data, control spend and concurrency, and answer deletion/privacy requests; launch policies and recovery steps are reviewed. | Local DB backup/restore tooling, CI audits, dependency update configuration, and initial request/job events are implemented. CI must run on GitHub; production backup, resource, policy, identity, security-review, and deployment gates remain. Details are in `milestone-7-production-readiness.md`. |

## Core workflow and job state

The intended creator path is: create project → provide and confirm a permitted source → configure language, duration, clip count, and aspect ratio → watch staged processing → inspect ranked highlights → edit range/captions/crop → render → review and approve → download → manage or delete the project.

Recommended durable lifecycle: `Draft → Queued → Validating → Extracting → Transcribing → Selecting highlights → Rendering → Review required → Complete`. `Failed`, `Cancelled`, and `Expired` are terminal alternatives. Each running state needs a last-update time and actionable recovery or cancellation guidance where safe. PostgreSQL remains the durable record; Redis is not the only record of progress.

Workers should run stages sequentially at first. Retryable stages should record structured failures without losing project metadata. Before opening intake to users, establish limits for file size, source duration, concurrent work, temporary disk, and output storage. Deletion must cover originals, intermediates, transcripts, previews, exports, and project records according to the published retention policy.

## Product and safety gates

- **Source rights:** require an affirmative permission confirmation. Do not implement YouTube downloading through circumvention. If authorized access is unavailable, explain the limitation and offer direct upload.
- **Privacy:** disclose processing location, stored data, retention, and deletion behavior before intake goes live. Protect media with access checks and non-public URLs.
- **Quality:** use permission-cleared or synthetic samples; record human judgments for relevance, completeness, clarity, and editability before presenting quality claims.
- **Local resources:** on the target Apple Silicon machine with 16 GB unified memory, do not run transcription, a local text model, and rendering concurrently until measured. Do not fetch model weights in the foundation stage.
- **Launch readiness:** publish privacy, terms, acceptable-use guidance, and a support contact before public processing. Keep hosting, storage, and model costs visible; “open-source first” does not mean zero operating cost.

## Open decisions to resolve before the dependent stage

1. Final brand name and domain.
2. Permitted source workflow, supported file formats, maximum duration and file size.
3. Target platforms, output resolution, default duration presets, caption languages, and watermark policy.
4. Storage region, retention duration, and deletion guarantees.
5. Representative evaluation set and human scoring rubric for candidate quality.
6. Hosting budget and whether future hosted inference/storage is subsidized or paid.

Do not invent a specific answer to these decisions in implementation. Record the chosen policy before building the milestone that depends on it.
