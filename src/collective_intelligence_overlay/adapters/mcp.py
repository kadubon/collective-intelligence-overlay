"""Official MCP client, restricted to operator registered endpoints and tool names."""

from typing import Any

import httpx2
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from ..models import UseRequest
from ..overlay import Overlay
from ..security import allowed_url


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
