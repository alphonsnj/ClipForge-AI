"""Request-level upload size and concurrency limits."""

import json

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from .intake import UPLOAD_LOCK, request_body_limit


class UploadTooLarge(Exception):
    pass


class UploadLimitMiddleware:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if not self._is_source_upload(scope):
            await self.app(scope, receive, send)
            return

        max_body = request_body_limit()
        content_length = next(
            (value for name, value in scope.get("headers", []) if name.lower() == b"content-length"),
            None,
        )
        if content_length is not None:
            try:
                if int(content_length) > max_body:
                    await self._reject(send, "This upload request exceeds the request size limit.")
                    return
            except ValueError:
                await self._reject(send, "The upload request has an invalid content length.", 400)
                return

        async with UPLOAD_LOCK:
            received = 0

            async def limited_receive() -> Message:
                nonlocal received
                message = await receive()
                if message["type"] == "http.request":
                    received += len(message.get("body", b""))
                    if received > max_body:
                        raise UploadTooLarge
                return message

            try:
                await self.app(scope, limited_receive, send)
            except UploadTooLarge:
                await self._reject(send, "This upload request exceeds the request size limit.")

    @staticmethod
    def _is_source_upload(scope: Scope) -> bool:
        return (
            scope["type"] == "http"
            and scope.get("method") == "POST"
            and scope.get("path", "").startswith("/api/projects/")
            and scope.get("path", "").endswith("/source")
        )

    @staticmethod
    async def _reject(send: Send, detail: str, status_code: int = 413) -> None:
        payload = json.dumps({"detail": detail}).encode("utf-8")
        await send({"type": "http.response.start", "status": status_code, "headers": [(b"content-type", b"application/json")]})
        await send({"type": "http.response.body", "body": payload})
