from uuid import uuid4

import jwt
import pytest
from sqlalchemy import create_engine, event, text, update

from collective_intelligence_overlay.models import Revocation, UseRequest
from collective_intelligence_overlay.overlay import Overlay
from collective_intelligence_overlay.storage import Store, feed_state, migrate, projection_digest
from collective_intelligence_overlay.synchronization import (
    Feed,
    FeedFilter,
    Receiver,
    ResnapshotRequired,
    verify_page,
)


@pytest.fixture
def source_store(store):
    name = "cio_feed_" + uuid4().hex
    admin = create_engine(store.engine.url, isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        conn.execute(text(f'CREATE DATABASE "{name}"'))
    source = Store(
        store.engine.url.set(database=name).render_as_string(hide_password=False),
        "producer",
        store.principals,
    )
    migrate(source.engine)
    try:
        yield source
    finally:
        source.close()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE "{name}" WITH (FORCE)'))
        admin.dispose()


def prepare(store, identities, records):
    cap, evidence = records
    own = [
        cap.model_copy(update={"issuer": "receiver"}),
        evidence.model_copy(update={"issuer": "receiver"}),
    ]
    for record in own:
        store.put(identities["receiver"].sign(record))
    return Feed(store, identities["receiver"]), own


def test_paged_snapshot_delta_and_final_withdrawal(store, identities, records):
    feed, own = prepare(store, identities, records)
    filter = FeedFilter()
    first = feed.page("producer", filter, limit=1)
    claims = verify_page(first, store.principals["receiver"], "receiver", "producer", filter)
    assert not claims["complete"]
    revocation = Revocation(issuer="receiver", subject=own[0].subject, reason="withdrawn")
    store.put(identities["receiver"].sign(revocation))
    second = feed.page("producer", filter, cursor=first.next_cursor, limit=1)
    finished = verify_page(second, store.principals["receiver"], "receiver", "producer", filter)
    assert finished["complete"] and finished["upper"] == 2
    assert finished["anchor"] == claims["anchor"]
    delta = feed.page("producer", filter, since=2, generation=finished["generation"])
    final = verify_page(delta, store.principals["receiver"], "receiver", "producer", filter)
    assert final["complete"] and len(delta.records) == 1
    assert final["upper"] == 3
    empty = feed.page("producer", filter, since=3, generation=final["generation"])
    assert not empty.records and empty.next_cursor is None
    # A repeated old snapshot keeps its original anchor instead of extending freshness.
    replay = feed.page("producer", filter, cursor=first.next_cursor, limit=1)
    assert (
        verify_page(replay, store.principals["receiver"], "receiver", "producer", filter)["anchor"]
        == claims["anchor"]
    )


def test_cursor_is_receiver_filter_and_generation_bound(store, identities, records):
    feed, own = prepare(store, identities, records)
    page = feed.page("producer", FeedFilter(), limit=1)
    with pytest.raises(jwt.InvalidAudienceError):
        feed.page("other", FeedFilter(), cursor=page.next_cursor)
    with pytest.raises(ValueError, match="filter"):
        feed.page("producer", FeedFilter(subjects=(own[0].subject,)), cursor=page.next_cursor)
    with store.engine.begin() as conn:
        conn.execute(update(feed_state).values(generation="restored-generation"))
    with pytest.raises(ResnapshotRequired):
        feed.page("producer", FeedFilter(), cursor=page.next_cursor)


def test_tampered_page_and_oversized_record_cannot_be_skipped(store, identities, records):
    feed, own = prepare(store, identities, records)
    page = feed.page("producer", FeedFilter(), limit=1)
    modified = page.model_copy(update={"records": []})
    with pytest.raises(ValueError, match="record set"):
        verify_page(modified, store.principals["receiver"], "receiver", "producer", FeedFilter())
    large = own[0].model_copy(
        update={
            "subject": own[0].subject.model_copy(update={"id": "large"}),
            "provenance": "x" * 12000,
        }
    )
    store.put(identities["receiver"].sign(large))
    with pytest.raises(ValueError, match="cannot skip"):
        feed.page("producer", FeedFilter(), byte_limit=8192)


def test_receiver_restart_duplicate_and_final_page_freshness(
    source_store, store, identities, records
):
    cap, evidence = records
    evidence = evidence.model_copy(update={"issuer": "producer"})
    revocation = Revocation(issuer="producer", subject=cap.subject, reason="withdrawn")
    for record in (cap, evidence, revocation):
        source_store.put(identities["producer"].sign(record))
    feed = Feed(source_store, identities["producer"])
    receiver = Receiver(store)
    filter = FeedFilter()
    first = feed.page("receiver", filter, limit=1)
    assert receiver.apply("producer", filter, first)
    assert receiver.freshness("producer", filter) is None
    assert store.record_count() == 1
    assert not receiver.apply("producer", filter, first)
    assert store.record_count() == 1
    # New Store/Receiver instances reconstruct continuation exclusively from DB.
    restarted_store = Store(
        store.engine.url.render_as_string(hide_password=False), store.owner, store.principals
    )
    try:
        restarted = Receiver(restarted_store)
        pending = restarted.checkpoint("producer", filter)
        second = feed.page("receiver", filter, cursor=pending["cursor"], limit=1)
        assert restarted.apply("producer", filter, second)
        assert restarted.freshness("producer", filter) is None
        third = feed.page("receiver", filter, cursor=second.next_cursor, limit=1)
        assert restarted.apply("producer", filter, third)
        assert len(store.revocations()) == 1
        anchor = restarted.freshness("producer", filter)
        assert anchor == pending["anchor"]
        assert not restarted.apply("producer", filter, third)
        assert restarted.freshness("producer", filter) == anchor
        restarted.restart("producer", filter)
        assert restarted.freshness("producer", filter) is None
        assert len(store.revocations()) == 1  # restarting transport cannot resurrect capability
    finally:
        restarted_store.close()


def test_bad_signature_does_not_advance_checkpoint(source_store, store, identities, records):
    source_store.put(identities["producer"].sign(records[0]))
    feed = Feed(source_store, identities["producer"])
    page = feed.page("receiver", FeedFilter())
    claims = verify_page(page, store.principals["producer"], "producer", "receiver", FeedFilter())
    broken = page.model_copy(deep=True)
    broken.records[0]["signatures"][0]["sig"] = "AAAA"
    forged_receipt = feed._token({**claims, "records_hash": projection_digest(broken.records)})
    broken = broken.model_copy(update={"receipt": forged_receipt})
    from securesystemslib.exceptions import VerificationError

    with pytest.raises(VerificationError):
        Receiver(store).apply("producer", FeedFilter(), broken)
    assert Receiver(store).checkpoint("producer", FeedFilter()) is None
    assert store.record_count() == 0


def test_import_and_cursor_commit_are_atomic(source_store, store, identities, records):
    source_store.put(identities["producer"].sign(records[0]))
    page = Feed(source_store, identities["producer"]).page("receiver", FeedFilter())
    receiver = Receiver(store)

    def crash(conn, cursor, statement, parameters, context, executemany):
        if statement.startswith("INSERT INTO records"):
            raise RuntimeError("injected crash before checkpoint commit")

    event.listen(store.engine, "after_cursor_execute", crash)
    try:
        with pytest.raises(RuntimeError, match="injected crash"):
            receiver.apply("producer", FeedFilter(), page)
    finally:
        event.remove(store.engine, "after_cursor_execute", crash)
    assert store.record_count() == 0
    assert receiver.checkpoint("producer", FeedFilter()) is None
    assert receiver.apply("producer", FeedFilter(), page)


async def test_incomplete_delta_blocks_admission_until_last_page_withdrawal(
    source_store,
    store,
    identities,
    records,
    policy,
):
    cap, evidence = records
    source_store.put(identities["producer"].sign(cap))
    source_store.put(identities["verifier"].sign(evidence))
    verifier_store = Store(
        source_store.engine.url.render_as_string(hide_password=False),
        "verifier",
        source_store.principals,
    )
    receiver = Receiver(store)
    producer = Feed(source_store, identities["producer"])
    verifier = Feed(verifier_store, identities["verifier"])
    filter = FeedFilter()
    try:
        for source, feed in (("producer", producer), ("verifier", verifier)):
            receiver.apply(source, filter, feed.page("receiver", filter))
        overlay = Overlay(store, policy, persistent_sources=True)
        request = UseRequest(
            receiver="receiver", subject=cap.subject, scope=cap.scope, semantic_fit="confirmed"
        )
        assert (await overlay.qualify(request)).outcome == "ACCEPT"
        with pytest.raises(ValueError, match="committed synchronization"):
            overlay.observed("producer")
        unrelated = cap.model_copy(
            update={"subject": cap.subject.model_copy(update={"id": "noise"})}
        )
        source_store.put(identities["producer"].sign(unrelated))
        source_store.put(
            identities["producer"].sign(
                Revocation(issuer="producer", subject=cap.subject, reason="last-page withdrawal")
            )
        )
        receiver.begin("producer", filter)
        assert (await overlay.qualify(request)).outcome == "UNKNOWN"
        checkpoint = receiver.checkpoint("producer", filter)
        first = producer.page(
            "receiver",
            filter,
            since=checkpoint["through"],
            generation=checkpoint["generation"],
            limit=1,
        )
        receiver.apply("producer", filter, first)
        assert (
            await Overlay(store, policy, persistent_sources=True).qualify(request)
        ).outcome == "UNKNOWN"
        receiver.apply(
            "producer", filter, producer.page("receiver", filter, cursor=first.next_cursor, limit=1)
        )
        assert (await overlay.qualify(request)).outcome == "REJECT"
    finally:
        verifier_store.close()
