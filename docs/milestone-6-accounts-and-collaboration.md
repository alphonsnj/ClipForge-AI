# Milestone 6: Accounts and collaboration

## Local account workflow

This stage uses provider-neutral, self-hosted accounts so the local product workflow can be reviewed before choosing an external identity provider. The first account created after migration is the initial owner; later accounts are invitation-only. The initial owner claims the migration-created `Local workspace`, which also preserves access to any pre-existing projects assigned to that legacy team.

Owners can create additional workspaces, invite editors or reviewers, copy a one-time invitation link, and remove members. Invitations expire after 24 hours and are stored as token hashes. No invitation email is sent. The invitee proves possession of the link and creates a password; an existing account must confirm its password before joining the additional workspace.

| Role | Read projects, transcripts, previews, downloads | Create projects, upload, edit, transcribe, render | Delete projects/sources | Invite/remove members |
| --- | --- | --- | --- | --- |
| Owner | Yes | Yes | Yes | Yes |
| Editor | Yes | Yes | No | No |
| Reviewer | Yes | No | No | No |

Projects belong to a team. Every project, source preview, transcription, candidate, render, and export endpoint checks the session's team membership. A reviewer can preview and download, but cannot mutate project state. A workspace must retain at least one owner.

## Session and password handling

- Passwords require 12–128 characters and are stored using salted `scrypt` hashes (`N=32768`, `r=8`, `p=1`); passwords are never stored or logged in plaintext.
- Opaque, random session tokens are held in `HttpOnly` cookies; only SHA-256 token verifiers are stored in PostgreSQL. Sessions expire after 14 days. Password changes revoke the account's old sessions and issue a fresh one.
- Mutating browser requests require an allowed `Origin`, a separate CSRF cookie, and a matching `X-CSRF-Token` header verified against the session record. CORS allows credentials only for the configured frontend origins.
- Failed-login counters are stored in shared Redis: ten failures per peer IP per 15 minutes across API processes. Keys use an HMAC digest of the address; production requires a deployment-managed `LOGIN_RATE_LIMIT_HASH_KEY`. Sign-in fails closed when Redis is unavailable. Behind a reverse proxy, configure trusted proxy address handling before enabling public login; the application does not trust arbitrary forwarded-IP headers.
- The production-oriented API entry point is `python -m app.server`. It uses Uvicorn's proxy header support with only the addresses in `TRUSTED_PROXY_IPS` (defaults to loopback) and disables Uvicorn access logs so query strings are not written to logs. Set that variable to the exact proxy IPs/CIDRs for a deployment; production startup rejects malformed values.
- Rate-limit and limiter-outage events are emitted without client addresses, account emails, or credentials. They still need deployment alert routing and monitoring.
- `AUTH_COOKIE_SECURE=false` supports the local HTTP setup. Set it to `true` behind HTTPS. Do not expose the development app to a public or shared network.

The password/session approach follows OWASP recommendations to use slow password hashing, high-entropy opaque session IDs, HttpOnly cookies, and CSRF defenses. See the [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) and [Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).

## Migration and configuration

Apply `0009_accounts_and_teams` with `alembic upgrade head`, then restart API and frontend. Configure `CORS_ORIGINS`, `FRONTEND_BASE_URL`, and `AUTH_COOKIE_SECURE` in `backend/.env`. Existing unowned local project rows are assigned to a migration-created starter team and claimed by the first owner at setup.

## Not yet implemented

There is no email delivery or email ownership verification, forgotten-password recovery, MFA, account deletion, external identity provider, invitation revocation, or security audit log. Deployment-specific trusted proxy addresses, rate-limit alert routing, production TLS/session-key operations, and independent security review remain required before any public or shared deployment. These remain Milestone 7 security and production-readiness work.
