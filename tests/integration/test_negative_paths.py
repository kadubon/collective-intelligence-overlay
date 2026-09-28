import asyncio
from datetime import timedelta

import pytest

from collective_intelligence_overlay.models import Evidence, Revocation, UseRequest, now
from collective_intelligence_overlay.overlay import Overlay
from collective_intelligence_overlay.security import Principal


def req(cap):
    return UseRequest(
        receiver="receiver", subject=cap.subject, scope=cap.scope, semantic_fit="confirmed"
    )


async def test_expired_evidence_and_unknown_license(store, policy, identities, records):
    cap, ev = records
    expired = ev.model_copy(
        update={"created_at": now() - timedelta(days=2), "expires_at": now() - timedelta(days=1)}
    )
    cap = cap.model_copy(update={"license": None})
    store.put(identities[cap.issuer].sign(cap))
    store.put(identities[ev.issuer].sign(expired))
    overlay = Overlay(store, policy)
    overlay.observed(cap.issuer)
    overlay.observed("verifier")
    assert (await overlay.qualify(req(cap))).outcome == "UNKNOWN"


async def test_trust_group_comes_from_operator(overlay, records):
    cap, _ = records
    old = overlay.store.principals["verifier"]
    overlay.store.principals["verifier"] = Principal(old.key, "producer", old.methods)
    assert (await overlay.qualify(req(cap))).outcome == "REQUALIFY"


async def test_counterexample_not_erased_by_more_pass(overlay, records, identities):
    cap, ev = records
    fail = Evidence.model_validate({**ev.model_dump(), "id": "counterexample", "verdict": "FAIL"})
    overlay.store.put(identities[ev.issuer].sign(fail))
    assert (await overlay.qualify(req(cap))).outcome == "REJECT"
    assert len(overlay.store.evidence()) == 2


async def test_out_of_scope_fail_does_not_revoke(overlay, records, identities):
    cap, ev = records
    fail = Evidence.model_validate(
        {
            **ev.model_dump(),
            "id": "different-scope",
            "verdict": "FAIL",
            "scope": {**ev.scope.model_dump(), "task": "another-task"},
        }
    )
    overlay.store.put(identities[ev.issuer].sign(fail))
    assert (await overlay.qualify(req(cap))).outcome == "ACCEPT"


async def test_evidence_revocation_and_wrong_issuer(overlay, records, identities):
    cap, ev = records
    rev = Revocation(
        issuer="other", subject=cap.subject, evidence_id=ev.id, reason="unapproved report"
    )
    overlay.store.put(identities["other"].sign(rev))
    assert (await overlay.qualify(req(cap))).outcome == "ACCEPT"
    rev = rev.model_copy(update={"issuer": "verifier"})
    overlay.store.put(identities["verifier"].sign(rev))
    assert (await overlay.qualify(req(cap))).outcome == "REQUALIFY"


async def test_cyclic_evidence_is_not_proof(store, policy, records, identities):
    cap, ev = records
    ev = ev.model_copy(update={"id": "e1", "evidence_dependencies": ("e2",)})
    ev2 = ev.model_copy(update={"id": "e2", "evidence_dependencies": ("e1",)})
    for record in (cap, ev, ev2):
        store.put(identities[record.issuer].sign(record))
    overlay = Overlay(store, policy)
    overlay.observed("producer")
    overlay.observed("verifier")
    assert (await overlay.qualify(req(cap))).outcome == "REQUALIFY"


async def test_dependency_cycle_and_graph_bound(store, policy, records, identities):
    cap, _ = records
    second_subject = cap.subject.model_copy(update={"id": "second"})
    first = cap.model_copy(update={"dependencies": (second_subject,)})
    second = cap.model_copy(update={"subject": second_subject, "dependencies": (cap.subject,)})
    for c in (first, second):
        store.put(identities[c.issuer].sign(c))
    overlay = Overlay(store, policy, max_graph_nodes=1)
    overlay.observed("producer")
    overlay.observed("verifier")
    assert (await overlay.qualify(req(cap))).outcome == "UNKNOWN"


async def test_timeout_and_cancellation_do_not_return_pass(overlay, records):
    async def slow():
        await asyncio.sleep(10)

    with pytest.raises(TimeoutError):
        await overlay.execute(req(records[0]), slow, deadline_seconds=0.01)
    task = asyncio.create_task(overlay.execute(req(records[0]), slow))
    await asyncio.sleep(0.2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task


async def test_policy_changes_require_new_policy_instance(overlay, records, tmp_path):
    original = overlay.policy.path
    path = tmp_path / "policy.rego"
    path.write_bytes(original.read_bytes() + b"\n# changed\n")
    overlay.policy.path = path
    decision = await overlay.qualify(req(records[0]))
    assert decision.outcome == "UNKNOWN"
    assert "policy_changed" in decision.reasons


async def test_revocation_arriving_during_policy_check(overlay, records, identities, monkeypatch):
    cap, _ = records
    original = overlay.policy.decide

    async def decide(facts):
        result = await original(facts)
        rev = Revocation(issuer="producer", subject=cap.subject, reason="arrived during check")
        overlay.store.put(identities["producer"].sign(rev))
        return result

    monkeypatch.setattr(overlay.policy, "decide", decide)
    result = await overlay.qualify(req(cap))
    assert result.outcome == "UNKNOWN"
    assert result.reasons == ("state_changed_during_check",)


async def test_verifier_refresh_is_required(overlay, records):
    overlay.observed_sources["verifier"] = now() - timedelta(days=1)
    assert (await overlay.qualify(req(records[0]))).outcome == "UNKNOWN"
