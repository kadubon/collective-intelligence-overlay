"""Stored-request negative controls; live original-ID transport is tested in E2E."""

import copy

import pytest
from sqlalchemy import select
from test_call_identity import peers as peers

from collective_intelligence_overlay.application import ApplicationHost
from collective_intelligence_overlay.bindings import fingerprint
from collective_intelligence_overlay.calls import RemoteCalls, call_instance
from collective_intelligence_overlay.invocations import Reservation
from collective_intelligence_overlay.starter.documents import DocumentService
from collective_intelligence_overlay.storage import budgets, records


@pytest.fixture
def original_document(peers):
    host = ApplicationHost(peers.configs["receiver"])
    producer = DocumentService(peers.configs["producer"])
    try:
        service = DocumentService(host.config, host)
        binding = service.install_remote(producer.installed["words"])
        arguments = {"text": "reference 文書 Δ"}
        request = {"caller": "receiver", "arguments": arguments}
        claim, fresh = host.executor.store.claim(
            "receiver", "stored-document", binding.id, binding.digest, request, Reservation()
        )
        assert fresh
        host.executor.store.dispatched(claim)
        context = fingerprint(["receiver", "receiver", "stored-document"])
        call = RemoteCalls(host.overlay.store).bind(
            call_instance("receiver", "document-child", None, context, request),
            binding,
            binding.target,
            arguments,
        )
        original = host.executor.store.cancel("receiver", "stored-document")
        assert original["state"] == "unknown" and original["reservation_state"] == "held"
        # A candidate provider report is input to these negative controls, not
        # evidence of a network exchange or physical provider execution.
        report = {
            "id": call.remote_invocation_id,
            "owner": call.provider,
            "caller": call.owner,
            "binding_digest": call.provider_binding_digest,
            "arguments_digest": call.arguments_digest,
            "state": "completed",
            "result": {"words": 3},
            "result_digest": fingerprint({"words": 3}),
        }
        yield service, host, call, report, original
        assert host.executor.store.get("receiver", "stored-document") == original
    finally:
        host.close()
        producer.overlay.store.close()


def saved_state(host):
    with host.overlay.store.engine.connect() as conn:
        return (
            conn.execute(select(budgets.c.remaining).where(budgets.c.unit == "work")).scalar_one(),
            dict(conn.execute(select(records.c.record_id, records.c.envelope)).all()),
        )


async def test_document_query_keeps_unconfirmed_results_and_original_allowance(original_document):
    service, host, call, report, _ = original_document
    before = saved_state(host)
    for changes in (
        {"state": "unknown"},
        {"result": {"words": 2}, "result_digest": fingerprint({"words": 2})},
        {"result": {"words": True}, "result_digest": fingerprint({"words": True})},
        {"result": {"words": 3, "extra": 1}},
        {"result": None},
        {"result_digest": "a" * 64},
    ):
        observed = await service.inspect_original_result(
            {"call": call.model_dump(mode="json"), "provider_report": report | changes}
        )
        assert observed["effect"] == "unknown", changes
        assert observed["reason"] == "DOCUMENT_RESULT_UNCONFIRMED"
        assert observed["provider_invocation_id"] == call.remote_invocation_id
        assert saved_state(host) == before


async def test_document_query_refuses_missing_or_changed_original_identity(original_document):
    service, host, call, report, _ = original_document
    before = saved_state(host)
    for area, field, value in (
        ("call", "call_key", "a" * 64),
        ("call", "invocation_context", "b" * 64),
        ("call", "arguments_digest", None),
        ("call", "caller", "verifier"),
        ("provider_report", "id", "another-operation"),
        ("provider_report", "owner", "other"),
        ("provider_report", "caller", "verifier"),
        ("provider_report", "binding_digest", "c" * 64),
        ("provider_report", "arguments_digest", "d" * 64),
    ):
        arguments = {"call": call.model_dump(mode="json"), "provider_report": copy.deepcopy(report)}
        arguments[area][field] = value
        with pytest.raises(ValueError, match="original|identity"):
            await service.inspect_original_result(arguments)
        assert saved_state(host) == before
