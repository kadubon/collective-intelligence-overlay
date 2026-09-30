import asyncio
import json
import os
import re
import sys
import threading
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import urlsplit

import httpx
import jwt
import pytest
import uvicorn
from agent_framework import (
    Agent,
    AgentSession,
    BaseChatClient,
    ChatResponse,
    Content,
    FunctionInvocationContext,
    FunctionInvocationLayer,
    Message,
    WorkflowBuilder,
    WorkflowContext,
)
from agent_framework import executor as maf_executor
from remote_call_application import (
    admit,
    context,
    parent_binding,
    provider_binding,
    register_consumer,
    register_parent,
    register_provider,
)
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.adapters.a2a import application, send
from collective_intelligence_overlay.adapters.maf import bound_tool
from collective_intelligence_overlay.bindings import ExecutionContext, Registry
from collective_intelligence_overlay.calls import MissingCallIdentity, RemoteCalls
from collective_intelligence_overlay.demo import initialize
from collective_intelligence_overlay.invocations import Executor, Reservation
from collective_intelligence_overlay.models import now
from collective_intelligence_overlay.peer import PeerService
from collective_intelligence_overlay.storage import Conflict


async def ready(url, identity, *, process=None):
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
    async with httpx.AsyncClient(
        trust_env=False, headers={"Authorization": f"Bearer {token}"}
    ) as client:
        for _ in range(120):
            if process is not None and process.returncode is not None:
                raise AssertionError((await process.stderr.read()).decode())
            try:
                response = await client.get(url + ".well-known/agent-card.json")
                assert response.status_code == 200
                return
            except httpx.ConnectError:
                await asyncio.sleep(0.05)
    raise AssertionError("real provider did not start")


async def stop(process):
    if process.returncode is None:
        process.terminate()
    await asyncio.wait_for(process.communicate(), 10)


@pytest.fixture
def peers(tmp_path, policy):
    admin_url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not admin_url:
        pytest.skip("real PostgreSQL required")
    root = tmp_path / "call-peers"
    configs = initialize(root, admin_url, policy.binary)
    for name, old in configs.items():
        configs[name] = old.model_copy(update={"execution_environment": {"application": "1"}})
        saved = configs[name].model_dump(mode="json")
        saved["database_url"] = configs[name].database_url.get_secret_value()
        (root / name / "config.json").write_text(json.dumps(saved), encoding="utf-8")
    provider_identity, provider_overlay = configs["producer"].runtime()
    receiver_identity, registry, proxy = register_consumer(configs["receiver"])
    try:
        with provider_overlay.store.engine.begin() as conn:
            conn.execute(
                text("CREATE TABLE test_call_witness (id integer PRIMARY KEY, count integer)")
            )
            conn.execute(text("INSERT INTO test_call_witness VALUES (1, 0)"))
        admit(provider_overlay, provider_identity, provider_binding(), configs["verifier"])
        admit(registry.overlay, receiver_identity, proxy, configs["verifier"])
        yield SimpleNamespace(
            configs=configs,
            root=root,
            identity=receiver_identity,
            registry=registry,
            proxy=proxy,
            provider=provider_overlay,
            context=context(configs["receiver"]),
        )
    finally:
        registry.overlay.store.close()
        provider_overlay.store.close()
        # Only this fixture's newly allocated UUID databases/roles are eligible.
        admin = create_engine(admin_url, isolation_level="AUTOCOMMIT")
        try:
            with admin.connect() as conn:
                for config in configs.values():
                    url = make_url(config.database_url.get_secret_value())
                    role = url.database
                    assert role == url.username and re.fullmatch(r"cio_[0-9a-f]{32}", role)
                    conn.execute(text(f'DROP DATABASE "{role}" WITH (FORCE)'))
                    conn.execute(text(f'DROP ROLE "{role}"'))
        finally:
            admin.dispose()


@pytest.fixture
async def serving(peers):
    config = peers.configs["producer"]
    service = PeerService(config, register_provider)
    server = uvicorn.Server(
        uvicorn.Config(
            application(config, service.handle),
            host="127.0.0.1",
            port=urlsplit(config.url).port,
            log_level="critical",
            access_log=False,
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        await ready(config.url, peers.identity)
        yield peers
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        service.overlay.store.close()


def count(peers):
    with peers.provider.store.engine.connect() as conn:
        return conn.execute(text("SELECT count FROM test_call_witness WHERE id = 1")).scalar_one()


async def execute(
    peers, call_id, *, scope="persisted-session", arguments=None, execution_context=None
):
    return await peers.registry.execute(
        peers.proxy.id,
        peers.proxy.digest,
        {"value": 7} if arguments is None else arguments,
        peers.context if execution_context is None else execution_context,
        call_id=call_id,
        call_scope=scope,
    )


@pytest.mark.parametrize("parallel", [False, True])
async def test_two_identical_readonly_calls_and_retries_under_one_parent(serving, parallel):
    peers = serving
    registry, proxy = peers.registry, peers.proxy

    async def pair(arguments):
        async def sample(call_id):
            return await registry.execute(
                proxy.id, proxy.digest, arguments, peers.context, call_id=call_id
            )

        values = (
            await asyncio.gather(sample("first"), sample("second"))
            if parallel
            else [await sample("first"), await sample("second")]
        )
        assert await sample("first") == values[0]
        assert await sample("second") == values[1]
        return values

    parent = parent_binding(proxy, pair)
    registry.register_local(parent, pair, lambda _: True)
    admit(registry.overlay, peers.identity, parent, peers.configs["verifier"], dependency=proxy)
    runner = Executor(registry, peers.identity, Reservation())
    result = await runner.invoke("two-calls", parent.id, parent.digest, {"value": 7}, peers.context)
    assert result["state"] == "completed" and sorted(result["result"]) == [1, 2]
    if not parallel:
        assert result["result"] == [1, 2]
    refs = registry.remote_calls(peers.context, invocation_id="two-calls")
    assert {r.call_id for r in refs} == {"first", "second"}
    assert len({r.remote_invocation_id for r in refs}) == 2
    assert len({r.parent_context for r in refs}) == 1 and refs[0].parent_context is not None
    assert count(peers) == 2
    assert (
        await runner.invoke("two-calls", parent.id, parent.digest, {"value": 7}, peers.context)
        == result
    )
    assert count(peers) == 2
    for ref in refs:
        actual = await registry.query_remote_call(
            ref.call_key, peers.context, peers.configs["receiver"], peers.identity
        )
        assert actual["state"] == "completed" and actual["result"] in [1, 2]


async def test_concurrent_retries_share_saved_identity_and_content_conflicts(serving):
    peers = serving
    results = await asyncio.gather(
        *(execute(peers, "same-call") for _ in range(4)), return_exceptions=True
    )
    # A provider still running may report incomplete; that is never another call.
    assert any(result == 1 for result in results)
    assert all(result == 1 or isinstance(result, ValueError) for result in results)
    assert await execute(peers, "same-call") == 1 and count(peers) == 1
    for changed in [
        {"arguments": {"value": 8}},
        {
            "execution_context": peers.context.model_copy(
                update={"permissions": frozenset({"extra"})}
            )
        },
        {"execution_context": peers.context.model_copy(update={"purpose": "verification"})},
        {
            "execution_context": peers.context.model_copy(
                update={"environment": {"application": "2"}}
            )
        },
    ]:
        with pytest.raises(Conflict, match="different request"):
            await execute(peers, "same-call", **changed)
    changed = peers.proxy.model_copy(update={"revision": "2"})
    peers.registry.register_a2a(changed, lambda _: True, peers.configs["receiver"], peers.identity)
    with pytest.raises(Conflict, match="different request"):
        await peers.registry.execute(
            changed.id,
            changed.digest,
            {"value": 7},
            peers.context,
            call_id="same-call",
            call_scope="persisted-session",
        )
    assert count(peers) == 1


async def test_missing_identity_and_separate_scope_owner_caller_lookup(serving):
    peers = serving
    for kwargs in [{}, {"call_id": "only-call"}, {"call_scope": "only-scope"}]:
        with pytest.raises(MissingCallIdentity, match="require"):
            await peers.registry.execute(
                peers.proxy.id, peers.proxy.digest, {"value": 7}, peers.context, **kwargs
            )
    assert count(peers) == 0
    assert await execute(peers, "one", scope="a") == 1
    assert await execute(peers, "one", scope="b") == 2
    assert await execute(peers, "two", scope="a") == 3
    first_page = peers.registry.remote_calls(peers.context, call_scope="a", limit=1)
    second_page = peers.registry.remote_calls(
        peers.context, call_scope="a", limit=1, after=first_page[0].call_key
    )
    assert len(first_page) == len(second_page) == 1
    assert first_page[0].call_key != second_page[0].call_key
    assert (
        peers.registry.remote_calls(
            peers.context, call_scope="a", limit=1, after=second_page[0].call_key
        )
        == ()
    )
    ref = first_page[0]
    stranger = ExecutionContext(caller="verifier", environment=peers.context.environment)
    assert (
        await peers.registry.query_remote_call(
            ref.call_key, stranger, peers.configs["receiver"], peers.identity
        )
        is None
    )
    assert await execute(peers, "one", scope="a", execution_context=stranger) == 4
    local_other = peers.registry.remote_calls(stranger, call_scope="a")[0]
    assert local_other.caller == "verifier" and local_other.call_key != ref.call_key
    assert (
        await peers.registry.query_remote_call(
            local_other.call_key, peers.context, peers.configs["receiver"], peers.identity
        )
        is None
    )
    other_identity, other_registry, other_proxy = register_consumer(peers.configs["verifier"])
    try:
        admit(other_registry.overlay, other_identity, other_proxy, peers.configs["receiver"])
        other_context = context(peers.configs["verifier"])
        assert (
            await other_registry.execute(
                other_proxy.id,
                other_proxy.digest,
                {"value": 7},
                other_context,
                call_id="one",
                call_scope="a",
            )
            == 5
        )
        other_ref = other_registry.remote_calls(other_context, call_scope="a")[0]
        assert other_ref.call_key != ref.call_key
        assert (
            await send(
                peers.configs["verifier"],
                other_identity,
                "producer",
                {"operation": "invocation", "invocation_id": ref.remote_invocation_id},
            )
        )["invocation"] is None
    finally:
        other_registry.overlay.store.close()
    assert count(peers) == 5


async def test_parent_namespaces_and_changed_parent_content_do_not_escape_conflict(serving):
    peers = serving
    registry, proxy = peers.registry, peers.proxy

    async def once(arguments):
        result = await registry.execute(
            proxy.id, proxy.digest, {"value": 7}, peers.context, call_id="same-child"
        )
        return [result]

    parent = parent_binding(proxy, once, name="named-parent")
    registry.register_local(parent, once, lambda _: True)
    admit(registry.overlay, peers.identity, parent, peers.configs["verifier"], dependency=proxy)

    async def invoke(parent_id, value):
        return await registry.execute(
            parent.id,
            parent.digest,
            {"value": value},
            peers.context,
            call_id=parent_id,
            call_scope="same-session",
        )

    assert await invoke("parent-one", 7) == [1]
    assert await invoke("parent-two", 7) == [2]
    assert await invoke("parent-one", 7) == [1]
    with pytest.raises(Conflict, match="parent content"):
        await invoke("parent-one", 8)
    refs = registry.remote_calls(peers.context, call_scope="same-session")
    assert len(refs) == 2 and len({r.parent_context for r in refs}) == 2
    assert count(peers) == 2


async def test_local_proxy_verification_keeps_provider_reuse_admission(serving):
    peers = serving
    proxy = peers.proxy.model_copy(
        update={
            "revision": "2",
            "verification_callers": ("receiver",),
            "subject": peers.proxy.subject.model_copy(update={"version": "2"}),
        }
    )
    peers.registry.register_a2a(proxy, lambda _: True, peers.configs["receiver"], peers.identity)
    admit(peers.registry.overlay, peers.identity, proxy, peers.configs["verifier"])
    # A local proxy probe reuses the qualified provider, preserving the original
    # contract. It does not grant that resource owner remote verification rights.
    assert (
        await peers.registry.execute(
            proxy.id,
            proxy.digest,
            {"value": 7},
            peers.context.model_copy(update={"purpose": "verification"}),
            call_id="probe",
            call_scope="purpose-session",
        )
        == 1
    )
    ref = peers.registry.remote_calls(peers.context, call_scope="purpose-session")[0]
    actual = await peers.registry.query_remote_call(
        ref.call_key, peers.context, peers.configs["receiver"], peers.identity
    )
    assert actual["purpose"] == "reuse" and actual["result"] == 1
    provider = provider_binding()
    denied = await send(
        peers.configs["receiver"],
        peers.identity,
        "producer",
        {
            "operation": "invoke",
            "invocation_id": "ungranted-provider-probe",
            "binding_id": provider.id,
            "binding_digest": provider.digest,
            "arguments": {"value": 7},
            "purpose": "verification",
        },
    )
    assert denied["state"] == "rejected" and count(peers) == 1
    # Nor can local verification bypass the provider's required independent PASS.
    from collective_intelligence_overlay.models import Revocation

    verifier, verifier_overlay = peers.configs["verifier"].runtime()
    try:
        evidence = next(
            item
            for item in peers.provider.store.evidence()
            if item.issuer == "verifier" and item.binding_digest == provider.digest
        )
        revocation = Revocation(
            issuer="verifier",
            subject=evidence.subject,
            evidence_id=evidence.id,
            reason="withdrawn",
        )
        peers.provider.store.put(verifier.sign(revocation))
    finally:
        verifier_overlay.store.close()
    with pytest.raises(ValueError, match="incomplete or unknown"):
        await peers.registry.execute(
            proxy.id,
            proxy.digest,
            {"value": 7},
            peers.context.model_copy(update={"purpose": "verification"}),
            call_id="after-withdrawal",
            call_scope="purpose-session",
        )
    assert count(peers) == 1


async def test_cancellation_joins_persisted_mapping_thread_before_store_cleanup(
    serving, monkeypatch
):
    peers = serving
    committed = asyncio.Event()
    release = threading.Event()
    loop = asyncio.get_running_loop()
    original = RemoteCalls.bind

    def delayed(self, *args):
        saved = original(self, *args)
        loop.call_soon_threadsafe(committed.set)
        assert release.wait(10), "mapping thread was not released"
        return saved

    monkeypatch.setattr(RemoteCalls, "bind", delayed)
    runner = Executor(peers.registry, peers.identity, Reservation())
    running = asyncio.create_task(
        runner.invoke(
            "cancel-during-map", peers.proxy.id, peers.proxy.digest, {"value": 7}, peers.context
        )
    )
    try:
        await asyncio.wait_for(committed.wait(), 10)
        running.cancel()
        await asyncio.sleep(0)
        assert not running.done()
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await running
        saved = runner.store.get("receiver", "cancel-during-map")
        assert saved["state"] == "unknown" and saved["phase"] == "dispatched"
        assert saved["reservation_state"] == "held" and count(peers) == 0
        refs = peers.registry.remote_calls(peers.context, invocation_id="cancel-during-map")
        assert len(refs) == 1
        assert (
            await peers.registry.query_remote_call(
                refs[0].call_key, peers.context, peers.configs["receiver"], peers.identity
            )
            is None
        )
    finally:
        release.set()
        if not running.done():
            running.cancel()
            await asyncio.gather(running, return_exceptions=True)


class TwoCallClient(FunctionInvocationLayer, BaseChatClient):
    async def _inner_get_response(self, *, messages, stream, options, **kwargs):
        if any(message.role == "tool" for message in messages):
            return ChatResponse(messages=Message("assistant", ["observed twice"]))
        return ChatResponse(
            messages=Message(
                "assistant",
                [
                    Content.from_function_call(
                        call_id=call_id,
                        name="remote-observe",
                        arguments={"arguments": {"value": 7}},
                    )
                    for call_id in ("maf-one", "maf-two")
                ],
            )
        )


async def test_actual_maf_public_call_ids_and_restored_agent_session(serving):
    peers = serving
    session = AgentSession(session_id="persisted-maf-session")
    registered = bound_tool(
        peers.registry, peers.proxy.id, peers.context, call_scope=session.session_id
    )
    assert set(registered.parameters()["properties"]) == {"arguments"}
    agent = Agent(client=TwoCallClient(), tools=[registered])
    assert (await agent.run("sample twice", session=session)).text == "observed twice"
    assert count(peers) == 2
    saved_session = json.loads(json.dumps(session.to_dict()))
    restored = AgentSession.from_dict(saved_session)
    assert restored.session_id == session.session_id
    replacement = Registry(peers.registry.overlay)
    replacement.register_a2a(peers.proxy, lambda _: True, peers.configs["receiver"], peers.identity)
    tool = bound_tool(replacement, peers.proxy.id, peers.context, call_scope=restored.session_id)
    for call_id in ("maf-one", "maf-two"):
        result = await tool.invoke(
            arguments={"arguments": {"value": 7}}, tool_call_id=call_id, skip_parsing=True
        )
        assert result in (1, 2)
    assert count(peers) == 2
    with pytest.raises(Conflict):
        await tool.invoke(
            arguments={"arguments": {"value": 8}}, tool_call_id="maf-one", skip_parsing=True
        )
    invocation_context = FunctionInvocationContext(
        function=tool, arguments={"arguments": {"value": 7}}, metadata={"call_id": "maf-two"}
    )
    assert await tool.invoke(context=invocation_context, skip_parsing=True) in (1, 2)
    with pytest.raises(Conflict, match="disagree"):
        await tool.invoke(context=invocation_context, tool_call_id="maf-one", skip_parsing=True)
    with pytest.raises(MissingCallIdentity):
        await tool.invoke(arguments={"arguments": {"value": 7}}, skip_parsing=True)
    assert count(peers) == 2


async def test_actual_maf_composite_workflow_preserves_two_child_ids(serving):
    peers = serving
    registry, proxy = peers.registry, peers.proxy

    async def composite(arguments):
        @maf_executor(id="first-sample")
        async def first(data: dict, ctx: WorkflowContext[dict]) -> None:
            one = await registry.execute(
                proxy.id, proxy.digest, data, peers.context, call_id="stage-first"
            )
            await ctx.send_message({"arguments": data, "first": one})

        @maf_executor(id="second-sample")
        async def second(data: dict, ctx: WorkflowContext[dict, list]) -> None:
            two = await registry.execute(
                proxy.id, proxy.digest, data["arguments"], peers.context, call_id="stage-second"
            )
            await ctx.yield_output([data["first"], two])

        flow = (
            WorkflowBuilder(start_executor=first, max_iterations=3).add_edge(first, second).build()
        )
        return (await flow.run(arguments)).get_outputs()[0]

    parent = parent_binding(proxy, composite, name="workflow-parent")
    registry.register_local(parent, composite, lambda _: True)
    admit(registry.overlay, peers.identity, parent, peers.configs["verifier"], dependency=proxy)
    runner = Executor(registry, peers.identity, Reservation())
    result = await runner.invoke(
        "workflow-call", parent.id, parent.digest, {"value": 7}, peers.context
    )
    assert result["state"] == "completed" and result["result"] == [1, 2]
    assert count(peers) == 2
    assert (
        await runner.invoke("workflow-call", parent.id, parent.digest, {"value": 7}, peers.context)
        == result
    )
    assert count(peers) == 2


async def child(peers, mode, *, lose=False, output=None):
    args = [
        sys.executable,
        str(Path(__file__).with_name("remote_call_application.py")),
        mode,
        str(peers.root / ("producer" if mode == "provider" else "receiver") / "config.json"),
    ]
    if lose:
        args.append("--lose-response")
    if output:
        args.extend(["--output", str(output)])
    return await asyncio.create_subprocess_exec(
        *args, cwd=peers.root, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
    )


async def test_lost_real_http_response_provider_and_caller_process_restart(peers, tmp_path):
    parent = register_parent(peers.registry, peers.proxy, peers.context)
    admit(
        peers.registry.overlay,
        peers.identity,
        parent,
        peers.configs["verifier"],
        dependency=peers.proxy,
    )
    provider_runtime = tmp_path / "provider-runtime.json"
    provider = await child(peers, "provider", lose=True, output=provider_runtime)
    try:
        await ready(peers.configs["producer"].url, peers.identity, process=provider)
        runtime = json.loads(provider_runtime.read_text())
        assert runtime["minor"] == list(sys.version_info[:2])
        assert os.path.normcase(runtime["executable"]) == os.path.normcase(sys.executable)
        output = tmp_path / "caller-before.json"
        caller = await child(peers, "caller", output=output)
        try:
            _, stderr = await asyncio.wait_for(caller.communicate(), 60)
            assert caller.returncode == 0, stderr.decode()
        finally:
            await stop(caller)
        before = json.loads(output.read_text())
        assert before["runtime"]["minor"] == list(sys.version_info[:2])
        assert os.path.normcase(before["runtime"]["executable"]) == os.path.normcase(sys.executable)
        assert before["result"]["state"] == "unknown"
        assert (
            before["result"]["reservation_state"] == "held"
            and before["result"]["phase"] == "dispatched"
        )
        assert len(before["calls"]) == 1 and count(peers) == 1
        await stop(provider)
        provider = await child(peers, "provider", output=provider_runtime)
        await ready(peers.configs["producer"].url, peers.identity, process=provider)
        assert json.loads(provider_runtime.read_text()) == runtime
        output = tmp_path / "caller-after.json"
        caller = await child(peers, "resume", output=output)
        try:
            _, stderr = await asyncio.wait_for(caller.communicate(), 60)
            assert caller.returncode == 0, stderr.decode()
        finally:
            await stop(caller)
        after = json.loads(output.read_text())
        assert after["runtime"]["minor"] == list(sys.version_info[:2])
        assert after["result"] == before["result"] and after["calls"] == before["calls"]
        assert after["queries"][0]["state"] == "completed" and after["queries"][0]["result"] == 1
        assert count(peers) == 1  # Parent UNKNOWN is retained; second child was never dispatched.
        assert (
            peers.registry.remote_calls(peers.context, invocation_id="lost-parent")[
                0
            ].remote_invocation_id
            == before["calls"][0]["remote_invocation_id"]
        )
        assert (
            await send(
                peers.configs["receiver"],
                peers.identity,
                "producer",
                {
                    "operation": "cancel_invocation",
                    "invocation_id": before["calls"][0]["remote_invocation_id"],
                },
            )
        )["invocation"]["state"] == "completed"
    finally:
        await stop(provider)
