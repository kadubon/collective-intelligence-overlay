"""Bound untrusted HTTP input before SDK parsing; retain ordinary ASGI semantics."""

import asyncio
from collections.abc import Callable
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from ssl import CERT_REQUIRED, SSLContext

import httpx
from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from ..security import MAX_RECORD_BYTES


class InvalidPeerResponse(ValueError):
    """Expected structural/size rejection at an untrusted HTTP response boundary."""


class BodyLimit:
    def __init__(self, app: ASGIApp, seconds: float = 30) -> None:
        self.app = app
        self.seconds = seconds

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        body = bytearray()
        try:
            async with asyncio.timeout(self.seconds):
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
        except TimeoutError:
            await JSONResponse({"error": "REQUEST_BODY_TIMEOUT"}, status_code=408)(
                scope, receive, send
            )
            return
        delivered = False

        async def replay() -> Message:
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": bytes(body), "more_body": False}
            return await receive()

        await self.app(scope, replay, send)


class RequestCapacity:
    """Finite authenticated ASGI requests, including expensive reads and body receipt."""

    def __init__(self, app: ASGIApp, owner_limit: int = 16, caller_limit: int = 4) -> None:
        self.app, self.owner_limit, self.caller_limit = app, owner_limit, caller_limit
        self.active = 0
        self.callers: dict[str, int] = {}

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        user = scope.get("user")
        if user is None or not user.is_authenticated:
            await JSONResponse({"error": "AUTHENTICATION_REQUIRED"}, status_code=401)(
                scope, receive, send
            )
            return
        caller = user.display_name
        count = self.callers.get(caller, 0)
        if count >= self.caller_limit or self.active >= self.owner_limit:
            per_caller = count >= self.caller_limit
            await JSONResponse(
                {"error": "CALLER_REQUEST_LIMIT" if per_caller else "OWNER_REQUEST_LIMIT"},
                status_code=429 if per_caller else 503,
                headers={"Retry-After": "1"},
            )(scope, receive, send)
            return
        self.active += 1
        self.callers[caller] = count + 1
        try:
            await self.app(scope, receive, send)
        finally:
            self.active -= 1
            self.callers[caller] -= 1
            if self.callers[caller] == 0:
                del self.callers[caller]


class BoundedA2ATransport(httpx.AsyncBaseTransport):
    """Restrict SDK HTTP requests and bound response bytes before protobuf parsing."""

    def __init__(
        self,
        endpoint: str,
        *,
        response_validator: Callable[[str, bytes], None] | None = None,
        tls_context: SSLContext | None = None,
        readonly_post: bool = False,
        seconds: float = 30,
    ) -> None:
        self.allowed = {
            ("POST", endpoint),
            ("GET", endpoint.rstrip("/") + "/.well-known/agent-card.json"),
        }
        if tls_context is not None and (
            not tls_context.check_hostname or tls_context.verify_mode != CERT_REQUIRED
        ):
            raise ValueError("verified TLS context required")
        self.transport = httpx.AsyncHTTPTransport(
            retries=0, trust_env=False, verify=tls_context if tls_context is not None else True
        )
        self.response_validator = response_validator
        self.readonly_post = readonly_post
        self.seconds = seconds

    async def handle_async_request(self, request: httpx.Request) -> httpx.Response:
        try:
            async with asyncio.timeout(self.seconds):
                return await self._bounded_request(request)
        except TimeoutError:
            raise httpx.ReadTimeout(
                "A2A operation exceeded its network deadline", request=request
            ) from None

    async def _bounded_request(self, request: httpx.Request) -> httpx.Response:
        if (request.method, str(request.url)) not in self.allowed:
            raise ValueError("A2A SDK request left the configured service boundary")
        request.headers["accept-encoding"] = "identity"
        readonly = request.method == "GET" or self.readonly_post
        if readonly and len(await request.aread()) > MAX_RECORD_BYTES:
            raise ValueError("readonly retry body exceeds byte bound")
        for attempt in range(4):
            response = await self.transport.handle_async_request(request)
            if not readonly or attempt == 3 or response.status_code not in {429, 503}:
                break
            delay = min(0.25 * (2**attempt), 5)
            retry_after = response.headers.get("Retry-After")
            if retry_after is not None:
                try:
                    delay = float(int(retry_after))
                except ValueError:
                    try:
                        value = parsedate_to_datetime(retry_after)
                        delay = (value - datetime.now(UTC)).total_seconds()
                    except (ValueError, TypeError, OverflowError):
                        pass
            if not 0 <= delay <= 5:
                break  # Do not retry earlier than a server's larger requested wait.
            await response.aclose()
            await asyncio.sleep(delay)
        try:
            if response.headers.get("content-encoding", "identity") != "identity":
                raise InvalidPeerResponse("compressed A2A response is not supported")
            content = bytearray()
            async for chunk in response.aiter_raw():
                if len(content) + len(chunk) > MAX_RECORD_BYTES:
                    raise InvalidPeerResponse("A2A service response exceeds byte bound")
                content.extend(chunk)
            if self.response_validator is not None and response.is_success:
                self.response_validator(request.method, bytes(content))
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
