import pytest
from sqlalchemy import insert, select

from collective_intelligence_overlay.models import Revocation, now
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.storage import feed_state, subject_key
from collective_intelligence_overlay.synchronization import (
    Feed,
    FeedFilter,
    Receiver,
    ResnapshotRequired,
    checkpoints,
)


def test_restore_rotation_invalidates_cursors_and_freshness_preserves_records(
    store, identities, records
):
    from collective_intelligence_overlay.storage import records as table

    cap, _ = records
    own = cap.model_copy(update={"issuer": "receiver"})
    revoked = Revocation(issuer="receiver", subject=own.subject, reason="retired")
    for record in (own, revoked):
        store.put(identities["receiver"].sign(record))
    filter = FeedFilter()
    feed = Feed(store, identities["receiver"])
    page = feed.page("producer", filter, limit=1)
    assert page.next_cursor
    inspection = store.record_page(RecordQuery(), limit=1)
    assert inspection.next_cursor
    with store.engine.begin() as conn:
        conn.execute(
            insert(checkpoints).values(
                source="producer",
                filter_digest=filter.digest,
                generation="old",
                through=2,
                upper=2,
                anchor=now(),
                cursor=None,
                complete=True,
                last_receipt="a" * 64,
                subjects=[],
            )
        )
        original = conn.execute(select(table)).mappings().all()
        old_generation = conn.execute(select(feed_state.c.generation)).scalar_one()
    key = subject_key(own.subject)
    assert Receiver(store).observations({key})["producer:" + key] is not None
    before = store.revisions({key})
    generation = store.reset_sync_after_restore()
    assert generation != old_generation
    assert Receiver(store).observations({key})["producer:" + key] is None
    assert store.revisions({key})[key] == before[key] + 1
    with pytest.raises(ResnapshotRequired):
        feed.page("producer", filter, cursor=page.next_cursor)
    with pytest.raises(ValueError, match="generation"):
        store.record_page(RecordQuery(), cursor=inspection.next_cursor)
    with store.engine.connect() as conn:
        assert conn.execute(select(table)).mappings().all() == original
        gate = conn.execute(select(feed_state)).mappings().one()
        assert gate["restored_sequence"] == max(row["sequence"] for row in original)
    # Repeated recovery is safe for immutable history, and rotates again.
    assert store.reset_sync_after_restore() != generation
    assert len(store.revocations()) == 1


def test_restore_cli_uses_store_recovery(store, policy, identities, monkeypatch, capsys):
    import json
    from types import SimpleNamespace

    from collective_intelligence_overlay import cli
    from collective_intelligence_overlay.overlay import Overlay

    configured = SimpleNamespace(runtime=lambda: (identities["receiver"], Overlay(store, policy)))
    monkeypatch.setattr(cli, "load_config", lambda path: configured)
    monkeypatch.setattr(
        "sys.argv",
        ["collective-intelligence-overlay", "restore-state", "--config", "operator.json"],
    )
    assert cli.main() == 0
    result = json.loads(capsys.readouterr().out)
    assert result["freshness"] == "invalidated"
    with store.engine.connect() as conn:
        assert conn.execute(select(feed_state.c.generation)).scalar_one() == result["generation"]
