"""Applicability and time bounds with real PostgreSQL and the packaged Rego policy."""

from datetime import timedelta

import pytest

from collective_intelligence_overlay.models import Capability, Evidence, UseRequest, now
from collective_intelligence_overlay.overlay import Overlay


def bound_records(records):
    cap, evidence = records
    cap = Capability.model_validate(
        {**cap.model_dump(), "schema_version": "2", "binding_digest": "a" * 64}
    )
    evidence = Evidence.model_validate(
        {**evidence.model_dump(), "schema_version": "2", "binding_digest": cap.binding_digest}
    )
    return cap, evidence


def request(cap):
    return UseRequest(
        receiver="receiver",
        subject=cap.subject,
        scope=cap.scope,
        binding_digest=cap.binding_digest,
        semantic_fit="confirmed",
    )


@pytest.mark.parametrize("field", ["binding_digest", "claim", "receivers", "scope", "method"])
async def test_unrelated_evidence_cannot_shorten_admission(
    store, policy, identities, records, field
):
    cap, evidence = bound_records(records)
    for record in (cap, evidence):
        store.put(identities[record.issuer].sign(record))
    overlay = Overlay(store, policy)
    overlay.observed("producer")
    overlay.observed("verifier")
    before = await overlay.qualify(request(cap))
    assert before.outcome == "ACCEPT"
    changes = {
        "binding_digest": "b" * 64,
        "claim": "different-claim",
        "receivers": ("other",),
        "scope": evidence.scope.model_copy(update={"task": "different-task"}),
        "method": "not-operator-authorized",
    }
    unrelated = evidence.model_copy(
        update={
            "id": "unrelated",
            "issuer": "other",
            field: changes[field],
            "expires_at": now() + timedelta(seconds=10),
        }
    )
    store.put(identities["other"].sign(unrelated))
    after = await overlay.qualify(request(cap))
    assert after.outcome == "ACCEPT"
    assert after.valid_until >= before.valid_until


async def test_support_expiry_bounds_the_accepted_decision(store, policy, identities, records):
    cap, evidence = bound_records(records)
    support = evidence.model_copy(
        update={"id": "support", "expires_at": now() + timedelta(seconds=120)}
    )
    root = evidence.model_copy(update={"evidence_dependencies": (support.id,)})
    for record in (cap, support, root):
        store.put(identities[record.issuer].sign(record))
    overlay = Overlay(store, policy)
    overlay.observed("producer")
    overlay.observed("verifier")
    decision = await overlay.qualify(request(cap))
    assert decision.outcome == "ACCEPT"
    assert decision.valid_until <= support.expires_at
