"""Structured, content-free request and worker lifecycle events."""

import json
import logging
import time
from uuid import uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send


def emit_event(logger: logging.Logger, event: str, **fields: str | int | float | bool | None) -> None:
    """Emit one JSON event containing only explicitly supplied operational fields."""
    logger.info(json.dumps({"event": event, **fields}, separators=(",", ":"), sort_keys=True))


class RequestLogMiddleware:
    """Add a server-generated correlation ID and log route metadata, never request bodies."""

    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request_id = uuid4().hex
        started = time.perf_counter()
        status_code = 500

        async def send_with_request_id(message: Message) -> None:
            nonlocal status_code
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                headers = list(message.get("headers", []))
                headers.append((b"x-request-id", request_id.encode("ascii")))
                message = {**message, "headers": headers}
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            emit_event(
                logging.getLogger("clipforge.request"),
                "http.request.completed",
                request_id=request_id,
                method=str(scope.get("method", "")),
                path=str(scope.get("path", "")),
                status_code=status_code,
                duration_ms=round((time.perf_counter() - started) * 1000, 2),
            )
