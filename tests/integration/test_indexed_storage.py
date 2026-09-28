import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Event as ThreadEvent

import pytest
from sqlalchemy import select

from collective_intelligence_overlay.models import Event, Subject, UseRequest
from collective_intelligence_overlay.storage import feed_state, subject_key
from collective_intelligence_overlay.storage import records as record_table


def request(cap):
    return UseRequest(
        receiver="receiver", subject=cap.subject, scope=cap.scope, semantic_fit="confirmed"
    )


async def test_unrelated_history_does_not_load_or_verify_all_records(
    overlay,
    identities,
    records,
    monkeypatch,
):
    import collective_intelligence_overlay.storage as storage

    cap, _ = records
    with overlay.store.engine.begin() as conn:
        for index in range(1001):
            unrelated = cap.model_copy(
                update={
                    "subject": Subject(id=f"unrelated-{index}", version="1", digest=f"{index:064x}")
                }
            )
            overlay.store._insert(conn, unrelated, identities["producer"].sign(unrelated))
    verified = []
    original = storage.verify

    def counted(envelope, principals):
        result = original(envelope, principals)
        verified.append(result)
        return result

    monkeypatch.setattr(storage, "verify", counted)
    decision = await overlay.qualify(request(cap))
    assert decision.outcome == "ACCEPT"
    assert len(verified) == 2
    assert len(decision.revisions) == 1
    with pytest.raises(ValueError, match="record limit"):
        overlay.store.capabilities()  # old bounded list API is not the admission path


async def test_cost_event_during_check_does_not_invalidate_subject(
    overlay,
    identities,
    records,
    monkeypatch,
):
    cap, _ = records
    original = overlay.policy.decide

    async def decide(facts):
        result = await original(facts)
        event = Event(
            issuer="receiver",
            subject=cap.subject,
            action="reuse",
            task_id="unrelated-cost",
            attempt_id="1",
            correlation_id="unrelated-cost",
        )
        await asyncio.to_thread(overlay.store.put, identities["receiver"].sign(event))
        return result

    before = overlay.store.revisions({subject_key(cap.subject)})
    monkeypatch.setattr(overlay.policy, "decide", decide)
    assert (await overlay.qualify(request(cap))).outcome == "ACCEPT"
    assert overlay.store.revisions(set(before)) == before


def test_transactional_prefix_serializes_writers_and_rollbacks(store, identities, records):
    cap, evidence = records
    started = ThreadEvent()
    with ThreadPoolExecutor(max_workers=1) as pool:
        with store.engine.connect() as first:
            transaction = first.begin()
            store._insert(first, cap, identities["producer"].sign(cap))

            def second():
                started.set()
                return store.put(identities["verifier"].sign(evidence))

            pending = pool.submit(second)
            assert started.wait(2)
            # First writer has allocated sequence 1 but has not committed. The
            # second cannot publish 2 before it. Readers see the old complete prefix.
            with store.engine.connect() as reader:
                assert reader.execute(select(feed_state.c.sequence)).scalar_one() == 0
                assert reader.execute(select(record_table.c.sequence)).all() == []
            assert not pending.done()
            transaction.rollback()
        assert pending.result(timeout=5)
    with store.engine.connect() as reader:
        assert reader.execute(select(feed_state.c.sequence)).scalar_one() == 1
        assert reader.execute(select(record_table.c.kind, record_table.c.sequence)).all() == [
            ("evidence", 1)
        ]
    assert store.put(identities["producer"].sign(cap))
    assert not store.put(identities["producer"].sign(cap))
    with store.engine.connect() as reader:
        assert reader.execute(select(feed_state.c.sequence)).scalar_one() == 2


async def test_slow_database_snapshot_does_not_block_event_loop(overlay, records, monkeypatch):
    import time

    original = overlay.store.admission_snapshot
    started = ThreadEvent()

    def slow(*args):
        started.set()
        time.sleep(0.15)
        return original(*args)

    monkeypatch.setattr(overlay.store, "admission_snapshot", slow)
    task = asyncio.create_task(overlay.qualify(request(records[0])))
    await asyncio.sleep(0.03)
    assert started.is_set()
    assert not task.done()
    assert (await task).outcome == "ACCEPT"
