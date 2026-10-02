"""Actual authenticated C -> B -> A, lost response and B process restart."""

import asyncio
import json
import sys
from pathlib import Path

import pytest
from a2a.utils.errors import InternalError
from remote_call_application import proxy_binding
from test_call_identity import child, count, ready, stop
from test_call_identity import peers as peers

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.bindings import ExecutionContext, Registry, fingerprint
from collective_intelligence_overlay.invocations import InvocationStore
from collective_intelligence_overlay.reconciliation import Reconciliations
from collective_intelligence_overlay.security import verify
from collective_intelligence_overlay.storage import Conflict


async def requester(p, tmp_path, payload, number):
    request = tmp_path / f"request-{number}.json"
    output = tmp_path / f"response-{number}.json"
    request.write_text(json.dumps(payload), encoding="utf-8")
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        str(Path(__file__).with_name("remote_call_application.py")),
        "requester",
        str(p.root / "verifier" / "config.json"),
        "--request",
        str(request),
        "--output",
        str(output),
        cwd=p.root,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        _, stderr = await asyncio.wait_for(process.communicate(), 60)
        assert process.returncode == 0, stderr.decode()
        return json.loads(output.read_text())
    finally:
        await stop(process)


async def test_three_peer_lost_response_owner_lookup_after_delegator_restart(peers, tmp_path):
    p = peers
    provider = await child(p, "provider", lose=True)
    delegator = await child(p, "delegator")
    c_identity, c_overlay = p.configs["verifier"].runtime()
    try:
        await ready(p.configs["producer"].url, p.identity, process=provider)
        await ready(p.configs["receiver"].url, c_identity, process=delegator)
        payload = {
            "operation": "invoke",
            "invocation_id": "same-delegated-id",
            "binding_id": p.proxy.id,
            "binding_digest": p.proxy.digest,
            "arguments": {"value": 7},
        }
        original = (await requester(p, tmp_path, payload, 1))["result"]
        assert original["state"] == "unknown" and original["reservation_state"] == "held"
        assert original["caller"] == "verifier" and original["owner"] == "receiver"
        assert count(p) == 1
        before = p.registry.remote_calls(
            p.context, original_caller="verifier", invocation_id="same-delegated-id"
        )
        assert len(before) == 1
        saved = before[0]
        assert saved.owner == "receiver" and saved.caller == "verifier"
        assert saved.invocation_context == fingerprint(
            ["receiver", "verifier", payload["invocation_id"]]
        )
        assert p.registry.remote_calls(p.context, invocation_id=payload["invocation_id"]) == ()
        # B's owning actor does not relabel C's original map during restart.
        old_pid = delegator.pid
        await stop(delegator)
        delegator = await child(p, "delegator")
        assert delegator.pid != old_pid and provider.pid != delegator.pid
        await ready(p.configs["receiver"].url, p.identity, process=delegator)
        listing = await send(
            p.configs["receiver"],
            p.identity,
            "receiver",
            {
                "operation": "remote_calls",
                "original_caller": "verifier",
                "invocation_id": payload["invocation_id"],
            },
        )
        assert listing["calls"] == [saved.model_dump(mode="json")]
        observed = await send(
            p.configs["receiver"],
            p.identity,
            "receiver",
            {
                "operation": "reconcile",
                "original_caller": "verifier",
                "invocation_id": payload["invocation_id"],
                "call_key": saved.call_key,
                "command_id": "owner-observe-C",
            },
        )
        event = verify(observed["envelope"], p.registry.overlay.store.principals)
        r = event.reconciliation
        assert r.caller == "verifier" and event.issuer == "receiver"
        assert r.provider_invocation_id == saved.remote_invocation_id
        assert r.reported_state == "completed" and r.provider_result_digest == fingerprint(1)
        assert r.effect == "unknown" and r.independent_verification == "UNKNOWN"
        assert r.original_receipt.issuer == "receiver"
        assert r.original_receipt.id == original["receipt_id"]
        assert (
            InvocationStore(p.registry.overlay.store).get("verifier", payload["invocation_id"])
            == original
        )
        assert count(p) == 1
        assert (await requester(p, tmp_path, payload, 2))["result"] == original
        assert count(p) == 1  # Resending B's original ID never resends its uncertain A call.
        for data in (
            {"operation": "remote_calls", "original_caller": "receiver"},
            {"operation": "reconcile", "call_key": saved.call_key, "command_id": "unauthorized"},
        ):
            with pytest.raises(InternalError, match="owner-only"):
                await send(p.configs["verifier"], c_identity, "receiver", data)
        a_config = p.configs["producer"]
        a_identity = a_config.identity(a_config.owner, a_config.private_key)
        with pytest.raises(InternalError, match="owner-only"):
            await send(a_config, a_identity, "receiver", {"operation": "remote_calls"})
        with pytest.raises(ValueError, match="owner-only"):
            p.registry.remote_calls(
                ExecutionContext(caller="verifier", environment={}), original_caller="receiver"
            )
        # Same textual parent ID under B is a distinct operation and map.
        other = await send(p.configs["receiver"], p.identity, "receiver", payload)
        assert other["state"] == "completed" and other["result"] == 2
        own = p.registry.remote_calls(p.context, invocation_id=payload["invocation_id"])
        assert len(own) == 1 and own[0].call_key != saved.call_key
        assert own[0].remote_invocation_id != saved.remote_invocation_id
        assert (
            p.registry.remote_calls(
                p.context, original_caller="verifier", invocation_id=payload["invocation_id"]
            )
            == before
        )
        # The immutable original receipt supplies the observation subject even if
        # a restarted installation now contains a changed local proxy revision.
        registry = Registry(p.registry.overlay)
        changed = proxy_binding(p.configs["receiver"]).model_copy(update={"revision": "2"})
        registry.register_a2a(changed, lambda _: True, p.configs["receiver"], p.identity)
        assert (
            await registry.query_remote_call(
                saved.call_key,
                p.context,
                p.configs["receiver"],
                p.identity,
                original_caller="verifier",
            )
        )["result"] == 1
        observer = Reconciliations(registry, p.configs["receiver"], p.identity)
        after = await observer.observe(
            "receiver",
            saved.call_key,
            "changed-install",
            original_caller="verifier",
            invocation_id=payload["invocation_id"],
        )
        assert after.reconciliation.reported_state == "completed"
        with pytest.raises(Conflict, match="changed"):
            await observer.observe(
                "receiver",
                saved.call_key,
                "changed-install",
                original_caller="receiver",
                invocation_id=payload["invocation_id"],
            )
        with pytest.raises(ValueError, match="original parent"):
            await observer.observe(
                "receiver",
                saved.call_key,
                "wrong-parent",
                original_caller="verifier",
                invocation_id="other-id",
            )
        assert count(p) == 2
    finally:
        await stop(delegator)
        await stop(provider)
        c_overlay.store.close()
