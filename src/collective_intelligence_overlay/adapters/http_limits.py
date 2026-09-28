"""Bound untrusted HTTP input before SDK parsing; retain ordinary ASGI semantics."""

import httpx
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
        body = bytearray()
        while True:
            message = await receive()
            if message["type"] == "http.disconnect":
                return
            body.extend(message.get("body", b""))
            if len(body) > MAX_RECORD_BYTES:
                await JSONResponse({"error": "request too large"}, status_code=413)(
                    scope, receive, send
                )
                return
            if not message.get("more_body", False):
                break
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


class BoundedA2ATransport(httpx.AsyncBaseTransport):
    """Restrict SDK HTTP requests and bound response bytes before protobuf parsing."""

    def __init__(self, endpoint: str) -> None:
        self.allowed = {
            ("POST", endpoint),
            ("GET", endpoint.rstrip("/") + "/.well-known/agent-card.json"),
        }
        self.transport = httpx.AsyncHTTPTransport(retries=0, trust_env=False)

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        if (request.method, str(request.url)) not in self.allowed:
            raise ValueError("A2A SDK request left the configured service boundary")
        request.headers["accept-encoding"] = "identity"
        response = await self.transport.handle_async_request(request)
        try:
            if response.headers.get("content-encoding", "identity") != "identity":
                raise ValueError("compressed A2A response is not supported")
            content = bytearray()
            async for chunk in response.aiter_raw():
                if len(content) + len(chunk) > MAX_RECORD_BYTES:
                    raise ValueError("A2A service response exceeds byte bound")
                content.extend(chunk)
            return httpx.Response(
                response.status_code,
                headers=response.headers,
                content=bytes(content),
                request=request,
            )
        finally:
            await response.aclose()

    async def aclose(self) -> None:
        await self.transport.aclose()
