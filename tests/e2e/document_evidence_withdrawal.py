"""Quiescent independent evidence withdrawal and explicit fresh read-only check."""

import asyncio
import json

from document_recovery_protocol import originals

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.bindings import Binding
from collective_intelligence_overlay.models import Evidence, Revocation
from collective_intelligence_overlay.operations import OwnerLock
from collective_intelligence_overlay.queries import RecordQuery


async def run(configs, identities, mesh, start, stop, call, sync, target, checker, reuse, root):
    target = Binding.model_validate(target)
    request = {
        "receiver": "receiver",
        "capability_issuer": target.issuer,
        "subject": target.subject.model_dump(mode="json"),
        "scope": target.scope.model_dump(mode="json"),
        "binding_digest": target.digest,
        "semantic_fit": "confirmed",
    }
    assert (await call("receiver", operation="qualify", request=request))["decision"][
        "outcome"
    ] == "ACCEPT"
    before = {
        owner: await asyncio.to_thread(originals, config) for owner, config in configs.items()
    }
    effects = mesh.mcp_audit.read_bytes()
    await stop("verifier")
    _, overlay = configs["verifier"].runtime()
    lock = OwnerLock(overlay.store)
    try:
        # A positive database session lock excludes any surviving checker writer.
        await asyncio.to_thread(lock.acquire)
        page = await asyncio.to_thread(
            overlay.store.record_page,
            RecordQuery(kinds=("evidence",), issuer="verifier", subject=target.subject),
            limit=128,
        )
        assert page.next_cursor is None
        supports = [
            item
            for item in page.items
            if isinstance(item, Evidence)
            and item.verdict == "PASS"
            and item.binding_digest == target.digest
        ]
        assert supports
        envelopes = [
            identities["verifier"].sign(
                Revocation(
                    issuer="verifier",
                    subject=item.subject,
                    evidence_id=item.id,
                    reason="operator withdrawal while independent checker is quiescent",
                )
            )
            for item in supports
        ]
        for envelope in envelopes:
            await asyncio.to_thread(overlay.store.put, envelope)
    finally:
        lock.close()
        overlay.store.close()
    for envelope in envelopes:
        delivered = await send(
            configs["verifier"],
            identities["verifier"],
            "receiver",
            {"operation": "submit", "envelope": envelope},
        )
        assert delivered["inserted"] is True
    decision = (await call("receiver", operation="qualify", request=request))["decision"]
    assert decision["outcome"] != "ACCEPT"
    denied = await call("receiver", **{**reuse, "invocation_id": "evidence-withdrawn-use"})
    assert denied["state"] == "unknown"
    assert mesh.mcp_audit.read_bytes() == effects
    for owner, config in configs.items():
        after = await asyncio.to_thread(originals, config)
        assert all(after[0][key] == envelope for key, envelope in before[owner][0].items())
        assert after[1] == before[owner][1]
    observation = {
        "injection": "evidence withdrawal",
        "prior_admission": "ACCEPT",
        "withdrawn_evidence_ids": [item.id for item in supports],
        "withdrawn_admission": decision,
        "new_use": denied,
        "original_signed_bytes_preserved": True,
        "withdrawal_created_no_mcp_call": True,
        "source_prefix_freshness_inferred": False,
    }
    path = root / "evidence-withdrawal-observations.json"
    path.write_text(json.dumps(observation, indent=2), encoding="utf-8")
    await start("verifier")
    # New operator intent and attempt; never rewrite or undo withdrawn evidence.
    checked = await send(
        configs["receiver"],
        identities["receiver"],
        "verifier",
        {
            "operation": "app.request-document-check",
            "name": "triage",
            "attempt": "after-explicit-evidence-withdrawal",
            "binding_digest": target.digest,
            "checker_digest": checker.digest,
        },
    )
    assert checked["evidence"]["verdict"] == "PASS"
    assert checked["evidence"]["id"] not in observation["withdrawn_evidence_ids"]
    await sync("receiver", "verifier")
    fresh = (await call("receiver", operation="qualify", request=request))["decision"]
    assert fresh["outcome"] == "ACCEPT"
    observation.update(fresh_evidence=checked["evidence"], fresh_admission=fresh)
    path.write_text(json.dumps(observation, indent=2), encoding="utf-8")
