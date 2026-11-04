"""Local-first API for ClipForge project and source intake."""

import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

import asyncpg
from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from redis.asyncio import Redis
from redis.exceptions import RedisError

from .db import engine
from .middleware import UploadLimitMiddleware
from .candidate_routes import router as candidate_router
from .routes import expiry_worker, router, stop_expiry_worker
from .transcription_routes import router as transcription_router
from .render_routes import router as render_router
from .auth_routes import router as auth_router, team_router
from .auth import current_user
from .configuration import validate_runtime_configuration
from .models import User
from .observability import RequestLogMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    validate_runtime_configuration()
    app.state.database_url = os.getenv(
        "DATABASE_URL",
        "postgresql://clipforge:clipforge_local_only@localhost:5432/clipforge",
    )
    app.state.redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    cleanup_task = asyncio.create_task(expiry_worker(), name="source-expiry-cleanup")
    try:
        yield
    finally:
        await stop_expiry_worker(cleanup_task)
        await engine.dispose()


app = FastAPI(
    title="ClipForge AI API",
    description="Local source intake with YouTube references, background transcription, and transcript-aligned highlight candidates.",
    version="0.5.0",
    lifespan=lifespan,
)
app.add_middleware(UploadLimitMiddleware)
app.add_middleware(RequestLogMiddleware)
allowed_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000"
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Content-Type", "X-CSRF-Token"],
)
app.include_router(auth_router)
app.include_router(team_router)
app.include_router(router)
app.include_router(transcription_router)
app.include_router(candidate_router)
app.include_router(render_router)


@app.get("/api/intake/config", tags=["intake"])
async def intake_config(_: User = Depends(current_user)) -> dict[str, object]:
    """Expose the active local intake limits to the workspace interface."""
    from .intake import (
        MAX_MEDIA_STORAGE_BYTES,
        MAX_UPLOAD_BYTES,
        MAX_VIDEO_DURATION_SECONDS,
        SOURCE_RETENTION_DAYS,
    )

    return {
        "accepted_formats": ["mp4", "mov"],
        "max_upload_bytes": MAX_UPLOAD_BYTES,
        "max_media_storage_bytes": MAX_MEDIA_STORAGE_BYTES,
        "max_video_duration_seconds": MAX_VIDEO_DURATION_SECONDS,
        "source_retention_days": SOURCE_RETENTION_DAYS,
        "youtube_processing": False,
        "access_scope": "authenticated-local-team",
    }


@app.get("/health", tags=["health"])
async def health() -> dict[str, str]:
    """Report that the API process is responding without checking dependencies."""
    return {"status": "ok"}


@app.get("/health/ready", tags=["health"])
async def readiness() -> dict[str, object]:
    """Check dependencies and return 503 until both are available."""
    checks: dict[str, str] = {"postgres": "unavailable", "redis": "unavailable"}

    try:
        connection = await asyncpg.connect(
            app.state.database_url,
            timeout=2,
            command_timeout=2,
        )
        try:
            await connection.execute("SELECT 1")
            checks["postgres"] = "ok"
        finally:
            await connection.close()
    except (OSError, TimeoutError, asyncpg.PostgresError, ValueError):
        pass

    client: Redis = Redis.from_url(
        app.state.redis_url,
        socket_connect_timeout=2,
        socket_timeout=2,
        decode_responses=True,
    )
    try:
        await client.ping()
        checks["redis"] = "ok"
    except (OSError, TimeoutError, RedisError, ValueError):
        pass
    finally:
        await client.aclose()

    ready = all(value == "ok" for value in checks.values())
    if not ready:
        raise HTTPException(
            status_code=503,
            detail={"status": "not_ready", "dependencies": checks},
        )
    return {"status": "ready", "dependencies": checks}
