import asyncio
import os
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
import pytest
import uvicorn

from collective_intelligence_overlay.adapters.a2a import application, send
from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Registry,
    Target,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.demo import initialize
from collective_intelligence_overlay.invocations import Executor, Reservation
from collective_intelligence_overlay.models import Capability, Evidence, Scope, Subject, now
from collective_intelligence_overlay.peer import PeerService
from collective_intelligence_overlay.synchronization import Feed, FeedFilter, Receiver


def candidate(binding):
    return Capability(
        schema_version="2",
        binding_digest=binding.digest,
        issuer=binding.issuer,
        subject=binding.subject,
        scope=binding.scope,
        entrypoint=binding.id,
        claim="bounded-double",
        license="Apache-2.0",
        provenance="installed test application",
        classification="declared-new",
        expires_at=now() + timedelta(hours=1),
    )


def evidence(binding):
    return Evidence(
        schema_version="2",
        binding_digest=binding.digest,
        issuer="verifier",
        subject=binding.subject,
        scope=binding.scope,
        claim="bounded-double",
        receivers=(binding.registrar,),
        verdict="PASS",
        method="reference-check",
        verifier_version="1",
        artifact_digest=fingerprint({"input": 3, "expected": 6}),
        expires_at=now() + timedelta(hours=1),
    )


@pytest.mark.parametrize("nested", [False, True])
async def test_a2a_provider_and_consumer_each_enforce_binding_and_persist_result(
    tmp_path, policy, nested
):
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("real PostgreSQL required")
    configs = initialize(tmp_path / "remote", url, policy.binary)
    scope = Scope(
        task="double",
        input_contract="integer.v1",
        output_contract="integer.v1",
        environment={"application": "1"},
    )
    config = configs["producer"].model_copy(update={"execution_environment": scope.environment})
    calls = []

    async def double(arguments):
        calls.append(arguments["value"])
        return arguments["value"] * 2

    provider_binding = Binding(
        id="double",
        revision="1",
        issuer="producer",
        registrar="producer",
        subject=Subject(id="application.double", version="1", digest=callable_digest(double)),
        scope=scope,
        target=Target(
            kind="local",
            name="double",
            interface_digest=callable_digest(double),
            implementation_identity="installed",
        ),
        input_schema={
            "type": "object",
            "required": ["value"],
            "additionalProperties": False,
            "properties": {"value": {"type": "integer", "minimum": -100, "maximum": 100}},
        },
        output_schema={"type": "integer"},
        callers=("receiver",),
        effects="read-only",
    )
    service = PeerService(
        config, lambda registry: registry.register_local(provider_binding, double, lambda _: True)
    )
    verifier_identity, verifier_overlay = configs["verifier"].runtime()
    consumer_identity, consumer_overlay = configs["receiver"].runtime()
    server = uvicorn.Server(
        uvicorn.Config(
            application(config, service.handle),
            host="127.0.0.1",
            port=urlsplit(config.url).port,
            log_level="critical",
            access_log=False,
        )
    )
    serving = None
    try:
        assert await double({"value": 3}) == 6
        calls.clear()
        service.overlay.store.put(service.identity.sign(candidate(provider_binding)))
        verifier_overlay.store.put(verifier_identity.sign(evidence(provider_binding)))
        Receiver(service.overlay.store).apply(
            "verifier",
            FeedFilter(),
            Feed(verifier_overlay.store, verifier_identity).page("producer", FeedFilter()),
        )
        serving = asyncio.create_task(server.serve())
        async with httpx.AsyncClient() as http:
            for _ in range(100):
                try:
                    await http.get(config.url)
                    break
                except httpx.ConnectError:
                    await asyncio.sleep(0.05)
        proxy = provider_binding.model_copy(
            update={
                "id": "remote-double",
                "issuer": "receiver",
                "registrar": "receiver",
                "subject": Subject(
                    id="remote.double", version="1", digest=fingerprint({"service": config.url})
                ),
                "target": Target(
                    kind="a2a",
                    name="double",
                    peer="producer",
                    endpoint=config.url,
                    interface_digest=provider_binding.digest,
                    implementation_identity="remote-unknown",
                ),
            }
        )
        consumer_overlay.store.put(consumer_identity.sign(candidate(proxy)))
        verifier_overlay.store.put(verifier_identity.sign(evidence(proxy)))
        Receiver(consumer_overlay.store).apply(
            "verifier",
            FeedFilter(),
            Feed(verifier_overlay.store, verifier_identity).page("receiver", FeedFilter()),
        )
        registry = Registry(consumer_overlay)
        registry.register_a2a(proxy, lambda _: True, configs["receiver"], consumer_identity)
        executor = Executor(registry, consumer_identity, Reservation())
        context = ExecutionContext(caller="receiver", environment=scope.environment)
        if nested:

            async def twice(arguments):
                first = await registry.execute(
                    proxy.id, proxy.digest, arguments, context, call_id="first"
                )
                second = await registry.execute(
                    proxy.id, proxy.digest, arguments, context, call_id="second"
                )
                return [first, second]

            parent = proxy.model_copy(
                update={
                    "id": "two-logical-calls",
                    "subject": Subject(
                        id="two-logical-calls", version="1", digest=callable_digest(twice)
                    ),
                    "target": Target(
                        kind="local",
                        name="twice",
                        interface_digest=callable_digest(twice),
                        implementation_identity="installed",
                    ),
                    "output_schema": {"type": "array", "items": {"type": "integer"}},
                    "components": (proxy.digest,),
                }
            )
            registry.register_local(parent, twice, lambda _: True)
            parent_candidate = candidate(parent).model_copy(
                update={"dependencies": (proxy.subject,), "dependency_issuers": ("receiver",)}
            )
            consumer_overlay.store.put(consumer_identity.sign(parent_candidate))
            verifier_overlay.store.put(verifier_identity.sign(evidence(parent)))
            parent_filter = FeedFilter(subjects=(parent.subject,))
            Receiver(consumer_overlay.store).apply(
                "verifier",
                parent_filter,
                Feed(verifier_overlay.store, verifier_identity).page("receiver", parent_filter),
            )
            result = await executor.invoke(
                "parent-two-calls", parent.id, parent.digest, {"value": 4}, context
            )
            assert result["state"] == "completed" and result["result"] == [8, 8]
            assert calls == [4, 4]
            assert (
                await executor.invoke(
                    "parent-two-calls", parent.id, parent.digest, {"value": 4}, context
                )
                == result
            )
            assert calls == [4, 4]
            return
        result = await executor.invoke("remote-1", proxy.id, proxy.digest, {"value": 4}, context)
        assert result["state"] == "completed" and result["result"] == 8
        assert calls == [4]
        assert (
            await executor.invoke("remote-1", proxy.id, proxy.digest, {"value": 4}, context)
            == result
        )
        assert calls == [4]
        # Protocol completion produced no verifier PASS: it is a business result.
        assert all(e.issuer == "verifier" for e in consumer_overlay.store.evidence())
        request = {
            "operation": "invoke",
            "invocation_id": "provider-direct",
            "binding_id": "double",
            "binding_digest": provider_binding.digest,
            "arguments": {"value": 5},
        }
        completed = await send(configs["receiver"], consumer_identity, "producer", request)
        assert completed["state"] == "completed" and completed["result"] == 10
        assert await send(configs["receiver"], consumer_identity, "producer", request) == completed
        queried = await send(
            configs["receiver"],
            consumer_identity,
            "producer",
            {"operation": "invocation", "invocation_id": "provider-direct"},
        )
        assert queried["invocation"] == completed
        hidden = await send(
            configs["verifier"],
            verifier_identity,
            "producer",
            {"operation": "invocation", "invocation_id": "provider-direct"},
        )
        assert hidden["invocation"] is None
        refused = await send(configs["verifier"], verifier_identity, "producer", request)
        assert refused["state"] == "rejected"
        refused = await send(
            configs["receiver"],
            consumer_identity,
            "producer",
            {**request, "invocation_id": "wrong-binding", "binding_digest": "0" * 64},
        )
        assert refused["state"] == "rejected"
        assert calls == [4, 5]
    finally:
        server.should_exit = True
        if serving:
            await asyncio.wait_for(serving, 10)
        service.overlay.store.close()
        verifier_overlay.store.close()
        consumer_overlay.store.close()
