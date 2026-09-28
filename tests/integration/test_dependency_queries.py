import pytest
from sqlalchemy import MetaData, Table, insert, select

from collective_intelligence_overlay.models import Subject
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.storage import migrate
from collective_intelligence_overlay.storage import records as record_table


def test_reverse_dependencies_exact_issuers_and_legacy_pages(store, identities, records):
    cap, _ = records
    for index, issuer in enumerate(("producer", "other", None)):
        parent = cap.model_copy(
            update={
                "subject": Subject(id=f"parent-{index}", version="1", digest=f"{index:064x}"),
                "dependencies": (cap.subject,),
                "dependency_issuers": (issuer,) if issuer else (),
                "schema_version": "2" if issuer else "1",
                "binding_digest": "b" * 64 if issuer else None,
            }
        )
        store.put(identities["producer"].sign(parent))
    query = RecordQuery(kinds=("capability",), depends_on=cap.subject, dependency_issuer="producer")
    exact = store.record_page(query)
    assert [r.subject.id for r in exact.items] == ["parent-0"]
    expanded = query.model_copy(update={"include_legacy_dependencies": True})
    first = store.record_page(expanded, limit=1)
    assert first.next_cursor
    second = store.record_page(expanded, cursor=first.next_cursor, limit=1)
    assert [r.subject.id for r in (*first.items, *second.items)] == ["parent-0", "parent-2"]
    assert second.next_cursor is None
    assert second.items[0].dependency_issuers == ()
    with pytest.raises(ValueError, match="filter"):
        store.record_page(query, cursor=first.next_cursor)
    wrong_digest = cap.subject.model_copy(update={"digest": "f" * 64})
    assert store.record_page(query.model_copy(update={"depends_on": wrong_digest})).items == ()
    # Forward edges come from the authenticated exact parent, with no projection
    # treated as evidence that its children are admissible.
    forward = store.record_page(
        RecordQuery(
            kinds=("capability",),
            issuer="producer",
            subject=exact.items[0].subject,
        )
    )
    assert forward.items[0].dependencies == (cap.subject,)
    assert forward.items[0].dependency_issuers == ("producer",)


def test_dependency_projection_backfill_preserves_payload(unmigrated_store, identities, records):
    store = unmigrated_store
    cap, _ = records
    parent = cap.model_copy(
        update={
            "subject": Subject(id="old-parent", version="1", digest="d" * 64),
            "dependencies": (cap.subject,),
        }
    )
    migrate(store.engine, "0007")
    old = Table("records", MetaData(), autoload_with=store.engine)
    envelope = identities["producer"].sign(parent)
    import base64
    import json

    body = json.loads(base64.b64decode(envelope["payload"]))
    with store.engine.begin() as conn:
        conn.execute(
            insert(old).values(
                kind="capability",
                issuer="producer",
                record_id=parent.subject.key,
                body=body,
                envelope=envelope,
                received_at=parent.created_at,
                sequence=1,
            )
        )
    migrate(store.engine)
    migrate(store.engine)
    with store.engine.connect() as conn:
        row = conn.execute(select(record_table)).mappings().one()
        assert row["body"] == body
        assert row["envelope"] == envelope
        assert row["dependency_refs"][0]["issuer"] is None
