import asyncio
import json
import sys

import httpx
import httpx2
import pytest
from agent_framework import (
    Agent,
    BaseChatClient,
    ChatResponse,
    Content,
    FunctionInvocationLayer,
    Message,
)
from jsonschema import ValidationError
from mcp import Client
from mcp.client.streamable_http import streamable_http_client

from collective_intelligence_overlay.adapters.maf import bound_tool
from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Registry,
    Target,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.demo import free_port
from collective_intelligence_overlay.models import Capability, Evidence, Revocation, Subject
from collective_intelligence_overlay.overlay import AdmissionDenied
from collective_intelligence_overlay.security import verify


async def transform(arguments):
    return {"total": str(sum(arguments["amounts"]))}


def setup_binding(overlay, identities, records, *, legacy=False):
    cap, evidence = records
    # Separate subject keeps the unchanged baseline fixture in the same real store.
    subject = Subject(id="application.sum", version="2", digest=callable_digest(transform))
    binding = Binding(
        id="application_sum",
        revision="1",
        issuer="producer",
        subject=subject,
        registrar="receiver",
        target=Target(
            kind="local",
            name="sum",
            interface_digest=callable_digest(transform),
            implementation_identity="installed",
        ),
        scope=cap.scope,
        input_schema={
            "type": "object",
            "required": ["amounts", "tenant"],
            "additionalProperties": False,
            "properties": {
                "amounts": {"type": "array", "maxItems": 100, "items": {"type": "integer"}},
                "tenant": {"type": "string"},
            },
        },
        output_schema={
            "type": "object",
            "required": ["total"],
            "properties": {"total": {"type": "string"}},
        },
        callers=("receiver",),
        effects="read-only",
        resources={"/tenant": ("tenant-a",)},
    )
    registry = Registry(overlay)
    registry.register_local(binding, transform, lambda args: bool(args["amounts"]))
    update = {"subject": subject}
    if not legacy:
        update.update(schema_version="2", binding_digest=binding.digest)
    candidate = Capability.model_validate({**cap.model_dump(), **update})
    checked = Evidence.model_validate({**evidence.model_dump(), **update, "id": "bound-check"})
    for record in (candidate, checked):
        overlay.store.put(identities[record.issuer].sign(record))
    context = ExecutionContext(caller="receiver", environment=cap.scope.environment)
    return registry, binding, context


async def test_local_binding_actual_execution_and_input_boundaries(overlay, identities, records):
    registry, binding, context = setup_binding(overlay, identities, records)
    args = {"amounts": [7, 11], "tenant": "tenant-a"}
    assert await registry.execute(binding.id, binding.digest, args, context) == {"total": "18"}
    cases = [
        (binding.id, "0" * 64, args, context, "binding changed"),
        ("unregistered", binding.digest, args, context, "unregistered"),
        (binding.id, binding.digest, {**args, "tenant": "tenant-b"}, context, "resource"),
        (
            binding.id,
            binding.digest,
            args,
            context.model_copy(update={"caller": "other"}),
            "caller",
        ),
        (
            binding.id,
            binding.digest,
            args,
            context.model_copy(update={"environment": {"reference": "2"}}),
            "environment",
        ),
    ]
    for name, change, arguments, authority, reason in cases:
        with pytest.raises(ValueError, match=reason):
            await registry.execute(name, change, arguments, authority)
    with pytest.raises(ValidationError):
        await registry.execute(binding.id, binding.digest, {**args, "amounts": ["7"]}, context)
    with pytest.raises(AdmissionDenied):
        await registry.execute(binding.id, binding.digest, {**args, "amounts": []}, context)


async def test_legacy_evidence_cannot_invent_a_checked_binding(overlay, identities, records):
    registry, binding, context = setup_binding(overlay, identities, records, legacy=True)
    with pytest.raises(AdmissionDenied) as caught:
        await registry.execute(
            binding.id, binding.digest, {"amounts": [1], "tenant": "tenant-a"}, context
        )
    assert caught.value.decision.outcome == "REQUALIFY"
    assert "binding_evidence_required" in caught.value.decision.reasons


async def test_issuer_and_binding_change_cannot_reuse_accept(overlay, identities, records):
    registry, binding, context = setup_binding(overlay, identities, records)
    args = {"amounts": [1], "tenant": "tenant-a"}
    prepared = registry.prepare(binding.id, binding.digest, args, context)
    bad = prepared.request.model_copy(update={"capability_issuer": "other"})
    assert (await overlay.qualify(bad)).outcome == "UNKNOWN"
    newer = binding.model_copy(update={"revision": "2"})
    registry.register_local(newer, transform, lambda _: True)
    with pytest.raises(ValueError, match="binding changed"):
        await registry.execute(binding.id, binding.digest, args, context)
    with pytest.raises(AdmissionDenied):
        await registry.execute(binding.id, newer.digest, args, context)


async def test_registry_owns_nested_manifest_and_arguments(overlay, identities, records):
    registry, binding, context = setup_binding(overlay, identities, records)
    old = binding.digest
    binding.resources["/tenant"] = ("tenant-b",)
    inspected = registry.inspect(binding.id)
    inspected.resources["/tenant"] = ("tenant-b",)
    with pytest.raises(ValueError, match="resource"):
        await registry.execute(binding.id, old, {"amounts": [1], "tenant": "tenant-b"}, context)
    assert await registry.execute(binding.id, old, {"amounts": [1], "tenant": "tenant-a"}, context)


class BindingClient(FunctionInvocationLayer, BaseChatClient):
    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        if any(message.role == "tool" for message in messages):
            return ChatResponse(messages=Message("assistant", ["done"]))
        return ChatResponse(
            messages=Message(
                "assistant",
                [
                    Content.from_function_call(
                        call_id="bound-call",
                        name="application_sum",
                        arguments={"arguments": {"amounts": [2, 3], "tenant": "tenant-a"}},
                    )
                ],
            )
        )


async def test_real_maf_tool_routes_through_registered_actuator(overlay, identities, records):
    registry, binding, context = setup_binding(overlay, identities, records)
    agent = Agent(client=BindingClient(), tools=[bound_tool(registry, binding.id, context)])
    assert (await agent.run("run the configured transformation")).text == "done"


async def test_registered_mcp_contract_and_actual_arguments(overlay, identities, records):
    port = free_port()
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "collective_intelligence_overlay.reference_mcp",
        "--port",
        str(port),
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    endpoint = f"http://127.0.0.1:{port}/mcp"
    try:
        async with httpx.AsyncClient() as http:
            for _ in range(100):
                try:
                    await http.get(endpoint)
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.05)
            else:
                raise AssertionError("MCP service did not become ready")
        async with httpx2.AsyncClient() as http:
            async with Client(streamable_http_client(endpoint, http_client=http)) as client:
                tool = next(t for t in (await client.list_tools()).tools if t.name == "csv_sum")
        cap, evidence = records
        binding = Binding(
            id="remote_sum",
            revision="1",
            issuer="producer",
            registrar="receiver",
            subject=Subject(
                id="mcp.csv-sum", version="1", digest=fingerprint({"service": endpoint})
            ),
            target=Target(
                kind="mcp",
                name="csv_sum",
                endpoint=endpoint,
                interface_digest=fingerprint(
                    {"name": tool.name, "input": tool.input_schema, "output": tool.output_schema}
                ),
                implementation_identity="remote-unknown",
            ),
            scope=cap.scope,
            input_schema=tool.input_schema,
            output_schema=tool.output_schema,
            callers=("receiver",),
            effects="read-only",
        )
        candidate = Capability.model_validate(
            {
                **cap.model_dump(),
                "subject": binding.subject,
                "schema_version": "2",
                "binding_digest": binding.digest,
            }
        )
        checked = Evidence.model_validate(
            {
                **evidence.model_dump(),
                "subject": binding.subject,
                "schema_version": "2",
                "binding_digest": binding.digest,
                "id": "remote-check",
            }
        )
        for record in (candidate, checked):
            overlay.store.put(identities[record.issuer].sign(record))
        registry = Registry(overlay)
        registry.register_mcp(
            binding, lambda args: args["source"].startswith("category,amount\n"), local=True
        )
        context = ExecutionContext(caller="receiver", environment=cap.scope.environment)
        arguments = {"source": "category,amount\na,7.00\nb,5.00\n"}
        assert await registry.execute(binding.id, binding.digest, arguments, context) == {
            "rows": 2,
            "total": "12.00",
        }
        changed = binding.model_copy(
            update={
                "revision": "2",
                "target": binding.target.model_copy(update={"interface_digest": "0" * 64}),
            }
        )
        # Exercise the real SDK contract observation separately from admission.
        from collective_intelligence_overlay.adapters.mcp import invoke_registered

        with pytest.RaisesGroup(
            pytest.RaisesGroup(pytest.RaisesExc(ValueError, match="interface changed"))
        ):
            await invoke_registered(endpoint, changed.target.name, "0" * 64, arguments)
        with pytest.raises(ValidationError):
            await registry.execute(binding.id, binding.digest, {"source": 42}, context)
    finally:
        if process.returncode is None:
            process.terminate()
        await asyncio.wait_for(process.wait(), 10)


def test_legacy_signed_payload_preserved_and_v2_requires_its_media_type(
    identities, principals, records
):
    import base64

    from securesystemslib.dsse import Envelope

    from collective_intelligence_overlay.security import PAYLOAD_TYPE, PAYLOAD_TYPE_V2

    legacy = identities["producer"].sign(records[0])
    original_bytes = base64.b64decode(legacy["payload"])
    assert "binding_digest" not in json.loads(original_bytes)
    verify(legacy, principals)
    assert base64.b64decode(legacy["payload"]) == original_bytes
    mismatch = Envelope(original_bytes, PAYLOAD_TYPE_V2, {})
    mismatch.sign(identities["producer"].signer)
    with pytest.raises(ValueError, match="media type"):
        verify(mismatch.to_dict(), principals)
    assert legacy["payloadType"] == PAYLOAD_TYPE


async def test_operator_probe_is_separate_from_reuse_and_still_honors_withdrawal(
    overlay, identities, records
):
    registry, original, context = setup_binding(overlay, identities, records)
    binding = Binding.model_validate(
        {
            **original.model_dump(),
            "id": "probe",
            "subject": {**original.subject.model_dump(), "id": "probe-target"},
            "verification_callers": ["receiver"],
        }
    )
    registry.register_local(binding, transform, lambda args: bool(args["amounts"]))
    candidate = Capability.model_validate(
        {
            **records[0].model_dump(),
            "schema_version": "2",
            "subject": binding.subject,
            "binding_digest": binding.digest,
        }
    )
    overlay.store.put(identities["producer"].sign(candidate))
    arguments = {"amounts": [2, 4], "tenant": "tenant-a"}
    with pytest.raises(AdmissionDenied):
        await registry.execute(binding.id, binding.digest, arguments, context)
    probe = context.model_copy(update={"purpose": "verification"})
    ungranted = registry.prepare(binding.id, binding.digest, arguments, probe).request
    assert (await overlay.qualify(ungranted)).outcome == "REJECT"
    assert await registry.execute(binding.id, binding.digest, arguments, probe) == {"total": "6"}
    assert not any(e.subject == candidate.subject for e in overlay.store.evidence())
    with pytest.raises(AdmissionDenied):
        await registry.execute(binding.id, binding.digest, arguments, context)
    overlay.store.put(
        identities["producer"].sign(
            Revocation(issuer="producer", subject=candidate.subject, reason="withdrawn")
        )
    )
    with pytest.raises(AdmissionDenied):
        await registry.execute(binding.id, binding.digest, arguments, probe)
