import json
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import event as sql_event

from collective_intelligence_overlay.lifecycle import (
    CapabilityIdentity,
    Coverage,
    assess_stock,
    inspect_lifecycle,
    observe_growth,
)
from collective_intelligence_overlay.lifecycle_store import export_originals, read_lifecycle_page
from collective_intelligence_overlay.models import Decision, Event, Revocation, UseRequest, now
from collective_intelligence_overlay.overlay import Overlay
from collective_intelligence_overlay.security import verify


def persisted_state(store):
    from sqlalchemy import select

    from collective_intelligence_overlay.storage import metadata

    with store.engine.connect() as conn:
        return {
            table.name: sorted(repr(dict(row)) for row in conn.execute(select(table)).mappings())
            for table in metadata.sorted_tables
        }


def target(cap):
    return CapabilityIdentity(
        issuer=cap.issuer, subject=cap.subject, binding_digest=cap.binding_digest
    )


def test_all_read_views_leave_actual_original_budget_invocation_admission_state_unchanged(
    store, identities, records
):
    from collective_intelligence_overlay.invocations import InvocationStore, Reservation
    from collective_intelligence_overlay.lifecycle import build_handoff, observe_contributions

    cap, evidence = records
    for record in records:
        store.put(identities[record.issuer].sign(record))
    store.set_budget("work", Decimal(7))
    api = InvocationStore(store)
    claim, fresh = api.claim(
        "receiver", "read-only-held", "binding", "a" * 64, {"operation": "fixture"}, Reservation()
    )
    assert fresh
    api.dispatched(claim)
    api.cancel("receiver", "read-only-held")
    held = api.get("receiver", "read-only-held")
    assert held["reservation_state"] == "held"
    decision = Decision(
        id="read-only-admission",
        request=UseRequest(
            receiver="receiver", subject=cap.subject, scope=cap.scope, capability_issuer=cap.issuer
        ),
        outcome="UNKNOWN",
        reasons=("unassessed",),
        policy_digest="1" * 64,
        valid_until=now() + timedelta(minutes=5),
    )
    store.save_decision(decision)
    before = persisted_state(store)
    page = read_lifecycle_page(store, target(cap), caller="receiver")
    view = inspect_lifecycle(page, target(cap))
    observe_contributions(page)
    build_handoff(
        view,
        source_role="GENERATE",
        target_role="VERIFY",
        producer=cap.issuer,
        receiver="receiver",
        contract_identity="cio.lifecycle.view.v1",
    )
    export_originals(
        store, tuple(item.source.reference for item in page.records), caller="receiver"
    )
    for operation in (
        lambda: read_lifecycle_page(store, target(cap), caller="other"),
        lambda: export_originals(store, (page.records[0].source.reference,), caller="other"),
    ):
        with pytest.raises(PermissionError):
            operation()
    assert persisted_state(store) == before
    assert api.get("receiver", "read-only-held") == held


async def test_invalid_assessment_targets_reject_before_actual_qualification_writes(
    store, policy, identities, records
):
    cap = records[0]
    for record in records:
        store.put(identities[record.issuer].sign(record))
    overlay = Overlay(store, policy)
    overlay.observed("producer")
    overlay.observed("verifier")
    request = UseRequest(
        receiver="receiver",
        subject=cap.subject,
        scope=cap.scope,
        semantic_fit="confirmed",
        capability_issuer=cap.issuer,
    )
    before = persisted_state(store)
    with pytest.raises(ValueError, match="duplicate stock target"):
        await assess_stock(
            overlay, (request, request.model_copy(update={"arguments_digest": "2" * 64}))
        )
    assert persisted_state(store) == before


def test_store_inspection_is_owner_read_only_original_payload_bound(store, identities, records):
    cap, evidence = records
    originals = [identities[record.issuer].sign(record) for record in records]
    for original in originals:
        store.put(original)
    decision = Decision(
        request=UseRequest(
            receiver="receiver", subject=cap.subject, scope=cap.scope, capability_issuer=cap.issuer
        ),
        outcome="UNKNOWN",
        reasons=("original-unknown",),
        policy_digest="1" * 64,
        valid_until=now() + timedelta(seconds=30),
    )
    store.save_decision(decision)
    statements = []

    def record_sql(conn, cursor, statement, parameters, context, many):
        statements.append(statement)

    sql_event.listen(store.engine, "before_cursor_execute", record_sql)
    try:
        snap = read_lifecycle_page(store, target(cap), caller="receiver")
        view = inspect_lifecycle(snap, target(cap))
        exported = export_originals(
            store, tuple(source.reference for source in view.sources), caller="receiver"
        )
    finally:
        sql_event.remove(store.engine, "before_cursor_execute", record_sql)
    assert statements and all(
        not s.lstrip().upper().startswith(("INSERT", "UPDATE", "DELETE", "ALTER", "CREATE"))
        for s in statements
    )
    assert snap.context.coverage == Coverage.COMPLETE
    assert view.current_admission == "unassessed"
    assert view.decisions == (decision,)
    for original in originals:
        assert any(item["document"] == original for item in exported["records"])
        assert verify(original, store.principals, require_authority=False) in [
            item.record for item in snap.records
        ]
    assert all(
        source.signature == "unsigned"
        for source in view.sources
        if source.reference.kind == "decision"
    )
    before = len(statements)
    with pytest.raises(PermissionError):
        read_lifecycle_page(store, target(cap), caller="other")
    with pytest.raises(PermissionError):
        export_originals(store, (view.sources[0].reference,), caller="other")
    assert len(statements) == before


def test_pages_retain_prefix_and_late_records_are_not_relabelled(store, identities, records):
    cap = records[0]
    store.put(identities[cap.issuer].sign(cap))
    for index in range(4):
        item = Event(
            id=f"event-{index}",
            issuer="receiver",
            subject=cap.subject,
            action="reuse",
            task_id="fixture",
            attempt_id=str(index),
            correlation_id="fixture",
        )
        store.put(identities["receiver"].sign(item))
    first = read_lifecycle_page(store, target(cap), caller="receiver", limit=4)
    assert first.context.coverage == Coverage.PARTIAL and first.context.record_cursor
    late = Revocation(issuer=cap.issuer, subject=cap.subject, reason="late withdrawal")
    store.put(identities[cap.issuer].sign(late))
    second = read_lifecycle_page(
        store,
        target(cap),
        caller="receiver",
        limit=4,
        record_cursor=first.context.record_cursor,
        decision_cursor=first.context.decision_cursor,
    )
    assert second.context.prefix == first.context.prefix
    assert second.context.cutoff == first.context.cutoff
    assert not any(item.record == late for item in second.records)
    assert second.context.coverage == Coverage.PARTIAL
    current = read_lifecycle_page(store, target(cap), caller="receiver")
    assert any(item.record == late for item in current.records)
    assert current.context.prefix > first.context.prefix


async def test_explicit_assessment_uses_existing_qualification_and_keeps_history(
    store, policy, identities, records
):
    cap, evidence = records
    for item in records:
        store.put(identities[item.issuer].sign(item))
    overlay = Overlay(store, policy)
    overlay.observed("producer")
    overlay.observed("verifier")
    request = UseRequest(
        receiver="receiver",
        subject=cap.subject,
        scope=cap.scope,
        semantic_fit="confirmed",
        capability_issuer=cap.issuer,
    )
    before = len(store.decision_records())
    opening = await assess_stock(overlay, (request,))
    assert len(store.decision_records()) > before
    assert opening.entries[0].availability == "accepted"
    revoked = Revocation(issuer=cap.issuer, subject=cap.subject, reason="withdrawn")
    store.put(identities[cap.issuer].sign(revoked))
    closing = await assess_stock(overlay, (request,))
    assert closing.entries[0].availability == "nonaccepted"
    growth = observe_growth(opening, closing)
    assert growth.reconciled is True and growth.lost_confirmed_availability == (target(cap),)
    assert opening.entries[0].decision.outcome == "ACCEPT"
    assert closing.entries[0].decision.outcome == "REJECT"
    assert json.loads(opening.model_dump_json())["entries"][0]["availability"] == "accepted"
    with pytest.raises(ValueError, match="exact capability"):
        await assess_stock(overlay, (request.model_copy(update={"capability_issuer": None}),))


def test_decision_only_continuation_never_restarts_exhausted_record_page(
    store, identities, records
):
    cap = records[0]
    store.put(identities[cap.issuer].sign(cap))
    for index in range(5):
        store.save_decision(
            Decision(
                id=f"decision-page-{index}",
                request=UseRequest(
                    receiver="receiver",
                    subject=cap.subject,
                    scope=cap.scope,
                    capability_issuer=cap.issuer,
                ),
                outcome="UNKNOWN",
                reasons=(),
                policy_digest="1" * 64,
                valid_until=now() + timedelta(minutes=5),
            )
        )
    pages = []
    rc = dc = None
    for _ in range(4):
        page = read_lifecycle_page(
            store, target(cap), caller="receiver", limit=4, record_cursor=rc, decision_cursor=dc
        )
        pages.append(page)
        rc, dc = page.context.record_cursor, page.context.decision_cursor
        if rc is None and dc is None:
            break
    refs = [item.source.reference for page in pages for item in page.records]
    assert len(refs) == len(set(refs)) == 6
    assert pages[0].context.record_cursor is None and pages[0].context.decision_cursor
    assert len({(page.context.prefix, page.context.cutoff) for page in pages}) == 1
    assert all(page.context.coverage == Coverage.PARTIAL for page in pages)


def test_related_change_during_read_is_inconsistent_and_retains_old_prefix(
    store, identities, records, monkeypatch
):
    cap = records[0]
    store.put(identities[cap.issuer].sign(cap))
    original_page = store.record_page
    inserted = False
    late = Revocation(issuer=cap.issuer, subject=cap.subject, reason="during projection")

    def concurrent_page(*args, **kwargs):
        nonlocal inserted
        result = original_page(*args, **kwargs)
        if not inserted:
            inserted = True
            store.put(identities[cap.issuer].sign(late))
        return result

    monkeypatch.setattr(store, "record_page", concurrent_page)
    page = read_lifecycle_page(store, target(cap), caller="receiver")
    assert page.context.coverage == Coverage.INCONSISTENT
    assert not any(item.record == late for item in page.records)


def test_generation_change_requires_resnapshot_and_exact_export_digest(store, identities, records):
    from sqlalchemy import update

    from collective_intelligence_overlay.storage import feed_state

    cap = records[0]
    store.put(identities[cap.issuer].sign(cap))
    for index in range(3):
        store.put(
            identities["receiver"].sign(
                Event(
                    id=f"generation-{index}",
                    issuer="receiver",
                    subject=cap.subject,
                    action="reuse",
                    task_id="fixture",
                    attempt_id=str(index),
                    correlation_id="fixture",
                )
            )
        )
    first = read_lifecycle_page(store, target(cap), caller="receiver", limit=2)
    bad = first.records[0].source.reference.model_copy(update={"payload_digest": "0" * 64})
    with pytest.raises(ValueError):
        export_originals(store, (bad,), caller="receiver")
    with store.engine.begin() as conn:
        conn.execute(update(feed_state).values(generation="changed-generation"))
    with pytest.raises(ValueError, match="restored generation"):
        read_lifecycle_page(
            store,
            target(cap),
            caller="receiver",
            limit=2,
            record_cursor=first.context.record_cursor,
            decision_cursor=first.context.decision_cursor,
        )


@pytest.mark.parametrize("kind", ["capability", "evidence", "event", "revocation"])
def test_signed_original_missing_clock_survives_store_read_and_exact_export(
    store, identities, records, kind
):
    from securesystemslib.dsse import Envelope

    cap, evidence = records
    original = {
        "capability": cap,
        "evidence": evidence,
        "event": Event(
            issuer="receiver",
            subject=cap.subject,
            action="reuse",
            task_id="clock",
            attempt_id="clock",
            correlation_id="clock",
        ),
        "revocation": Revocation(issuer=cap.issuer, subject=cap.subject, reason="clock test"),
    }[kind]
    signed = identities[original.issuer].sign(original)
    body = json.loads(Envelope.from_dict(signed).payload)
    clock = "occurred_at" if kind == "event" else "created_at"
    body.pop(clock)
    envelope = Envelope(json.dumps(body).encode(), signed["payloadType"], {})
    envelope.sign(identities[original.issuer].signer)
    document = envelope.to_dict()
    assert store.put(document) is True
    observed = read_lifecycle_page(store, target(cap), caller="receiver")
    source = observed.records[0].source
    assert source.occurred_at is None and clock in source.decoder_default_fields
    assert source.signature == "historical_verified" and source.received_at is not None
    exported = export_originals(store, (source.reference,), caller="receiver")
    assert exported["records"][0]["document"] == document
    assert Envelope.from_dict(exported["records"][0]["document"]).payload == envelope.payload
    assert clock not in json.loads(envelope.payload)
