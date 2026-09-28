import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import MetaData, Table, insert, select, update

from collective_intelligence_overlay.accounting import capability_metrics, metrics_page
from collective_intelligence_overlay.models import (
    Cost,
    Decision,
    Event,
    ExecutionReceipt,
    Revocation,
    UseRequest,
    Verdict,
    now,
)
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.security import digest
from collective_intelligence_overlay.storage import feed_state, migrate
from collective_intelligence_overlay.storage import records as record_table


def execution(cap, index, policy, scope=None):
    return Event(
        schema_version="2",
        id=f"use-{index}",
        issuer="receiver",
        subject=cap.subject,
        action="reuse",
        task_id=f"task-{index}",
        attempt_id=f"attempt-{index}",
        correlation_id="batch",
        execution=ExecutionReceipt(
            invocation_id=f"task-{index}",
            caller="receiver",
            resource_owner="receiver",
            capability_issuer=cap.issuer,
            binding_digest=digest(b"binding"),
            arguments_digest=digest(str(index).encode()),
            result_digest=digest(b"result"),
            scope=scope or cap.scope,
            policy_digest=policy,
            state="completed",
            transport="local",
        ),
        costs=(Cost(category="use", status="measured", quantity=Decimal("0.125"), unit="work"),),
    )


def test_metrics_pages_cover_over_one_thousand_and_keep_snapshot_prefix(store, identities, records):
    cap = records[0]
    timestamp = now() - timedelta(hours=1)
    with store.engine.begin() as conn:
        for index in range(1105):
            event = Event(
                id=f"history-{index}",
                issuer="receiver",
                subject=cap.subject,
                action="reuse",
                task_id=f"task-{index}",
                attempt_id=f"attempt-{index}",
                correlation_id="history",
                occurred_at=timestamp + timedelta(seconds=index),
                costs=(
                    Cost(category="use", status="measured", quantity=Decimal("0.125"), unit="work"),
                ),
            )
            store._insert(conn, event, identities["receiver"].sign(event))
    query = RecordQuery(kinds=("event",), since=timestamp, until=now())
    report = metrics_page(store, query, limit=100)
    snapshot = report["snapshot"]
    total = report["events"]
    charged = Decimal(report["costs"][0]["quantity"])
    cursor = report["next_cursor"]
    # An append with backdated occurrence time cannot enter the fixed prefix.
    late = event.model_copy(update={"id": "late"})
    assert store.put(identities["receiver"].sign(late))
    assert not store.put(identities["receiver"].sign(late))
    from collective_intelligence_overlay.queries import RecordCursor

    while cursor:
        report = metrics_page(store, query, cursor=RecordCursor.model_validate(cursor), limit=100)
        assert report["snapshot"]["anchor"] == snapshot["anchor"]
        assert report["snapshot"]["upper"] == snapshot["upper"]
        total += report["events"]
        charged += Decimal(report["costs"][0]["quantity"])
        cursor = report["next_cursor"]
    assert total == 1105 and charged == Decimal("138.125")
    assert report["complete"] and report["aggregation"] == "this_page_only"
    with pytest.raises(ValueError, match="record_page"):
        store.events()  # legacy helper explicitly fails; the new route has no history cutoff


def test_scoped_policy_task_time_queries_and_cursor_misuse(store, identities, records):
    cap = records[0]
    policy = digest(b"policy")
    first = execution(cap, 1, policy)
    second = execution(cap, 2, policy)
    other = execution(cap, 3, digest(b"other"))
    changed_scope = execution(cap, 4, policy, cap.scope.model_copy(update={"task": "other"}))
    for event in (first, second, other, changed_scope):
        store.put(identities["receiver"].sign(event))
    query = RecordQuery(kinds=("event",), scope=cap.scope, policy_digest=policy)
    page = store.record_page(query, limit=1)
    assert page.items == (first,) and page.next_cursor is not None
    again = store.record_page(query, cursor=page.next_cursor, limit=1)
    assert again.items == (second,) and again.next_cursor is None
    assert store.record_page(query.model_copy(update={"task_id": "task-2"})).items == (second,)
    assert store.record_page(query.model_copy(update={"attempt_id": "attempt-1"})).items == (first,)
    with pytest.raises(ValueError, match="mismatch"):
        store.record_page(
            query.model_copy(update={"policy_digest": digest(b"other")}), cursor=page.next_cursor
        )
    with pytest.raises(ValueError, match="mismatch"):
        store.record_page(query, cursor=page.next_cursor.model_copy(update={"owner": "producer"}))
    with pytest.raises(ValueError, match="cannot be skipped"):
        store.record_page(query, byte_limit=1024)
    report = metrics_page(store, query)
    assert report["events"] == 2 and report["scope_unobserved"] == 0
    assert report["execution_states"] == {"completed": 2}
    with store.engine.begin() as conn:
        conn.execute(update(feed_state).values(generation="restored"))
    with pytest.raises(ValueError, match="restored"):
        store.record_page(query, cursor=page.next_cursor)


async def test_historical_check_is_not_current_acceptance_and_receipt_latency(
    overlay, identities, records
):
    old_cap, old_evidence = records
    subject = old_cap.subject.model_copy(update={"id": "observed-lifecycle"})
    cap = old_cap.model_copy(
        update={"schema_version": "2", "subject": subject, "binding_digest": digest(b"binding")}
    )
    evidence = old_evidence.model_copy(
        update={
            "schema_version": "2",
            "id": "observed-check",
            "subject": subject,
            "binding_digest": cap.binding_digest,
        }
    )
    request = UseRequest(
        receiver="receiver",
        capability_issuer=cap.issuer,
        subject=subject,
        scope=cap.scope,
        binding_digest=cap.binding_digest,
        semantic_fit="confirmed",
    )
    overlay.store.put(identities["producer"].sign(cap))
    before = await capability_metrics(overlay, (request,))
    assert before["historically_checked_targets"] == 0
    assert before["currently_accepted_targets"] == 0
    assert before["verification_backlog"] == 1
    assert before["targets"][0]["first_verification_seconds"] is None
    overlay.store.put(identities["verifier"].sign(evidence))
    foreign_policy_use = execution(cap, 9, digest(b"different-policy"))
    overlay.store.put(identities["receiver"].sign(foreign_policy_use))
    other_policy = await capability_metrics(overlay, (request,))
    assert other_policy["targets"][0]["first_reuse_seconds"] is None
    assert other_policy["historical_reuse_policy_digest"] == overlay.policy.digest
    reuse = execution(cap, 10, overlay.policy.digest)
    overlay.store.put(identities["receiver"].sign(reuse))
    checked = await capability_metrics(overlay, (request,))
    assert checked["historically_checked_targets"] == 1
    assert checked["currently_accepted_targets"] == 1
    assert checked["targets"][0]["first_verification_seconds"] >= 0
    assert checked["targets"][0]["first_reuse_seconds"] >= 0
    unknown = await capability_metrics(
        overlay, (request.model_copy(update={"semantic_fit": "unknown"}),)
    )
    assert unknown["currently_accepted_targets"] == 0
    assert unknown["historically_checked_targets"] == 1
    overlay.store.put(
        identities["producer"].sign(
            Revocation(issuer="producer", subject=subject, reason="withdrawn")
        )
    )
    revoked = await capability_metrics(overlay, (request,))
    assert revoked["currently_accepted_targets"] == 0
    assert revoked["historically_checked_targets"] == 1
    assert revoked["targets"][0]["decision"]["outcome"] == "REJECT"
    with pytest.raises(ValueError, match="duplicate"):
        await capability_metrics(overlay, (request, request))


async def test_obligation_and_unknown_ages_use_original_local_receipts(
    overlay, identities, records, monkeypatch
):
    import collective_intelligence_overlay.accounting as accounting

    cap, evidence = records
    subject = cap.subject.model_copy(update={"id": "aged-observations"})
    cap = cap.model_copy(update={"subject": subject, "obligations": ("review source conditions",)})
    evidence = evidence.model_copy(
        update={
            "id": "aged-unknown",
            "subject": subject,
            "verdict": Verdict.UNKNOWN,
            "obligations": ("collect another observation",),
        }
    )
    overlay.store.put(identities[cap.issuer].sign(cap))
    signed = identities[evidence.issuer].sign(evidence)
    overlay.store.put(signed)
    request = UseRequest(
        receiver="receiver", subject=cap.subject, scope=cap.scope, semantic_fit="confirmed"
    )
    observation_time = now() + timedelta(minutes=2)
    monkeypatch.setattr(accounting, "now", lambda: observation_time)
    first = await capability_metrics(overlay, (request,))
    target = first["targets"][0]
    assert first["unresolved_obligations"] == 2
    assert first["unknown_evidence_observations"] == 1
    assert target["candidate_observed_age_seconds"] >= 120
    assert all(item["observed_age_seconds"] >= 120 for item in target["unresolved_obligations"])
    original = target["unknown_evidence"][0]
    overlay.store.put(signed)  # delivery replay must not reset local observation age
    observation_time += timedelta(seconds=30)
    replay = await capability_metrics(overlay, (request,))
    repeated = replay["targets"][0]["unknown_evidence"][0]
    assert repeated["observed_at"] == original["observed_at"]
    assert repeated["observed_age_seconds"] == pytest.approx(
        original["observed_age_seconds"] + 30, abs=1e-9
    )
    overlay.store.put(
        identities[evidence.issuer].sign(
            Revocation(
                issuer=evidence.issuer,
                subject=cap.subject,
                evidence_id=evidence.id,
                reason="observation withdrawn",
            )
        )
    )
    withdrawn = await capability_metrics(overlay, (request,))
    assert withdrawn["unknown_evidence_observations"] == 0
    assert withdrawn["unresolved_obligations"] == 1


async def test_local_decision_inspection_uses_stable_pages_without_affecting_revisions(
    overlay, records
):
    cap = records[0]
    request = UseRequest(
        receiver="receiver", subject=cap.subject, scope=cap.scope, semantic_fit="confirmed"
    )
    first = await overlay.qualify(request)
    second = await overlay.qualify(request.model_copy(update={"semantic_fit": "unknown"}))
    query = RecordQuery(kinds=("decision",), scope=cap.scope, policy_digest=overlay.policy.digest)
    page = overlay.store.record_page(query, limit=1)
    assert page.items == (first,) and page.next_cursor
    third = await overlay.qualify(request)
    assert third.revisions == first.revisions
    last = overlay.store.record_page(query, cursor=page.next_cursor)
    assert last.items == (second,) and last.next_cursor is None
    assert len(overlay.store.record_page(query).items) == 3


async def test_cli_inspection_cursor_and_exit_status(
    overlay, records, identities, monkeypatch, tmp_path, capsys
):
    from collective_intelligence_overlay.cli import main

    request = UseRequest(
        receiver="receiver",
        subject=records[0].subject,
        scope=records[0].scope,
        semantic_fit="confirmed",
    )
    await overlay.qualify(request)
    await overlay.qualify(request)
    monkeypatch.setattr(
        "collective_intelligence_overlay.cli.load_config",
        lambda _: SimpleNamespace(runtime=lambda: (identities["receiver"], overlay)),
    )
    args = [
        "collective-intelligence-overlay",
        "inspect",
        "--config",
        "owner.json",
        "decision",
        "--page-size",
        "1",
    ]
    monkeypatch.setattr("sys.argv", args)
    assert main() == 3
    first = json.loads(capsys.readouterr().out)
    assert len(first["items"]) == 1 and first["next_cursor"]
    cursor = tmp_path / "cursor.json"
    cursor.write_text(json.dumps(first["next_cursor"]), encoding="utf-8")
    monkeypatch.setattr("sys.argv", args + ["--cursor-file", str(cursor)])
    assert main() == 0
    last = json.loads(capsys.readouterr().out)
    assert len(last["items"]) == 1 and last["next_cursor"] is None
    assert first["items"][0]["id"] != last["items"][0]["id"]


def test_inspection_upgrade_backfills_existing_receipts_and_decisions(
    unmigrated_store, identities, records
):
    store = unmigrated_store
    migrate(store.engine, "0006")
    cap = records[0]
    event = execution(cap, 1, digest(b"policy"))
    envelope = identities["receiver"].sign(event)
    request = UseRequest(receiver="receiver", subject=cap.subject, scope=cap.scope)
    decision = Decision(
        request=request,
        outcome="UNKNOWN",
        reasons=("not_checked",),
        policy_digest=digest(b"policy"),
    )
    old_records = Table("records", MetaData(), autoload_with=store.engine)
    old_decisions = Table("decisions", MetaData(), autoload_with=store.engine)
    with store.engine.begin() as conn:
        conn.execute(
            insert(old_records).values(
                kind="event",
                issuer=event.issuer,
                record_id=event.id,
                body=event.model_dump(mode="json"),
                envelope=envelope,
                sequence=1,
                received_at=now(),
            )
        )
        conn.execute(
            insert(old_decisions).values(id=decision.id, body=decision.model_dump(mode="json"))
        )
        conn.execute(update(feed_state).values(sequence=1))
    migrate(store.engine)
    query = RecordQuery(kinds=("event",), scope=cap.scope, policy_digest=decision.policy_digest)
    assert store.record_page(query).items == (event,)
    assert store.record_page(query.model_copy(update={"kinds": ("decision",)})).items == (decision,)
    with store.engine.connect() as conn:
        assert conn.execute(select(record_table.c.envelope)).scalar_one() == envelope
