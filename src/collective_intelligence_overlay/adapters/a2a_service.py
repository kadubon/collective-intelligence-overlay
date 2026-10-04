"""Narrow standard A2A binding: JSON input and an immediate JSON data result."""

from typing import Any

import httpx
from a2a.client import A2ACardResolver, ClientConfig, create_client
from a2a.types import Message, Part, Role, SendMessageRequest
from google.protobuf.json_format import MessageToDict

from ..bindings import Target, fingerprint
from ..calls import active_call
from ..models import uid
from .a2a import struct
from .http_limits import BoundedA2ATransport


async def invoke(
    target: Target, endpoint: str, arguments: dict[str, Any], *, auth: httpx.Auth | None = None
) -> Any:
    """No overlay extension, remote code attestation or protocol Task continuation."""
    async with httpx.AsyncClient(
        transport=BoundedA2ATransport(endpoint),
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
        try:
            wire_arguments = struct(arguments)
            if MessageToDict(wire_arguments) != arguments:
                raise ValueError("standard A2A data part cannot preserve these numeric values")
            call = active_call.get()
            request = SendMessageRequest(
                message=Message(
                    message_id=call.key if call is not None else uid(),
                    role=Role.ROLE_USER,
                    parts=[Part(data=wire_arguments)],
                )
            )
            result: Any = None
            received = False
            # Finish the nonstreaming SDK request before its HTTP context exits.
            # A JSON null is a result, so receipt presence is tracked separately.
            async for response in client.send_message(request):
                if received:
                    raise ValueError("A2A service requires one nonstreaming message result")
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
                result = MessageToDict(reply.parts[0].data)
                received = True
            if not received:
                raise ValueError("A2A service completed without a result")
            return result
        finally:
            await client.close()
