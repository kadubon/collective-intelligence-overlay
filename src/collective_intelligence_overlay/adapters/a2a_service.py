"""Narrow standard A2A binding: JSON input and an immediate JSON data result."""

from typing import Any

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict

from ..bindings import Target, active_invocation, fingerprint
from ..models import uid
from ..security import MAX_RECORD_BYTES
from .a2a import struct


class _BoundedTransport(httpx.AsyncBaseTransport):
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


async def invoke(
    target: Target, endpoint: str, arguments: dict[str, Any], *, auth: httpx.Auth | None = None
) -> Any:
    """No overlay extension, remote code attestation or protocol Task continuation."""
    async with httpx.AsyncClient(
        transport=_BoundedTransport(endpoint),
        auth=auth,
        timeout=30,
        follow_redirects=False,
        trust_env=False,
    ) as http:
        card = await A2ACardResolver(http, endpoint).get_agent_card()
        if fingerprint(MessageToDict(card)) != target.interface_digest:
            raise ValueError("A2A card changed; requalification required")
        if (
            card.name != target.peer
            or not card.supported_interfaces
            or any(
                interface.url != endpoint
                or interface.protocol_binding != "JSONRPC"
                or interface.protocol_version != "1.0"
                for interface in card.supported_interfaces
            )
            or not any(skill.id == target.name for skill in card.skills)
            or any(extension.required for extension in card.capabilities.extensions)
        ):
            raise ValueError("A2A card identity, destination, skill or extension is unsupported")
        client = await create_client(
            card,
            ClientConfig(
                streaming=False,
                polling=False,
                httpx_client=http,
                supported_protocol_bindings=["JSONRPC"],
            ),
        )
        request = SendMessageRequest(
            message=Message(
                message_id=active_invocation.get() or uid(),
                role=Role.ROLE_USER,
                parts=[Part(data=struct(arguments))],
            )
        )
        async for response in client.send_message(request):
            if not response.HasField("message"):
                raise ValueError("A2A service returned a Task; result requires reconciliation")
            reply = response.message
            if (
                reply.role != Role.ROLE_AGENT
                or reply.extensions
                or len(reply.parts) != 1
                or reply.parts[0].WhichOneof("content") != "data"
            ):
                raise ValueError("A2A service did not return the registered JSON result shape")
            return MessageToDict(reply.parts[0].data)
        raise ValueError("A2A service completed without a result")
