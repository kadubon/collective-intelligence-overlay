"""Official MCP client, restricted to operator registered endpoints and tool names."""

import asyncio
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool
from pydantic import BaseModel, ConfigDict, Field

from ..models import UseRequest
from ..overlay import Overlay
from ..security import allowed_url


class ReceiveLimits(BaseModel):
    """Operator transport bounds, before SDK JSON decoding; not model arguments."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    bytes: int = Field(default=262144, ge=1024, le=1048576)
    depth: int = Field(default=64, ge=8, le=128)
    tools: int = Field(default=128, ge=1, le=1024)
    seconds: float = Field(default=20, gt=0, le=30)


class MCPReceiveLimit(httpx2.StreamError):
    pass


DEFAULT_RECEIVE_LIMITS = ReceiveLimits()


class _BoundedResponse(httpx2.AsyncByteStream):
    """Public HTTPX2 response hook wraps the stream consumed by the official SDK."""

    def __init__(
        self,
        stream: httpx2.AsyncByteStream,
        limits: ReceiveLimits,
        on_limit: Callable[[str], None],
        *,
        sse: bool = False,
    ) -> None:
        self.stream, self.limits, self.on_limit, self.sse = stream, limits, on_limit, sse

    def _fail(self, reason: str) -> None:
        self.on_limit(reason)
        raise MCPReceiveLimit(reason)

    async def __aiter__(self) -> AsyncIterator[bytes]:
        size = depth = 0
        quoted = escaped = False
        prefix = bytearray()
        data_line = False
        async for chunk in self.stream:
            size += len(chunk)
            if size > self.limits.bytes:
                self._fail("MCP_RESPONSE_BYTES_EXCEEDED")
            # A small lexer checks nesting without constructing a JSON object.
            # String/escape state carries across network chunks and SSE data lines.
            for value in chunk:
                if self.sse:
                    # Only SSE data fields carry JSON. Comments and event IDs
                    # must not alter quote/depth state to bypass the bound. The
                    # official HTTPX2 EventSource still parses/dispatches events.
                    if value == 10:
                        if not prefix or prefix == b"\r":
                            depth = 0
                            quoted = escaped = False
                        prefix.clear()
                        data_line = False
                        continue
                    if not data_line:
                        if len(prefix) < 9:
                            prefix.append(value)
                        candidate = bytes(prefix).removeprefix(b"\xef\xbb\xbf")
                        if candidate == b"data:":
                            data_line = True
                        continue
                if quoted:
                    if escaped:
                        escaped = False
                    elif value == 92:
                        escaped = True
                    elif value == 34:
                        quoted = False
                elif value == 34:
                    quoted = True
                elif value in {91, 123}:
                    depth += 1
                    if depth > self.limits.depth:
                        self._fail("MCP_RESPONSE_DEPTH_EXCEEDED")
                elif value in {93, 125}:
                    depth = max(0, depth - 1)
            yield chunk

    async def aclose(self) -> None:
        await self.stream.aclose()


@asynccontextmanager
async def _client(
    endpoint: str, factory: Callable[[], httpx2.AsyncClient] | None, limits: ReceiveLimits
) -> AsyncIterator[Client]:
    http = (
        factory()
        if factory is not None
        else httpx2.AsyncClient(timeout=limits.seconds, follow_redirects=False, trust_env=False)
    )
    if http.follow_redirects:
        await http.aclose()
        raise ValueError("registered MCP client must not follow redirects")
    violations: list[str] = []

    async def receive(response: httpx2.Response) -> None:
        # Compression could expand within a decoder before the bound sees bytes.
        # Ask for identity and fail closed if a peer nevertheless compresses data.
        if response.headers.get("content-encoding", "identity").lower() != "identity":
            raise MCPReceiveLimit("MCP_COMPRESSED_RESPONSE_UNSUPPORTED")
        if response.is_redirect:
            raise MCPReceiveLimit("MCP_REDIRECT_UNSUPPORTED")
        length = response.headers.get("content-length")
        if length is not None and (not length.isdigit() or int(length) > limits.bytes):
            raise MCPReceiveLimit("MCP_RESPONSE_BYTES_EXCEEDED")
        if not isinstance(response.stream, httpx2.AsyncByteStream):
            raise MCPReceiveLimit("MCP_ASYNC_RESPONSE_REQUIRED")
        response.stream = _BoundedResponse(
            response.stream,
            limits,
            violations.append,
            sse=response.headers.get("content-type", "").startswith("text/event-stream"),
        )

    http.headers["Accept-Encoding"] = "identity"
    http.event_hooks["response"].insert(0, receive)
    try:
        async with http, asyncio.timeout(limits.seconds):
            transport = streamable_http_client(endpoint, http_client=http)
            async with Client(transport, read_timeout_seconds=limits.seconds) as client:
                yield client
        if violations:
            raise MCPReceiveLimit(violations[0])
    except Exception as error:
        # MCP 2.2 may translate an SSE stream error to a generic ended-stream
        # error. Preserve the detected transport reason without retrying.
        if violations:
            raise MCPReceiveLimit(violations[0]) from error
        raise
    finally:
        http.event_hooks["response"].remove(receive)


async def invoke_registered(
    endpoint: str,
    name: str,
    interface_digest: str,
    arguments: dict[str, Any],
    *,
    http_client_factory: Callable[[], httpx2.AsyncClient] | None = None,
    receive_limits: ReceiveLimits = DEFAULT_RECEIVE_LIMITS,
) -> Any:
    """Registry-only actuator. Observe the pinned tool contract on every call."""
    from ..bindings import fingerprint

    async with _client(endpoint, http_client_factory, receive_limits) as client:
        cursor = None
        matches: list[Tool] = []
        seen = set()
        tool_count = 0
        for _ in range(16):
            page = await client.list_tools(cursor=cursor, cache_mode="refresh")
            tool_count += len(page.tools)
            if tool_count > receive_limits.tools:
                raise ValueError("MCP_TOOL_COUNT_EXCEEDED")
            matches.extend(tool for tool in page.tools if tool.name == name)
            cursor = page.next_cursor
            if not cursor:
                break
            if cursor in seen:
                raise ValueError("MCP tool listing repeated cursor")
            seen.add(cursor)
        else:
            raise ValueError("MCP tool listing exceeds discovery bound")
        if len(matches) != 1:
            raise ValueError("registered MCP tool missing or ambiguous")
        tool = matches[0]
        observed = {"name": tool.name, "input": tool.input_schema, "output": tool.output_schema}
        if fingerprint(observed) != interface_digest:
            raise ValueError("MCP interface changed; requalification required")
        result = await client.call_tool(name, arguments)
        if result.is_error:
            raise ValueError("MCP execution failed; result remains unverified")
        return result.structured_content


async def call_tool(
    overlay: Overlay,
    request: UseRequest,
    endpoint: str,
    name: str,
    arguments: dict[str, Any],
    *,
    endpoints: frozenset[str],
    tools: frozenset[str],
    local: bool = False,
    receive_limits: ReceiveLimits = DEFAULT_RECEIVE_LIMITS,
) -> Any:
    allowed_url(endpoint, endpoints, local=local)
    if name not in tools:
        raise ValueError("tool not authorized")

    async def operation() -> Any:
        async with _client(endpoint, None, receive_limits) as client:
            result = await client.call_tool(name, arguments)
            if result.is_error:
                raise ValueError("MCP tool failed; verification remains unknown")
            return result.structured_content

    return await overlay.execute(request, operation)
