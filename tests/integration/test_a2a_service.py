import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
import uvicorn
from a2a.server.agent_execution import AgentExecutor
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
    Task,
    TaskState,
    TaskStatus,
)
from google.protobuf.json_format import MessageToDict
from starlette.applications import Starlette

from collective_intelligence_overlay.adapters.a2a import struct
from collective_intelligence_overlay.adapters.a2a_service import invoke
from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Registry,
    Target,
    fingerprint,
)
from collective_intelligence_overlay.demo import free_port
from collective_intelligence_overlay.invocations import Executor, Reservation
from collective_intelligence_overlay.models import Capability, Evidence, Scope, Subject, now, uid


class StandardService(AgentExecutor):
    """Ordinary SDK server without any overlay imports in its execution logic."""

    def __init__(self):
        self.calls = []
        self.mode = "data"

    async def execute(self, context, event_queue):
        assert not context.message.extensions
        arguments = MessageToDict(context.message.parts[0].data)
        self.calls.append(arguments)
        if self.mode == "task":
            await event_queue.enqueue_event(
                Task(
                    id=context.task_id,
                    context_id=context.context_id,
                    status=TaskStatus(state=TaskState.TASK_STATE_WORKING),
                )
            )
            return
        result = {"count": len(arguments["text"].split())}
        part = Part(data=struct(result))
        if self.mode == "text":
            part = Part(text="unstructured result")
        if self.mode == "large":
            part = Part(data=struct({"count": 1, "text": "x" * 300000}))
        await event_queue.enqueue_event(
            Message(message_id=uid(), role=Role.ROLE_AGENT, parts=[part])
        )

    async def cancel(self, context, event_queue):
        raise ValueError("this example exposes immediate messages only")


@pytest.fixture
async def service():
    port = free_port()
    endpoint = f"http://127.0.0.1:{port}/"
    card = AgentCard(
        name="standard-service",
        description="Document count service without overlay",
        version="1",
        supported_interfaces=[
            AgentInterface(url=endpoint, protocol_binding="JSONRPC", protocol_version="1.0")
        ],
        capabilities=AgentCapabilities(),
        default_input_modes=["application/json"],
        default_output_modes=["application/json"],
        skills=[AgentSkill(id="count", name="Count", description="Count words", tags=["text"])],
    )
    operation = StandardService()
    handler = DefaultRequestHandler(operation, InMemoryTaskStore(), card)
    app = Starlette(routes=create_agent_card_routes(card) + create_jsonrpc_routes(handler, "/"))
    server = uvicorn.Server(
        uvicorn.Config(app, host="127.0.0.1", port=port, log_level="critical", access_log=False)
    )
    serving = asyncio.create_task(server.serve())
    try:
        async with asyncio.timeout(10):
            while not server.started:
                if serving.done():
                    await serving
                await asyncio.sleep(0.02)
        yield endpoint, card, operation
    finally:
        server.should_exit = True
        await asyncio.wait_for(serving, 10)


def installed_binding(endpoint, card):
    return Binding(
        id="standard-count",
        revision="1",
        issuer="receiver",
        registrar="receiver",
        subject=Subject(id="standard-count", version="1", digest=fingerprint(MessageToDict(card))),
        scope=Scope(
            task="document-count",
            input_contract="text.v1",
            output_contract="count.v1",
            environment={"application": "1"},
        ),
        target=Target(
            kind="a2a",
            name="count",
            peer=card.name,
            endpoint=endpoint,
            interface_digest=fingerprint(MessageToDict(card)),
            implementation_identity="remote-unknown",
        ),
        input_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["text"],
            "properties": {"text": {"type": "string", "maxLength": 1024}},
        },
        output_schema={
            "type": "object",
            "additionalProperties": False,
            "required": ["count"],
            "properties": {"count": {"type": "integer", "minimum": 0}},
        },
        callers=("receiver",),
        effects="read-only",
    )


async def test_standard_service_requires_external_check_and_preserves_unknown(
    service, overlay, identities
):
    endpoint, card, operation = service
    binding = installed_binding(endpoint, card)
    registry = Registry(overlay)
    registry.register_a2a_service(binding, lambda args: bool(args["text"].strip()), local=True)
    overlay.store.set_budget("work", Decimal(20))
    runner = Executor(registry, identities["receiver"], Reservation())
    context = ExecutionContext(caller="receiver", environment=binding.scope.environment)
    candidate = Capability(
        schema_version="2",
        binding_digest=binding.digest,
        issuer="receiver",
        subject=binding.subject,
        scope=binding.scope,
        entrypoint=binding.id,
        claim="word-count",
        license="Apache-2.0",
        provenance="operator-installed service declaration; remote code unknown",
        classification="imported",
        expires_at=now() + timedelta(hours=1),
    )
    overlay.store.put(identities["receiver"].sign(candidate))
    denied = await runner.invoke(
        "before-check", binding.id, binding.digest, {"text": "input"}, context
    )
    assert denied["state"] == "unknown"
    assert operation.calls == []
    # Explicit operator verification probes the real service; its checker decides PASS.
    observed = await invoke(binding.target, endpoint, {"text": "separate checker input"})
    assert observed == {"count": 3}
    evidence = Evidence(
        schema_version="2",
        binding_digest=binding.digest,
        issuer="verifier",
        subject=binding.subject,
        scope=binding.scope,
        claim=candidate.claim,
        receivers=("receiver",),
        verdict="PASS",
        method="report-check",
        verifier_version="1",
        artifact_digest=fingerprint(observed),
        expires_at=now() + timedelta(hours=1),
    )
    overlay.store.put(identities["verifier"].sign(evidence))
    first = await runner.invoke("reuse", binding.id, binding.digest, {"text": "new work"}, context)
    assert first["state"] == "completed" and first["result"] == {"count": 2}
    assert (
        await runner.invoke("reuse", binding.id, binding.digest, {"text": "new work"}, context)
        == first
    )
    assert len(operation.calls) == 2
    for mode in ("text", "large", "task"):
        operation.mode = mode
        failed = await runner.invoke(
            mode, binding.id, binding.digest, {"text": "new work"}, context
        )
        assert failed["state"] == "unknown" and failed["result"] is None
        count = len(operation.calls)
        assert (
            await runner.invoke(mode, binding.id, binding.digest, {"text": "new work"}, context)
            == failed
        )
        assert len(operation.calls) == count
    assert len([e for e in overlay.store.evidence() if e.subject == binding.subject]) == 1


async def test_standard_card_changes_and_required_extensions_block_dispatch(service):
    endpoint, card, operation = service
    binding = installed_binding(endpoint, card)
    with pytest.raises(ValueError, match="numeric values"):
        await invoke(binding.target, endpoint, {"text": "data", "unsafe_integer": 2**80 + 7})
    bad_pin = binding.target.model_copy(update={"interface_digest": fingerprint("different")})
    with pytest.raises(ValueError, match="card changed"):
        await invoke(bad_pin, endpoint, {"text": "data"})
    card.supported_interfaces[0].url = "https://unconfigured.invalid/"
    redirected = binding.target.model_copy(
        update={"interface_digest": fingerprint(MessageToDict(card))}
    )
    with pytest.raises(ValueError, match="unsupported"):
        await invoke(redirected, endpoint, {"text": "data"})
    card.supported_interfaces[0].url = endpoint
    card.capabilities.extensions.append(
        AgentExtension(uri="https://example.org/required", required=True)
    )
    current = binding.target.model_copy(
        update={"interface_digest": fingerprint(MessageToDict(card))}
    )
    with pytest.raises(ValueError, match="unsupported"):
        await invoke(current, endpoint, {"text": "data"})
    assert operation.calls == []
