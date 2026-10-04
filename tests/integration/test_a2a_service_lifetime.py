"""Official standard A2A SDK request/client lifetime without network or models."""

import asyncio

import httpx
import pytest
from a2a.server.agent_execution import AgentExecutor
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.routes import create_agent_card_routes, create_jsonrpc_routes
from a2a.server.tasks import InMemoryTaskStore
from a2a.types import AgentCapabilities, AgentCard, AgentInterface, AgentSkill, Message, Part, Role
from google.protobuf.json_format import MessageToDict
from google.protobuf.struct_pb2 import Value
from starlette.applications import Starlette

from collective_intelligence_overlay.adapters import a2a_service
from collective_intelligence_overlay.adapters.a2a import struct
from collective_intelligence_overlay.bindings import Target, fingerprint
from collective_intelligence_overlay.models import uid


@pytest.mark.parametrize("mode", ["data", "null", "send_failure", "multiple", "numeric_failure"])
async def test_standard_sdk_exchange_owns_request_and_client_until_return(monkeypatch, mode):
    endpoint = "http://127.0.0.1:1234/"
    card = AgentCard(
        name="standard-service",
        description="Finite standard-service lifetime regression",
        version="1",
        supported_interfaces=[
            AgentInterface(url=endpoint, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[AgentSkill(id="count", name="Count", description="Count", tags=["text"])],
    )
    calls = []

    class StandardService(AgentExecutor):
        async def execute(self, context, event_queue):
            calls.append(MessageToDict(context.message.parts[0].data))
            data = Value(null_value=0) if mode == "null" else struct({"count": 2})
            await event_queue.enqueue_event(
                Message(message_id=uid(), role=Role.ROLE_AGENT, parts=[Part(data=data)])
            )

        async def cancel(self, context, event_queue):
            raise ValueError("this fixture returns one immediate message")

    handler = DefaultRequestHandler(StandardService(), InMemoryTaskStore(), card)
    app = Starlette(routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/"))
    target = Target(
        kind="a2a",
        name="count",
        peer=card.name,
        endpoint=endpoint,
        interface_digest=fingerprint(MessageToDict(card)),
        implementation_identity="remote-unknown",
    )
    monkeypatch.setattr(
        a2a_service, "BoundedA2ATransport", lambda *args, **kwargs: httpx.ASGITransport(app=app)
    )
    create_client = a2a_service.create_client
    clients, owned_http, iterators, finalized, closed = [], [], [], [], []

    async def instrumented_create(card, client_config):
        client = await create_client(card, client_config)
        send_message, close = client.send_message, client.close
        clients.append(client)
        owned_http.append(client_config.httpx_client)

        async def observe_iterator(request):
            try:
                if mode == "send_failure":
                    raise RuntimeError("owned fixture failure after client construction")
                async for response in send_message(request):
                    yield response
                    if mode == "multiple":
                        yield response
            finally:
                finalized.append(True)

        def observed_send(request):
            iterator = observe_iterator(request)
            iterators.append(iterator)
            return iterator

        async def observe_close():
            await close()
            closed.append(True)

        monkeypatch.setattr(client, "send_message", observed_send)
        monkeypatch.setattr(client, "close", observe_close)
        return client

    monkeypatch.setattr(a2a_service, "create_client", instrumented_create)
    arguments = {"text": "one two"}
    if mode == "numeric_failure":
        arguments["unsafe_integer"] = 2**80 + 7
    try:
        if mode == "send_failure":
            with pytest.raises(RuntimeError, match="owned fixture failure"):
                await a2a_service.invoke(target, endpoint, arguments)
        elif mode == "multiple":
            with pytest.raises(ValueError, match="one nonstreaming message"):
                await a2a_service.invoke(target, endpoint, arguments)
        elif mode == "numeric_failure":
            with pytest.raises(ValueError, match="numeric values"):
                await a2a_service.invoke(target, endpoint, arguments)
        else:
            expected = None if mode == "null" else {"count": 2}
            assert await a2a_service.invoke(target, endpoint, arguments) == expected
        # These assertions occur before another event-loop turn or GC can hide
        # a retained request frame. Invalid input still owns its constructed client.
        assert closed == [True]
        assert len(owned_http) == 1 and owned_http[0].is_closed
        if mode in {"data", "null", "send_failure"}:
            assert finalized == [True]
        assert len(calls) == (0 if mode in {"send_failure", "numeric_failure"} else 1)
    finally:
        # Close the original failing fixture after assertions, never to make them pass.
        for iterator in iterators:
            await iterator.aclose()
        for client in clients:
            await client.close()
        closer = getattr(handler, "aclose", None)
        if closer is not None:
            await closer()
    await asyncio.sleep(0)
