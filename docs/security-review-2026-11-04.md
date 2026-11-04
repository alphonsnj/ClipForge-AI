# Local security review - 4 November 2026

## Scope and limits

This is a source-level review of the local-development API, auth/session handling, project/source access, media path handling, FFmpeg invocation, and the CI configuration. It is not a penetration test, legal review, independent assessment, or production security approval. The local workflow smoke checks and dependency audits are recorded in the [validation log](validation-log.md).

## Controls observed

- Project, transcription, candidate, and render routes use the session/team access dependency; reviewers are read-only and destructive project/source operations are owner-only.
- Mutating browser routes require an allowed Origin and matching session-bound CSRF token. Session IDs are random and stored as hashes; passwords use salted scrypt.
- Uploaded bytes are size-limited, probed with FFprobe, stored under generated UUID keys in a private local directory, and served through authenticated routes. Storage paths are constrained beneath the configured root.
- FFmpeg is invoked with an argument array rather than a shell command. Captions are escaped for ASS output. Worker events avoid logging source filenames and FFmpeg stderr.
- PostgreSQL and Redis Compose ports bind to loopback. Dependency audits reported no known findings on the review date.

## Findings that remain open

| Finding | Impact | Required before shared/public use |
| --- | --- | --- |
| Login throttling is process-local and keyed by client IP, with a bounded in-memory address table. | It is not shared across replicas and is not a reliable public abuse control. | Add a distributed limiter, proxy-aware client identity rules, and alerting. |
| No verified email, recovery, MFA, invitation revocation, or account deletion flow. | Account ownership and recovery cannot meet common hosted-service needs. | Select an identity policy and implement/review its lifecycle. |
| Exception tracebacks are not centrally redacted. | Runtime/SQL diagnostics could expose local paths or operational details. | Define a redaction policy, test it, and restrict log access/retention. |
| Local database/media archives are not encrypted and the database archive excludes media. | Local archive files expose user data and are incomplete for full recovery. | Choose encrypted storage, backup coverage, retention, access policy, and restore objectives. |
| `AUTH_COOKIE_SECURE` defaults to false for HTTP development. | A deployment that retains the development setting could send session cookies over HTTP. | A startup guard now refuses `APP_ENV=production` unless the database URL is explicit and not using the local-only password, Redis/Redis-TLS is explicit, and frontend/CORS origins use HTTPS. Deployment still needs independent review. |
| The CI and Dependabot configuration is present; the draft PR's follow-up CI run passed all four jobs on 4 November 2026. | A single pass does not establish long-term dependency or floating base-image safety. | Keep scheduled and PR CI enabled, review each Dependabot proposal, and investigate future scanner findings rather than carrying exceptions forward automatically. |
| The PostgreSQL image scan reports 26 HIGH/CRITICAL findings against the Go standard library embedded in `/usr/local/bin/gosu`; the PostgreSQL Alpine OS package scan is clean. | Generic scanners identify vulnerable standard-library APIs without establishing that this small utility calls those code paths. gosu maintainers document this false-positive pattern and direct users to call-path analysis. | A temporary Trivy exception is limited to the exact reported CVE IDs and `pkg:golang/stdlib@v1.24.6`, and expires 4 February 2027. Re-run the scan and reassess the exception before expiry or when the image/gosu component changes. This is a scanner exception, not a vulnerability remediation. |
| Call-path review of the local PostgreSQL image's gosu 1.19 found GO-2026-6686 in `github.com/moby/sys/user` v0.1.0; govulncheck identifies reachable parsing functions. | The moderate DoS advisory applies if an attacker can supply crafted passwd/group-style input. The product does not intentionally supply these files, but this is a real dependency finding and Trivy's image scan did not surface it. | Do not carry this as a false positive or under the stdlib exception. Require a PostgreSQL image with patched `moby/sys/user` v0.4.1 (gosu 1.20 source tag currently passes govulncheck) or document an independently reviewed risk acceptance before shared/public use. |
| GitHub Actions references can move when they use release tags, and the Trivy Action experienced a 2026 supply-chain compromise affecting older releases. | Mutable references can change what CI executes without a repository change. | CI actions are pinned to the verified v7/v0.36.0 commit IDs; Dependabot remains configured to propose reviewed updates. Recheck action provenance before accepting updates. |
| No independent security assessment or privacy/legal review has occurred. | Source review cannot establish resistance to real-world attacks or compliance. | Complete qualified review against the selected jurisdiction, product scope, and deployment. |

Keep the service bound to the local machine until these items are addressed and the production-readiness gates in [Milestone 7](milestone-7-production-readiness.md) have evidence.
