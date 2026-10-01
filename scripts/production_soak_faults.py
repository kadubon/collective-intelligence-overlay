"""Explicit operator fault injections; never replace the installed business runtime."""

import asyncio
import os
import signal
import time
from decimal import Decimal

from production_session import stop_process
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.models import Evidence, Revocation, UseRequest
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.storage import budgets


def request(session):
    binding = session.target
    return UseRequest(
        receiver="receiver",
        capability_issuer=binding.issuer,
        subject=binding.subject,
        scope=binding.scope,
        binding_digest=binding.digest,
        semantic_fit="confirmed",
    ).model_dump(mode="json")


def invocation(session, identity, document):
    return {
        "operation": "invoke",
        "invocation_id": identity,
        "binding_id": session.target.id,
        "binding_digest": session.target.digest,
        "arguments": {"text": document},
    }


async def inject(session, index, completed):
    """Retain intermediate observations, original IDs and explicit repair actions."""
    started = time.monotonic()
    result = {"index": index, "started_seconds": session.seconds(), "observations": []}
    observations = result["observations"]
    if index == 0:
        await session.stop("verifier", crash=True)
        observations.append(
            await session.verify(
                "receiver", "triage", {"text": "checker 故障"}, "fault-checker-unavailable"
            )
        )
        await session.start("verifier")
    elif index in {1, 2}:
        worker = session.mesh.workers[-1]
        if index == 1:
            os.kill(worker.pid, signal.SIGSTOP)
            try:
                delayed = asyncio.create_task(
                    session.call(
                        "receiver", **invocation(session, "fault-delayed-original", "delayed 文書")
                    )
                )
                await asyncio.sleep(31)
            finally:
                os.kill(worker.pid, signal.SIGCONT)
            observations.append(await delayed)
            observations.append(
                await session.call(
                    "receiver", operation="invocation", invocation_id="fault-delayed-original"
                )
            )
        else:
            await asyncio.to_thread(stop_process, worker)
            observations.append(
                await session.call(
                    "receiver",
                    **invocation(session, "fault-provider-stopped-original", "stop 文書"),
                )
            )
            await asyncio.to_thread(session.mesh.restart_mcp)
            observations.append(
                await session.call(
                    "receiver",
                    operation="invocation",
                    invocation_id="fault-provider-stopped-original",
                )
            )
    elif index == 3:
        if not completed:
            raise ValueError("duplicate test requires an actual completed original invocation")
        original = completed[0]
        repeated = await session.call("receiver", **original["request"])
        observations.extend([original["result"], repeated])
        result["original_invocation_id"] = original["request"]["invocation_id"]
        result["original_receipt_unchanged"] = repeated == original["result"]
        if not result["original_receipt_unchanged"]:
            raise ValueError("duplicate delivery changed the original receipt")
    elif index == 4:
        # Withdraw all currently retained verifier PASS supports of this target,
        # through the public signed-record submission path. Never overwrite them.
        _, overlay = session.configs["verifier"].runtime()
        try:
            page = await asyncio.to_thread(
                overlay.store.record_page,
                RecordQuery(kinds=("evidence",), issuer="verifier", subject=session.target.subject),
                limit=128,
            )
            if page.next_cursor is not None:
                raise ValueError("withdrawal fixture exceeded its predeclared evidence bound")
            supports = [
                item
                for item in page.items
                if isinstance(item, Evidence)
                and item.verdict == "PASS"
                and item.binding_digest == session.target.digest
            ]
        finally:
            overlay.store.close()
        if not supports:
            raise ValueError("withdrawal requires original independent PASS evidence")
        result["withdrawn_evidence_ids"] = [item.id for item in supports]
        for evidence in supports:
            signed = session.identities["verifier"].sign(
                Revocation(
                    issuer="verifier",
                    subject=evidence.subject,
                    evidence_id=evidence.id,
                    reason="predeclared soak operator evidence withdrawal",
                )
            )
            observations.append(await session.call("verifier", operation="submit", envelope=signed))
        observations.append(await session.sync("receiver", "verifier"))
        before = await session.call("receiver", operation="qualify", request=request(session))
        observations.append(before)
        result["withdrawn_support_not_accepted"] = (
            before.get("decision", {}).get("outcome") != "ACCEPT"
        )
        if not result["withdrawn_support_not_accepted"]:
            raise ValueError("known withdrawn supports remained admitted")
        fresh = await session.verify(
            "receiver",
            "triage",
            {"text": "new independently checked 文書"},
            "fault-explicit-requalification",
        )
        observations.append(fresh)
        observations.append(await session.sync("receiver", "verifier"))
        observations.append(
            await session.call("receiver", operation="qualify", request=request(session))
        )
        result["fresh_check_id"] = fresh.get("evidence", {}).get("id")
    elif index == 5:
        old_pid = session.processes["receiver"].pid
        await session.stop("receiver", crash=True)
        await session.start("receiver")
        result.update(old_pid=old_pid, new_pid=session.processes["receiver"].pid)
        if completed:
            original = completed[0]
            repeated = await session.call("receiver", **original["request"])
            observations.append(repeated)
            result["original_receipt_unchanged"] = repeated == original["result"]
            if not result["original_receipt_unchanged"]:
                raise ValueError("owner crash/restart changed a committed receipt")
    elif index == 6:
        role = make_url(session.configs["receiver"].database_url.get_secret_value()).username
        with session.mesh.admin.connect() as conn:
            terminated = (
                conn.execute(
                    text(
                        "SELECT pg_terminate_backend(pid) FROM pg_stat_activity "
                        "WHERE usename=:role AND pid <> pg_backend_pid()"
                    ),
                    {"role": role},
                )
                .scalars()
                .all()
            )
            conn.commit()
        result["terminated_owner_database_sessions"] = len(terminated)
        observations.append(await session.call("receiver", operation="status"))
        await session.stop("receiver")
        await session.start("receiver")
    elif index == 7:
        observations.append(await session.call("receiver", operation="drain"))
        refused = await session.call(
            "receiver", **invocation(session, "fault-drain-refused", "drain 文書")
        )
        observations.append(refused)
        result["new_effect_refused"] = refused.get("error") == "SERVICE_INTAKE_CLOSED"
        if not result["new_effect_refused"]:
            raise ValueError("new effect entered a drained owner")
        observations.append(await session.call("receiver", operation="resume"))
    elif index == 8:
        # Sixteen distinct offers against unchanged caller=4, owner=16 and
        # execution=4 bounds; the external provider is physically delayed.
        worker = session.mesh.workers[-1]
        os.kill(worker.pid, signal.SIGSTOP)
        try:
            group = [
                asyncio.create_task(
                    session.call(
                        "receiver",
                        **invocation(session, f"fault-caller-capacity-{i}", f"capacity 文書 {i}"),
                    )
                )
                for i in range(16)
            ]
            await asyncio.sleep(8)
        finally:
            os.kill(worker.pid, signal.SIGCONT)
        observations.extend(await asyncio.gather(*group))
        result["refused_or_failed_offers"] = sum(
            value.get("state") != "completed" for value in observations
        )
    elif index == 9:
        # A workflow root is not the identity of its nested A2A child. The
        # explicitly offered direct registered A2A operation was completed at
        # setup, with its own stable parent. Query it without a new operation.
        parent = session.original_direct["request"]["invocation_id"]
        mapped = await session.call("receiver", operation="remote_calls", invocation_id=parent)
        observations.append(mapped)
        if not mapped.get("calls"):
            raise ValueError("original remote mapping is missing")
        reference = mapped["calls"][0]
        observations.append(
            await session.call(
                "receiver",
                operation="reconcile",
                call_key=reference["call_key"],
                command_id="fault-missing-reconciliation-evidence",
                invocation_id=parent,
            )
        )
        result["original_parent_invocation_id"] = parent
        receipt = observations[-1].get("event", {}).get("reconciliation", {})
        if receipt.get("effect") != "unknown":
            raise ValueError("missing external effect confirmation did not retain UNKNOWN")
    elif index == 10:
        # An explicit test operator reserves the remaining existing allowance
        # using Store.acquire. It is retained held, never interpreted as actual
        # consumption or refunded. No hidden update/top-up bypasses the ledger.
        _, overlay = session.configs["receiver"].runtime()
        try:
            with overlay.store.engine.connect() as conn:
                available = conn.execute(
                    select(budgets.c.remaining).where(budgets.c.unit == "work")
                ).scalar_one()
            fence = await asyncio.to_thread(
                overlay.store.acquire,
                "fault-operator-budget-pressure",
                "receiver",
                "work",
                Decimal(available),
                seconds=600,
                reclaim_expired=False,
            )
            result["operator_held_reservation"] = {
                "task_id": "fault-operator-budget-pressure",
                "worker": "receiver",
                "fence": fence,
                "quantity": str(available),
                "unit": "work",
                "effect_attempted": False,
                "refund": False,
            }
        finally:
            overlay.store.close()
        refused = await session.call(
            "receiver", **invocation(session, "fault-budget-refused", "budget 文書")
        )
        observations.append(refused)
        result["budget_refused"] = refused.get("state") != "completed"
        if not result["budget_refused"]:
            raise ValueError("operation completed without available allowance")
    else:
        raise ValueError("unknown predeclared fault index")
    # Recovery of service readiness is separate from reconciliation of any
    # uncertain effect. Original-ID lookup does not settle or refund those effects.
    result["elapsed_seconds"] = time.monotonic() - started
    result["ready_after_explicit_repair"] = {
        owner: await session.call(owner, operation="status") for owner in session.configs
    }
    return result
