import base64

import pytest

from collective_intelligence_overlay.models import RecordRef
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.security import digest
from collective_intelligence_overlay.storage import Conflict, subject_key
from collective_intelligence_overlay.synchronization import Feed, FeedFilter


def test_opportunity_dedup_exact_lookup_and_no_admission_revision(
    store, identities, records, opportunity
):
    cap = records[0]
    store.put(identities[cap.issuer].sign(cap))
    before = store.revisions({subject_key(cap.subject)})
    envelope = identities[opportunity.issuer].sign(opportunity)
    assert store.put(envelope)
    assert not store.put(envelope)
    assert store.revisions({subject_key(cap.subject)}) == before
    # Evidence synchronization must not silently opt private proposals into sharing.
    page = Feed(store, identities["receiver"]).page("producer", FeedFilter())
    assert not page.records

    assert store.record_page(RecordQuery()).items == (cap,)
    query = RecordQuery(
        kinds=("opportunity",),
        issuer=opportunity.issuer,
        record_id=opportunity.id,
        scope=opportunity.scope,
        policy_digest=opportunity.policy_digest,
    )
    assert store.record_page(query, limit=1).items == (opportunity,)
    assert not store.record_page(query.model_copy(update={"record_id": "absent"})).items
    assert store.record_page(
        RecordQuery(kinds=("capability",), issuer=cap.issuer, record_id=cap.subject.key)
    ).items == (cap,)
    changed = opportunity.model_copy(update={"reasons": ("different-cause",)})
    with pytest.raises(Conflict):
        store.put(identities[changed.issuer].sign(changed))
    assert store.revisions({subject_key(cap.subject)}) == before


def test_reference_checks_original_legacy_payload_and_issuer(store, identities, records):
    cap = records[0]
    envelope = identities[cap.issuer].sign(cap)
    store.put(envelope)
    ref = RecordRef(
        kind="capability",
        issuer=cap.issuer,
        id=cap.subject.key,
        payload_digest=digest(base64.b64decode(envelope["payload"])),
    )
    assert store.resolve_reference(ref) == cap
    # Legacy signing omits extension defaults: current serialization is not the original.
    assert digest(cap.model_dump_json().encode()) != ref.payload_digest
    for change in (
        {"payload_digest": digest(b"fabricated")},
        {"issuer": "other"},
        {"id": "absent"},
        {"kind": "evidence"},
    ):
        with pytest.raises(ValueError):
            store.resolve_reference(ref.model_copy(update=change))
