"""Bound untrusted HTTP input before SDK parsing; retain ordinary ASGI semantics."""

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..security import MAX_RECORD_BYTES


class BodyLimit:
    def __init__(self, app: ASGIApp) -> None:
        self.app = app

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        buffered: list[Message] = []
        size = 0
        while True:
            message = await receive()
            size += len(message.get("body", b""))
            if size > MAX_RECORD_BYTES:
                await JSONResponse({"error": "request too large"}, status_code=413)(
                    scope, receive, send
                )
                return
            buffered.append(message)
            if message["type"] == "http.disconnect" or not message.get("more_body", False):
                break

        async def replay() -> Message:
            if buffered:
                return buffered.pop(0)
            return await receive()

        await self.app(scope, replay, send)
