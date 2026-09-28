"""Official MCP client, restricted to operator registered endpoints and tool names."""

from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client
from mcp.types import Tool

from ..models import UseRequest
from ..overlay import Overlay
from ..security import allowed_url


async def invoke_registered(
    endpoint: str, name: str, interface_digest: str, arguments: dict[str, Any]
) -> Any:
    """Registry-only actuator. Observe the pinned tool contract on every call."""
    from ..bindings import fingerprint

    async with httpx2.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as http:
        transport = streamable_http_client(endpoint, http_client=http)
        async with Client(transport, read_timeout_seconds=20) as client:
            cursor = None
            matches: list[Tool] = []
            seen = set()
            for _ in range(16):
                page = await client.list_tools(cursor=cursor, cache_mode="refresh")
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
) -> Any:
    allowed_url(endpoint, endpoints, local=local)
    if name not in tools:
        raise ValueError("tool not authorized")

    async def operation() -> Any:
        async with httpx2.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as http:
            transport = streamable_http_client(endpoint, http_client=http)
            async with Client(transport, read_timeout_seconds=20) as client:
                result = await client.call_tool(name, arguments)
                if result.is_error:
                    raise ValueError("MCP tool failed; verification remains unknown")
                return result.structured_content

    return await overlay.execute(request, operation)
