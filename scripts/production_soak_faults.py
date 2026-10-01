"""Explicit operator fault injections; never replace the installed business runtime."""

import asyncio
import os
import signal
import time
from decimal import Decimal
from pathlib import Path

from production_session import stop_process
from quiesced_evidence_withdrawal import withdraw
from sqlalchemy import select, text
from sqlalchemy.engine import make_url

from collective_intelligence_overlay.models import UseRequest
from collective_intelligence_overlay.storage import budgets


async def suspend(process):
    """Confirm the owned Linux soak process is stopped before timing the outage."""
    os.kill(process.pid, signal.SIGSTOP)
    try:
        async with asyncio.timeout(1):
            while process.poll() is None:
                state = (Path("/proc") / str(process.pid) / "status").read_text()
                if any(
                    line.startswith("State:") and "T (stopped)" in line
                    for line in state.splitlines()
                ):
                    return
                await asyncio.sleep(0.01)
        raise ValueError("owned provider did not positively stop")
    except BaseException:
        try:
            os.kill(process.pid, signal.SIGCONT)
        except ProcessLookupError:
            pass
        raise


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


async def intake(session, operation, state, observations):
    """Bounded explicit idempotent owner control, confirmed by real status queries.

    The scheduled burst may refuse a control request before dispatch. Retain all
    attempts; never infer drain from a transport exception or retry an invocation.
    """
    for attempt in range(3):
        value = await session.call("receiver", operation=operation)
        observations.append(value)
        observed = await session.call("receiver", operation="status")
        observations.append(observed)
        if observed.get("state") == state:
            return observed
        if attempt < 2:
            await asyncio.sleep(attempt + 1)
    raise ValueError("owner intake transition was not positively confirmed")


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
            await suspend(worker)
            result["provider_unavailable"] = {
                "owner": "producer",
                "transport": "mcp",
                "pid": worker.pid,
                "from_seconds": session.seconds(),
                "physical_stop_confirmed": True,
                "observation": "owned Linux process status confirmed T (stopped)",
            }
            try:
                delayed = asyncio.create_task(
                    session.call(
                        "receiver", **invocation(session, "fault-delayed-original", "delayed 文書")
                    )
                )
                await asyncio.sleep(31)
            finally:
                result["provider_unavailable"]["until_seconds"] = session.seconds()
                os.kill(worker.pid, signal.SIGCONT)
            observations.append(await delayed)
            observations.append(
                await session.call(
                    "receiver", operation="invocation", invocation_id="fault-delayed-original"
                )
            )
        else:
            await asyncio.to_thread(stop_process, worker)
            result["provider_unavailable"] = {
                "owner": "producer",
                "transport": "mcp",
                "pid": worker.pid,
                "from_seconds": session.seconds(),
                "physical_exit_confirmed": worker.poll() is not None,
            }
            observations.append(
                await session.call(
                    "receiver",
                    **invocation(session, "fault-provider-stopped-original", "stop 文書"),
                )
            )
            result["provider_unavailable"]["until_seconds"] = session.seconds()
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
        try:
            # Stop and positively lock the checker before taking the bounded
            # support snapshot. A concurrently offered check otherwise creates
            # fresh valid evidence during withdrawal and tests a different claim.
            withdrawn = await withdraw(session, session.target)
            result.update(withdrawn_evidence_ids=withdrawn["withdrawn_evidence_ids"])
            observations.extend(withdrawn["delivered"])
            result["checker_quiescent_during_withdrawal"] = True
            before = await session.call("receiver", operation="qualify", request=request(session))
            observations.append(before)
            result["withdrawn_support_not_accepted"] = (
                before.get("decision", {}).get("outcome") != "ACCEPT"
            )
            if not result["withdrawn_support_not_accepted"] or "decision" not in before:
                raise ValueError("withdrawn-support decision is missing or still ACCEPT")
        finally:
            await session.start("verifier")
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
        try:
            await intake(session, "drain", "draining", observations)
            refused = await session.call(
                "receiver", **invocation(session, "fault-drain-refused", "drain 文書")
            )
            observations.append(refused)
            result["new_effect_refused"] = refused.get("error") == "SERVICE_INTAKE_CLOSED"
            if not result["new_effect_refused"]:
                raise ValueError("drained new-effect refusal is missing")
        finally:
            await intake(session, "resume", "ready", observations)
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
    result["ready_after_explicit_repair"] = {
        owner: await session.call(owner, operation="status") for owner in session.configs
    }
    if any(
        value.get("state") != "ready" for value in result["ready_after_explicit_repair"].values()
    ):
        raise ValueError("explicit repair did not positively confirm every owner's readiness")
    result["elapsed_seconds"] = time.monotonic() - started
    return result
