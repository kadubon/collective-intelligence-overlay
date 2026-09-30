import asyncio
import os
from datetime import timedelta
from urllib.parse import urlsplit

import httpx
import pytest
import uvicorn
from a2a.utils.errors import A2AError
from sqlalchemy import event, func, select

from collective_intelligence_overlay import storage
from collective_intelligence_overlay.adapters.a2a import application, send, synchronize
from collective_intelligence_overlay.demo import initialize
from collective_intelligence_overlay.models import (
    Capability,
    Evidence,
    Scope,
    Subject,
    UseRequest,
    now,
)
from collective_intelligence_overlay.peer import PeerService
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.security import digest, verify
from collective_intelligence_overlay.synchronization import Feed, FeedFilter, Receiver

COUNTS = tuple(int(n) for n in os.getenv("CIO_REVOKE_COUNTS", "1000,1001,10000").split(","))


@pytest.mark.parametrize("total", COUNTS)
async def test_cio_030_01_authenticated_exact_revoke_with_mixed_capability_history(
    tmp_path, policy, monkeypatch, total
):
    url = os.environ.get("CIO_TEST_DATABASE_URL")
    if not url:
        pytest.skip("real PostgreSQL required")
    configs = initialize(tmp_path / "revoke", url, policy.binary)
    service = PeerService(configs["producer"])
    foreign = {name: config.runtime() for name, config in configs.items() if name != "producer"}
    identities = {name: pair[0] for name, pair in foreign.items()}
    identities["producer"] = service.identity
    store = service.overlay.store
    target = Capability(
        schema_version="2",
        binding_digest=digest(b"target-binding"),
        issuer="producer",
        subject=Subject(id="owned-target", version="1", digest=digest(b"target")),
        scope=Scope(task="revoke", input_contract="in", output_contract="out", environment={}),
        entrypoint="target",
        claim="exact-target",
        license="Apache-2.0",
        provenance="installed regression fixture",
        classification="declared-new",
        expires_at=now() + timedelta(hours=1),
    )
    store.put(service.identity.sign(target))
    dependent = target.model_copy(
        update={
            "subject": Subject(id="dependent", version="1", digest=digest(b"dependent")),
            "binding_digest": digest(b"dependent-binding"),
            "dependencies": (target.subject,),
            "dependency_issuers": ("producer",),
        }
    )
    store.put(service.identity.sign(dependent))
    pending = []
    for index in range(total - 2):
        issuer = ("receiver", "verifier", "producer")[index % 3]
        record = target.model_copy(
            update={
                "issuer": issuer,
                "schema_version": "1" if index % 2 else "2",
                "binding_digest": None if index % 2 else digest(f"binding-{index}".encode()),
                "subject": target.subject
                if index == 0
                else Subject(
                    id=target.subject.id if index % 5 == 0 else f"history-{index}",
                    version=str(index + 2),
                    digest=digest(str(index).encode()),
                ),
            }
        )
        envelope = identities[issuer].sign(record)
        pending.append((verify(envelope, store.principals), envelope))
        if len(pending) == 100 or index == total - 3:
            with store.engine.begin() as conn:
                for checked, signed in pending:
                    store._insert(conn, checked, signed)
            pending.clear()
    with store.engine.connect() as conn:
        assert (
            conn.execute(
                select(func.count())
                .select_from(storage.records)
                .where(storage.records.c.kind == "capability")
            ).scalar_one()
            == total
        )
    receiver_identity, receiver_overlay = foreign["receiver"]
    verifier_identity, verifier_overlay = foreign["verifier"]
    for cap in (target, dependent):
        evidence = Evidence(
            schema_version="2",
            binding_digest=cap.binding_digest,
            issuer="verifier",
            subject=cap.subject,
            scope=cap.scope,
            claim=cap.claim,
            receivers=("receiver",),
            verdict="PASS",
            method="reference-check",
            verifier_version="1",
            artifact_digest=digest(b"fixture-check"),
            expires_at=target.expires_at,
        )
        verifier_overlay.store.put(verifier_identity.sign(evidence))
    filter = FeedFilter(subjects=(target.subject, dependent.subject))
    Receiver(receiver_overlay.store).apply(
        "verifier",
        filter,
        Feed(verifier_overlay.store, verifier_identity).page("receiver", filter),
    )
    signatures, returned = [], []
    original_verify = storage.verify

    def measured_verify(envelope, principals):
        signatures.append(1)
        return original_verify(envelope, principals)

    def measured_rows(conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            returned.append(max(cursor.rowcount, 0))

    monkeypatch.setattr(storage, "verify", measured_verify)
    event.listen(store.engine, "after_cursor_execute", measured_rows)
    server = uvicorn.Server(
        uvicorn.Config(
            application(configs["producer"], service.handle),
            host="127.0.0.1",
            port=urlsplit(configs["producer"].url).port,
            log_level="critical",
            access_log=False,
        )
    )
    serving = asyncio.create_task(server.serve())
    try:
        for _ in range(100):
            if server.started:
                break
            await asyncio.sleep(0.05)
        assert server.started
        await synchronize(
            configs["receiver"],
            receiver_identity,
            receiver_overlay.store,
            "producer",
            filter_data=filter.model_dump(mode="json"),
        )
        requests = tuple(
            UseRequest(
                receiver="receiver",
                capability_issuer="producer",
                subject=cap.subject,
                scope=cap.scope,
                binding_digest=cap.binding_digest,
                semantic_fit="confirmed",
            )
            for cap in (target, dependent)
        )
        assert [(await receiver_overlay.qualify(req)).outcome for req in requests] == [
            "ACCEPT",
            "ACCEPT",
        ]
        async with httpx.AsyncClient(trust_env=False) as http:
            unauthenticated = await http.post(configs["producer"].url, json={})
            assert unauthenticated.status_code == 400
        for caller, subject in (
            ("receiver", target.subject),
            ("producer", target.subject.model_copy(update={"id": "missing"})),
            ("producer", target.subject.model_copy(update={"digest": digest(b"different")})),
            (
                "producer",
                Subject(id="history-1", version="3", digest=digest(b"1")),
            ),
        ):
            with pytest.raises(A2AError, match="owner operation|can only revoke own"):
                await send(
                    configs[caller],
                    identities[caller],
                    "producer",
                    {
                        "operation": "revoke",
                        "subject": subject.model_dump(mode="json"),
                        "reason": "unauthorized",
                    },
                )
        assert not store.record_page(RecordQuery(kinds=("revocation",))).items
        signatures.clear()
        returned.clear()
        result = await send(
            configs["producer"],
            service.identity,
            "producer",
            {
                "operation": "revoke",
                "subject": target.subject.model_dump(mode="json"),
                "reason": "withdrawn",
            },
        )
        assert verify(result["envelope"], store.principals).subject == target.subject
        assert len(signatures) <= 4
        assert sum(returned) <= 16
        print(
            {
                "capabilities": total,
                "revoke_signature_checks": len(signatures),
                "select_statements": len(returned),
                "returned_rows": sum(returned),
            }
        )
        assert store.record_page(
            RecordQuery(kinds=("revocation",), issuer="producer", subject=target.subject), limit=1
        ).items
        await synchronize(
            configs["receiver"],
            receiver_identity,
            receiver_overlay.store,
            "producer",
            filter_data=filter.model_dump(mode="json"),
        )
        decisions = [(await receiver_overlay.qualify(req)) for req in requests]
        assert [decision.outcome for decision in decisions] == ["REJECT", "REJECT"]
        assert "known_revocation" in decisions[0].reasons
        assert "dependency_rejected" in decisions[1].reasons
    finally:
        event.remove(store.engine, "after_cursor_execute", measured_rows)
        server.should_exit = True
        await asyncio.wait_for(serving, 10)
        store.close()
        for _, overlay in foreign.values():
            overlay.store.close()
