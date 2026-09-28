from datetime import timedelta

import pytest

from collective_intelligence_overlay.models import Revocation, UseRequest, now
from collective_intelligence_overlay.overlay import AdmissionDenied
from collective_intelligence_overlay.storage import Conflict


def request(cap, **kwargs):
    return UseRequest(
        receiver="receiver",
        subject=cap.subject,
        scope=cap.scope,
        semantic_fit="confirmed",
        **kwargs,
    )


async def test_accept_then_revocation_at_use(overlay, records, identities):
    cap, _ = records
    req = request(cap)
    assert (await overlay.qualify(req)).outcome == "ACCEPT"
    rev = Revocation(issuer="producer", subject=cap.subject, reason="withdrawn")
    overlay.store.put(identities["producer"].sign(rev))
    ran = False

    async def operation():
        nonlocal ran
        ran = True

    with pytest.raises(AdmissionDenied):
        await overlay.execute(req, operation)
    assert not ran
    assert len(overlay.store.decision_records()) == 2


@pytest.mark.parametrize(
    ("change", "outcome"),
    [
        ({"verdict": "UNKNOWN"}, "REQUALIFY"),
        ({"verdict": "FAIL"}, "REJECT"),
        ({"issuer": "producer"}, "REQUALIFY"),
        ({"receivers": ("other",)}, "REQUALIFY"),
        ({"method": "unknown"}, "REQUALIFY"),
        ({"obligations": ("unresolved",)}, "REQUALIFY"),
    ],
)
async def test_evidence_fail_closed(store, policy, records, identities, change, outcome):
    from collective_intelligence_overlay.overlay import Overlay

    cap, evidence = records
    evidence = type(evidence).model_validate({**evidence.model_dump(), **change})
    store.put(identities[cap.issuer].sign(cap))
    store.put(identities[evidence.issuer].sign(evidence))
    overlay = Overlay(store, policy)
    overlay.observed("producer")
    overlay.observed("verifier")
    assert (await overlay.qualify(request(cap))).outcome == outcome


async def test_scope_unknown_and_freshness(overlay, records):
    cap, _ = records
    req = request(cap)
    assert (
        await overlay.qualify(req.model_copy(update={"semantic_fit": "unknown"}))
    ).outcome == "UNKNOWN"
    changed = cap.scope.model_copy(update={"environment": {"reference": "2"}})
    assert (await overlay.qualify(req.model_copy(update={"scope": changed}))).outcome == "REQUALIFY"
    overlay.observed_sources["producer"] = now() - timedelta(days=1)
    assert (await overlay.qualify(req)).outcome == "UNKNOWN"


def test_duplicate_and_conflict(overlay, records, identities):
    cap, _ = records
    assert not overlay.store.put(identities[cap.issuer].sign(cap))
    changed = cap.model_copy(update={"license": "MIT"})
    with pytest.raises(Conflict):
        overlay.store.put(identities[cap.issuer].sign(changed))


async def test_policy_missing_is_unknown(overlay, records):
    overlay.policy.binary = "missing-opa-binary-should-not-exist"
    assert (await overlay.qualify(request(records[0]))).outcome == "UNKNOWN"
