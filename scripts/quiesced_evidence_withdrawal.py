"""Operator-owned checker quiescence and actual HTTPS signed withdrawal delivery."""

import json
import time

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.models import Evidence, Revocation
from collective_intelligence_overlay.operations import OwnerLock
from collective_intelligence_overlay.queries import RecordQuery


async def deliver(session, envelope):
    """An offline owner's signer can submit its DSSE to a configured live peer."""
    data = {"operation": "submit", "envelope": envelope}
    item = {
        "call_index": len(session.calls),
        "owner": "verifier",
        "target": "receiver",
        "phase": session.phase,
        "category": "control",
        "operation": "submit",
        "request": data,
        "offered_seconds": session.seconds(),
        "status": "censored",
    }
    session.calls.append(item)
    started = time.monotonic()
    try:
        result = await send(
            session.configs["verifier"], session.identities["verifier"], "receiver", data
        )
        item.update(status="returned", result=result)
        return result
    except Exception as error:
        item.update(status="failed", error_type=type(error).__name__)
        raise
    finally:
        item["wall_seconds"] = time.monotonic() - started
        item["latency_censored"] = item["status"] == "censored"
        session.journal.write(json.dumps(item, ensure_ascii=False) + "\n")
        session.journal.flush()


async def withdraw(session, target):
    """Stop the checker, retain all original supports, deliver actual signed withdrawals.

    Caller-visible checks offered during this outage fail normally. No actual input,
    seed, quota, criterion or response is rewritten. Source freshness is not renewed:
    the receiver receives authenticated original DSSE through its ordinary submit API.
    Its existing complete-prefix timestamp remains unchanged until actual later sync.
    """
    import asyncio

    await session.stop("verifier")
    _, overlay = session.configs["verifier"].runtime()
    lock = OwnerLock(overlay.store)
    try:
        # A positive owner-session lock excludes a surviving checker writer;
        # process-await cancellation by itself would not prove quiescence.
        await asyncio.to_thread(lock.acquire)
        page = await asyncio.to_thread(
            overlay.store.record_page,
            RecordQuery(kinds=("evidence",), issuer="verifier", subject=target.subject),
            limit=128,
        )
        if page.next_cursor is not None:
            raise ValueError("withdrawal fixture exceeded its predeclared evidence bound")
        supports = [
            item
            for item in page.items
            if isinstance(item, Evidence)
            and item.verdict == "PASS"
            and item.binding_digest == target.digest
        ]
        if not supports:
            raise ValueError("withdrawal requires original independent PASS supports")
        envelopes = [
            session.identities["verifier"].sign(
                Revocation(
                    issuer="verifier",
                    subject=item.subject,
                    evidence_id=item.id,
                    reason="predeclared operator withdrawal while checker is quiescent",
                )
            )
            for item in supports
        ]
        for envelope in envelopes:
            await asyncio.to_thread(overlay.store.put, envelope)
    finally:
        lock.close()
        overlay.store.close()
    delivered = [await deliver(session, envelope) for envelope in envelopes]
    if not all(item.get("inserted") is True for item in delivered):
        raise ValueError("a signed withdrawal was not delivered to the receiving owner")
    return {
        "withdrawn_evidence_ids": [item.id for item in supports],
        "delivered": delivered,
        "checker_still_stopped": True,
        "source_prefix_freshness_inferred": False,
    }
