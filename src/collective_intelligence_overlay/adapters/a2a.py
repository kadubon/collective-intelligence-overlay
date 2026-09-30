"""A2A 1.x official protobuf types and HTTP SDK. Overlay data is an extension."""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
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
from google.protobuf.json_format import MessageToDict, ParseDict, ParseError
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
from starlette.types import Lifespan

from .. import __version__
from ..blocking import run_blocking
from ..config import Config
from ..models import now, uid
from ..security import MAX_RECORD_BYTES, Identity, allowed_url
from .http_limits import BodyLimit, InvalidPeerResponse, RequestCapacity

EXTENSION = "https://github.com/kadubon/collective-intelligence-overlay/extensions/v2"
Handler = Callable[[str, dict[str, Any]], Awaitable[dict[str, Any]]]


def struct(value: dict[str, Any]) -> Value:
    result = Struct()
    result.update(value)
    return Value(struct_value=result)


def extension_data(value: dict[str, Any]) -> Value:
    # Protobuf Struct represents numbers as double. Preserve business JSON exactly,
    # including large integers and manifest digests, inside the v2 extension part.
    return struct({"application_json": json.dumps(value, allow_nan=False, separators=(",", ":"))})


def read_extension_data(value: Value) -> dict[str, Any]:
    wrapper = MessageToDict(value)
    if not isinstance(wrapper, dict) or set(wrapper) != {"application_json"}:
        raise InvalidPeerResponse("v2 extension requires an exact application JSON payload")
    encoded = wrapper["application_json"]
    if not isinstance(encoded, str) or len(encoded.encode()) > MAX_RECORD_BYTES:
        raise InvalidPeerResponse("invalid or oversized extension payload")
    try:
        result = json.loads(encoded)
    except (ValueError, RecursionError) as exc:
        raise InvalidPeerResponse("invalid application JSON payload") from exc
    if not isinstance(result, dict):
        raise InvalidPeerResponse("extension payload must be an object")
    return result


def validate_peer_response(method: str, content: bytes) -> None:
    """Reject malformed wire data at a pure parsing boundary using SDK types.

    This contains no network operation, host configuration or database access;
    parser failures cannot turn a local execution/storage fault into rejection.
    """
    from a2a.client.card_resolver import parse_agent_card
    from a2a.types import SendMessageResponse
    from jsonrpc.jsonrpc2 import JSONRPC20Response  # type: ignore[import-untyped]

    try:
        data = json.loads(content)
        if not isinstance(data, dict):
            raise ValueError("response must be an object")
        if method == "GET":
            parse_agent_card(data)
        else:
            response = JSONRPC20Response(**data)
            if not response.error:
                ParseDict(response.result, SendMessageResponse())
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError, ParseError) as exc:
        raise InvalidPeerResponse("invalid A2A service response structure") from exc


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
            if (
                entry.keyid in entry.compromised_keyids
                or jwt.get_unverified_header(token).get("kid", entry.keyid) != entry.keyid
            ):
                raise AuthenticationError("current uncompromised authentication key required")
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
    def __init__(self, handler: Handler, limit: int, run_seconds: int = 120) -> None:
        self.handler = handler
        self.semaphore = asyncio.Semaphore(limit)
        self.run_seconds = min(run_seconds, 300)

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
        data = read_extension_data(message.parts[0].data)
        seconds = self.run_seconds + 5 if data.get("operation") == "run" else 30
        async with asyncio.timeout(seconds):
            async with self.semaphore:
                result = await self.handler(principal.user_name, data)
        if len(json.dumps(result).encode()) > MAX_RECORD_BYTES:
            raise ValueError("overlay response too large")
        response = Message(
            message_id=uid(),
            role=Role.ROLE_AGENT,
            parts=[Part(data=extension_data(result))],
            extensions=[EXTENSION],
        )
        await event_queue.enqueue_event(response)

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # The SDK cancels the running execute coroutine before calling this hook.
        await event_queue.enqueue_event(
            Message(
                message_id=uid(),
                role=Role.ROLE_AGENT,
                parts=[Part(data=extension_data({"outcome": "UNKNOWN", "reason": "cancelled"}))],
                extensions=[EXTENSION],
            )
        )


def application(
    config: Config, handler: Handler, *, lifespan: Lifespan[Starlette] | None = None
) -> Starlette:
    card = AgentCard(
        name=config.owner,
        description="Local evidence admission peer",
        version=__version__,
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
        ExtensionExecutor(handler, config.max_concurrency, config.max_seconds),
        InMemoryTaskStore(),
        card,
    )
    routes = create_agent_card_routes(card) + create_jsonrpc_routes(request_handler, "/")
    return Starlette(
        routes=routes,
        lifespan=lifespan,
        middleware=[
            Middleware(AuthenticationMiddleware, backend=PeerAuthentication(config)),
            Middleware(
                RequestCapacity,
                owner_limit=config.max_owner_requests,
                caller_limit=config.max_caller_requests,
            ),
            Middleware(BodyLimit),
        ],
    )


async def send(
    config: Config, identity: Identity, peer_name: str, data: dict[str, Any]
) -> dict[str, Any]:
    """Official SDK exchange; process-local logging is not a signed cost receipt."""
    import logging

    started = time.perf_counter()
    returned = False
    try:
        result = await _send(config, identity, peer_name, data)
        returned = True
        return result
    finally:
        logging.getLogger(__name__).info(
            json.dumps(
                {
                    "owner": config.owner,
                    "reason": "A2A_EXCHANGE_FINISHED" if returned else "A2A_EXCHANGE_FAILED",
                    "elapsed_seconds": time.perf_counter() - started,
                }
            )
        )


async def _send(
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
        headers={"kid": identity.signer.public_key.keyid},
    )
    if len(json.dumps(data).encode()) > MAX_RECORD_BYTES:
        raise ValueError("message too large")
    from .http_limits import BoundedA2ATransport

    async with httpx.AsyncClient(
        transport=BoundedA2ATransport(
            url,
            response_validator=validate_peer_response,
            tls_context=config.tls_context(),
            seconds=min(config.max_seconds, 300) + 5 if data.get("operation") == "run" else 30,
            readonly_post=data.get("operation")
            in {
                "status",
                "invocation",
                "remote_calls",
                "goals",
                "discover",
                "metrics",
                "operational_metrics",
                "recovery_state",
            },
        ),
        timeout=min(config.max_seconds, 300) + 5 if data.get("operation") == "run" else 30,
        follow_redirects=False,
        trust_env=False,
        headers={"Authorization": f"Bearer {token}", "A2A-Extensions": EXTENSION},
    ) as http:
        # Resolve the card from the configured URL. Reject endpoint substitution.
        from a2a.client import A2ACardResolver

        card = await A2ACardResolver(http, url).get_agent_card()
        if card.name != peer_name or any(i.url != url for i in card.supported_interfaces):
            raise InvalidPeerResponse("card identity or endpoint mismatch")
        if any(e.required and e.uri != EXTENSION for e in card.capabilities.extensions):
            raise InvalidPeerResponse("unsupported required extension")
        if not any(e.uri == EXTENSION for e in card.capabilities.extensions):
            raise InvalidPeerResponse("overlay extension absent")
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
                message_id=uid(),
                role=Role.ROLE_USER,
                parts=[Part(data=extension_data(data))],
                extensions=[EXTENSION],
            )
        )
        async for response in client.send_message(request):
            if response.HasField("message"):
                reply = response.message
                if list(reply.extensions) != [EXTENSION] or len(reply.parts) != 1:
                    raise InvalidPeerResponse("invalid extension response")
                return read_extension_data(reply.parts[0].data)
        raise InvalidPeerResponse("A2A completed without an overlay result")


async def synchronize(
    config: Config,
    identity: Identity,
    store: Any,
    source: str,
    *,
    filter_data: dict[str, Any] | None = None,
    max_pages: int = 16,
    page_size: int = 32,
    restart: bool = False,
) -> dict[str, Any]:
    """One bounded synchronization step; continuation survives process restart."""
    from ..synchronization import FeedFilter, FeedPage, Receiver, ResnapshotRequired

    if source == store.owner or source not in {peer.identity for peer in config.peers}:
        raise ValueError("synchronization requires a configured remote source")
    if not 1 <= max_pages <= 128:
        raise ValueError("invalid synchronization page budget")
    filter = FeedFilter.model_validate(filter_data or {})
    receiver = Receiver(store)
    if restart:
        await run_blocking(receiver.restart, source, filter)
    await run_blocking(receiver.begin, source, filter)
    received = 0
    async with asyncio.timeout(config.max_seconds):
        for index in range(max_pages):
            state = await run_blocking(receiver.checkpoint, source, filter)
            assert state is not None
            started = time.perf_counter()
            response = await send(
                config,
                identity,
                source,
                {
                    "operation": "discover",
                    "filter": filter.model_dump(mode="json"),
                    "cursor": state["cursor"],
                    "since": state["through"],
                    "generation": state["generation"],
                    "limit": page_size,
                },
            )
            if response.get("error") == "RESNAPSHOT_REQUIRED":
                raise ResnapshotRequired("source requires explicit snapshot restart")
            page = FeedPage.model_validate(response)
            inserted = await run_blocking(
                receiver.apply,
                source,
                filter,
                page,
                identity=identity,
                network_seconds=Decimal(str(round(time.perf_counter() - started, 9))),
            )
            if inserted:
                received += len(page.records)
            state = await run_blocking(receiver.checkpoint, source, filter)
            assert state is not None
            if state["complete"]:
                return {
                    "received": received,
                    "complete": True,
                    "pages": index + 1,
                    "cursor": None,
                    "through": state["through"],
                    "anchor": state["anchor"].isoformat(),
                }
    assert state is not None
    return {
        "received": received,
        "complete": False,
        "pages": max_pages,
        "cursor": state["cursor"],
        "through": state["through"],
        "anchor": None,
    }
