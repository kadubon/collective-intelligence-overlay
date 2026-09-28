"""A2A 1.x official protobuf types and HTTP SDK. Overlay data is an extension."""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any

import httpx
import jwt
from a2a.client import ClientConfig, create_client
from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    AgentExtension,
    AgentInterface,
    AgentSkill,
    Message,
    Part,
    Role,
    SendMessageRequest,
)
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Struct, Value
from starlette.applications import Starlette
from starlette.authentication import (
    AuthCredentials,
    AuthenticationBackend,
    AuthenticationError,
    SimpleUser,
)
from starlette.middleware import Middleware
from starlette.middleware.authentication import AuthenticationMiddleware
from starlette.requests import HTTPConnection

from ..config import Config
from ..models import now, uid
from ..security import MAX_RECORD_BYTES, Identity, allowed_url
from .http_limits import BodyLimit

EXTENSION = "https://github.com/kadubon/collective-intelligence-overlay/extensions/v1"
Handler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def struct(value: dict[str, Any]) -> Value:
    result = Struct()
    result.update(value)
    return Value(struct_value=result)


class PeerAuthentication(AuthenticationBackend):
    def __init__(self, config: Config) -> None:
        self.config = config

    async def authenticate(self, conn: HTTPConnection) -> tuple[AuthCredentials, SimpleUser]:
        header = conn.headers.get("authorization", "")
        if not header.startswith("Bearer ") or len(header) > 8192:
            raise AuthenticationError("authentication required")
        token = header[7:]
        try:
            untrusted = jwt.decode(token, options={"verify_signature": False})
            issuer = untrusted.get("iss")
            if not isinstance(issuer, str):
                raise AuthenticationError("missing issuer")
            entry = self.config.identities.get(issuer)
            if entry is None:
                raise AuthenticationError("unknown issuer")
            key = Ed25519PublicKey.from_public_bytes(bytes.fromhex(entry.key["keyval"]["public"]))
            claims = jwt.decode(
                token,
                key,
                algorithms=["EdDSA"],
                audience=self.config.url,
                issuer=issuer,
                options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            )
            if claims["sub"] != issuer or claims["exp"] - claims["iat"] > 120:
                raise AuthenticationError("invalid token scope")
            return AuthCredentials(["authenticated"]), SimpleUser(issuer)
        except (jwt.PyJWTError, ValueError, KeyError, TypeError) as exc:
            raise AuthenticationError("invalid credentials") from exc


class ExtensionExecutor(AgentExecutor):
    def __init__(self, handler: Handler, limit: int) -> None:
        self.handler = handler
        self.semaphore = asyncio.Semaphore(limit)

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        message = context.message
        if (
            message is None
            or list(message.extensions) != [EXTENSION]
            or len(message.parts) != 1
            or message.ByteSize() > MAX_RECORD_BYTES
        ):
            raise ValueError("required extension or bounded data part missing")
        principal = context.call_context.user
        if not principal.is_authenticated:
            raise ValueError("unauthenticated peer")
        data = MessageToDict(message.parts[0].data)
        async with asyncio.timeout(30):
            async with self.semaphore:
                result = await self.handler(principal.user_name, data)
        response = Message(
            message_id=uid(),
            role=Role.ROLE_AGENT,
            parts=[Part(data=struct(result))],
            extensions=[EXTENSION],
        )
        await event_queue.enqueue_event(response)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # The SDK cancels the running execute coroutine before calling this hook.
        await event_queue.enqueue_event(
            Message(
                message_id=uid(),
                role=Role.ROLE_AGENT,
                parts=[Part(data=struct({"outcome": "UNKNOWN", "reason": "cancelled"}))],
                extensions=[EXTENSION],
            )
        )


def application(config: Config, handler: Handler) -> Starlette:
    card = AgentCard(
        name=config.owner,
        description="Local evidence admission peer",
        version="0.1.0",
        supported_interfaces=[
            AgentInterface(url=config.url, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(
            extensions=[
                AgentExtension(
                    uri=EXTENSION, required=True, description="Evidence shared; admission local"
                )
            ]
        ),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[
            AgentSkill(
                id="evidence",
                name="Evidence exchange",
                description="Signed candidates, local decisions",
                tags=["evidence"],
            )
        ],
    )
    request_handler = DefaultRequestHandler(
        ExtensionExecutor(handler, config.max_concurrency), InMemoryTaskStore(), card
    )
    routes = create_agent_card_routes(card) + create_jsonrpc_routes(request_handler, "/")
    return Starlette(
        routes=routes,
        middleware=[
            Middleware(BodyLimit),
            Middleware(AuthenticationMiddleware, backend=PeerAuthentication(config)),
        ],
    )


async def send(
    config: Config, identity: Identity, peer_name: str, data: dict[str, Any]
) -> dict[str, Any]:
    peer = next((p for p in config.peers if p.identity == peer_name), None)
    if peer is None:
        raise ValueError("unconfigured peer")
    url = allowed_url(
        peer.url, frozenset(p.url for p in config.peers), local=config.local_development
    )
    timestamp = now()
    token = jwt.encode(
        {
            "iss": identity.name,
            "sub": identity.name,
            "aud": url,
            "iat": timestamp,
            "exp": timestamp + timedelta(seconds=60),
        },
        identity.signer.private_bytes,
        algorithm="EdDSA",
    )
    if len(json.dumps(data).encode()) > MAX_RECORD_BYTES:
        raise ValueError("message too large")
    async with httpx.AsyncClient(
        timeout=30,
        follow_redirects=False,
        trust_env=False,
        headers={"Authorization": f"Bearer {token}", "A2A-Extensions": EXTENSION},
    ) as http:
        # Resolve the card from the configured URL. Reject endpoint substitution.
        from a2a.client import A2ACardResolver

        card = await A2ACardResolver(http, url).get_agent_card()
        if card.name != peer_name or any(i.url != url for i in card.supported_interfaces):
            raise ValueError("card identity or endpoint mismatch")
        if any(e.required and e.uri != EXTENSION for e in card.capabilities.extensions):
            raise ValueError("unsupported required extension")
        if not any(e.uri == EXTENSION for e in card.capabilities.extensions):
            raise ValueError("overlay extension absent")
        client = await create_client(card, ClientConfig(streaming=False, httpx_client=http))
        request = SendMessageRequest(
            message=Message(
                message_id=uid(),
                role=Role.ROLE_USER,
                parts=[Part(data=struct(data))],
                extensions=[EXTENSION],
            )
        )
        async for response in client.send_message(request):
            if response.HasField("message"):
                reply = response.message
                if list(reply.extensions) != [EXTENSION] or len(reply.parts) != 1:
                    raise ValueError("invalid extension response")
                return MessageToDict(reply.parts[0].data)
        raise ValueError("A2A completed without an overlay result")
