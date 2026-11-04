"""Startup checks that prevent accidental production use of local defaults."""

import os
import ipaddress
from urllib.parse import urlsplit


def _is_https_origin(value: str) -> bool:
    try:
        parsed = urlsplit(value)
        return (
            parsed.scheme == "https"
            and bool(parsed.hostname)
            and parsed.username is None
            and parsed.password is None
            and parsed.path in ("", "/")
            and not parsed.query
            and not parsed.fragment
        )
    except ValueError:
        return False


def validate_runtime_configuration() -> None:
    mode = os.getenv("APP_ENV", "development").strip().lower()
    if mode not in {"development", "test", "production"}:
        raise RuntimeError("APP_ENV must be development, test, or production.")
    if mode != "production":
        return

    problems: list[str] = []
    database_url = os.getenv("DATABASE_URL", "")
    redis_url = os.getenv("REDIS_URL", "")
    frontend_url = os.getenv("FRONTEND_BASE_URL", "")
    rate_limit_key = os.getenv("LOGIN_RATE_LIMIT_HASH_KEY", "")
    origins = [item.strip() for item in os.getenv("CORS_ORIGINS", "").split(",") if item.strip()]
    try:
        database = urlsplit(database_url)
        redis = urlsplit(redis_url)
    except ValueError:
        database = redis = urlsplit("")

    if database.scheme not in {"postgres", "postgresql", "postgresql+asyncpg"} or not database.hostname or "clipforge_local_only" in database_url:
        problems.append("DATABASE_URL must be an explicit PostgreSQL URL with deployment-managed credentials")
    if redis.scheme not in {"redis", "rediss"} or redis.hostname in {None, "localhost", "127.0.0.1", "::1"}:
        problems.append("REDIS_URL must explicitly identify the deployment queue service")
    if os.getenv("AUTH_COOKIE_SECURE", "false").strip().lower() != "true":
        problems.append("AUTH_COOKIE_SECURE must be true")
    if len(rate_limit_key) < 32 or rate_limit_key.startswith("clipforge-development-only"):
        problems.append("LOGIN_RATE_LIMIT_HASH_KEY must be a deployment-managed secret of at least 32 characters")
    if not _is_https_origin(frontend_url):
        problems.append("FRONTEND_BASE_URL must be an HTTPS origin")
    if not origins or any(not _is_https_origin(origin) for origin in origins):
        problems.append("CORS_ORIGINS must contain only HTTPS origins")
    trusted_proxies = [item.strip() for item in os.getenv("TRUSTED_PROXY_IPS", "127.0.0.1,::1").split(",") if item.strip()]
    try:
        for proxy in trusted_proxies:
            ipaddress.ip_network(proxy, strict=False)
    except ValueError:
        problems.append("TRUSTED_PROXY_IPS must contain comma-separated IP addresses or CIDRs")

    if problems:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(problems))
