"""Configured-provider inconsistencies over real authenticated A2A and PostgreSQL."""

import asyncio
import copy
from urllib.parse import urlsplit

import pytest
import uvicorn
from remote_call_application import register_provider
from test_call_identity import count, ready
from test_call_identity import peers as peers

from collective_intelligence_overlay.adapters.a2a import application
from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.invocations import Executor, Reservation
from collective_intelligence_overlay.peer import PeerService
from collective_intelligence_overlay.security import verify


@pytest.mark.parametrize(
    ("field", "replacement"),
    [
        ("id", "other-invocation"),
        ("caller", "verifier"),
        ("owner", "verifier"),
        ("binding_id", "other-binding"),
        ("binding_digest", "a" * 64),
        ("arguments_digest", "b" * 64),
        ("purpose", "verification"),
        ("result", 999),
        ("result_digest", "c" * 64),
        ("fingerprint", "malformed"),
        ("result_digest", None),
        ("id", None),
    ],
)
async def test_wrong_completed_reply_never_becomes_executor_result(peers, field, replacement):
    p = peers
    config = p.configs["producer"]
    service = PeerService(config, register_provider)
    actual = service.handle
    responses = []

    async def inconsistent(caller, data):
        response = await actual(caller, data)
        if data.get("operation") == "invoke":
            assert response["state"] == "completed"
            responses.append(copy.deepcopy(response))
            response = {**response, field: replacement}
            if replacement is None:
                del response[field]
        return response

    server = uvicorn.Server(
        uvicorn.Config(
            application(config, inconsistent),
            host="127.0.0.1",
            port=urlsplit(config.url).port,
            log_level="critical",
            access_log=False,
        )
    )
    task = asyncio.create_task(server.serve())
    try:
        await ready(config.url, p.identity)
        executor = Executor(p.registry, p.identity, Reservation())
        result = await executor.invoke(
            "inconsistent-provider", p.proxy.id, p.proxy.digest, {"value": 7}, p.context
        )
        assert result["state"] == "unknown"
        assert result["result"] is None and result["result_digest"] is None
        store = p.registry.overlay.store
        receipt = verify(
            store.signed_record(store.reference("event", "receiver", result["receipt_id"])),
            store.principals,
        )
        assert receipt.execution.state == "unknown"
        assert receipt.execution.result_digest is None
        saved = p.registry.remote_calls(p.context, invocation_id="inconsistent-provider")
        assert len(saved) == 1
        assert saved[0].remote_invocation_id == responses[0]["id"]
        assert saved[0].arguments_digest == fingerprint({"value": 7})
        assert result["reservation_state"] == "held"
        assert count(p) == 1
        lookup = await p.registry.query_remote_call(
            saved[0].call_key, p.context, p.configs["receiver"], p.identity
        )
        assert lookup == responses[0]
        assert executor.store.get("receiver", "inconsistent-provider") == result
        assert count(p) == 1
    finally:
        server.should_exit = True
        await asyncio.wait_for(task, 10)
        service.close()
