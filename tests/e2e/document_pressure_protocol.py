"""Exercise finite durable capacity and allowance in the same real peer mesh."""

import asyncio
import json
from decimal import Decimal

from document_recovery_protocol import originals
from production_mesh import stop_process
from sqlalchemy import select

from collective_intelligence_overlay.bindings import Binding, ExecutionContext
from collective_intelligence_overlay.invocations import (
    InvocationStore,
    Reservation,
    invocation_request,
)
from collective_intelligence_overlay.storage import budgets


async def run(configs, mesh, call, counter, root):
    observations = []

    def retain(injection, **fields):
        observations.append({"injection": injection, **fields})
        (root / "pressure-observations.json").write_text(
            json.dumps(observations, indent=2), encoding="utf-8"
        )

    def reserve(owner, binding, identifier, *, all_remaining=False):
        config = configs[owner]
        _, overlay = config.runtime()
        try:
            with overlay.store.engine.connect() as conn:
                available = conn.execute(
                    select(budgets.c.remaining).where(budgets.c.unit == "work")
                ).scalar_one()
            context = ExecutionContext(
                caller=owner,
                purpose="reuse",
                environment=config.execution_environment,
                permissions=frozenset(config.policy.permissions),
            )
            arguments = {"text": "explicit undispatched operator pressure"}
            request = invocation_request(owner, binding.id, binding.digest, arguments, context)
            claim, fresh = InvocationStore(overlay.store).claim(
                owner,
                identifier,
                binding.id,
                binding.digest,
                request,
                Reservation(
                    quantity=available if all_remaining else Decimal(1),
                    seconds=300,
                    max_concurrent=config.max_concurrency,
                    max_unresolved=config.max_unresolved,
                ),
            )
            assert fresh and claim["phase"] == "reserved" and claim["state"] == "running"
            return {
                "id": identifier,
                "quantity": str(available if all_remaining else Decimal(1)),
                "lease_id": claim["lease_id"],
            }
        finally:
            overlay.store.close()

    # Positive durable reservations consume actual owner slots. No effect is
    # dispatched by this explicit operator fixture; cancellation must prove that.
    binding = Binding.model_validate(counter)
    before = await asyncio.to_thread(originals, configs["producer"])
    effects = mesh.mcp_audit.read_bytes()
    holders = [
        await asyncio.to_thread(reserve, "producer", binding, f"capacity-reserved-{i}")
        for i in range(4)
    ]
    held = await asyncio.to_thread(originals, configs["producer"])
    assert held[1]["work"] == before[1]["work"] - 4
    refused_request = {
        "operation": "invoke",
        "invocation_id": "capacity-fifth-refused",
        "binding_id": binding.id,
        "binding_digest": binding.digest,
        "arguments": {"text": "finite capacity refusal"},
    }
    refused = await call("producer", **refused_request)
    assert refused == {"state": "conflict", "error": "INVOCATION_OR_ALLOWANCE_CONFLICT"}
    assert (
        await call(
            "producer", operation="invocation", invocation_id=refused_request["invocation_id"]
        )
    )["invocation"] is None
    assert await asyncio.to_thread(originals, configs["producer"]) == held
    for holder in holders:
        cancelled = await call(
            "producer", operation="cancel_invocation", invocation_id=holder["id"]
        )
        assert cancelled["invocation"]["state"] == "cancelled"
        assert cancelled["invocation"]["reservation_state"] == "released"
        assert (
            await call("producer", operation="cancel_invocation", invocation_id=holder["id"])
            == cancelled
        )
    assert await asyncio.to_thread(originals, configs["producer"]) == before
    assert mesh.mcp_audit.read_bytes() == effects
    retain(
        "execution capacity exhaustion",
        max_concurrent=4,
        undispatched_operator_reservations=holders,
        refused=refused,
        positive_undispatched_release_once=True,
    )

    # Exhaust the receiver's existing work allowance through a durable claim,
    # rather than updating balances or fabricating consumption.
    remote = Binding.model_validate(
        (await call("receiver", operation="app.describe", name="remote-words"))["binding"]
    )
    before_receiver = await asyncio.to_thread(originals, configs["receiver"])
    holder = await asyncio.to_thread(
        reserve, "receiver", remote, "budget-reserved-original", all_remaining=True
    )
    assert (await asyncio.to_thread(originals, configs["receiver"]))[1]["work"] == 0
    budget_request = {
        "operation": "invoke",
        "invocation_id": "budget-new-refused",
        "binding_id": remote.id,
        "binding_digest": remote.digest,
        "arguments": {"text": "finite budget refusal"},
    }
    budget_refused = await call("receiver", **budget_request)
    assert budget_refused == {"state": "conflict", "error": "INVOCATION_OR_ALLOWANCE_CONFLICT"}
    assert (
        await call(
            "receiver", operation="invocation", invocation_id=budget_request["invocation_id"]
        )
    )["invocation"] is None
    cancellation = await call("receiver", operation="cancel_invocation", invocation_id=holder["id"])
    assert (
        cancellation["invocation"]["state"] == "cancelled"
        and cancellation["invocation"]["reservation_state"] == "released"
    )
    assert (
        await call("receiver", operation="cancel_invocation", invocation_id=holder["id"])
        == cancellation
    )
    assert await asyncio.to_thread(originals, configs["receiver"]) == before_receiver
    assert mesh.mcp_audit.read_bytes() == effects
    retain(
        "budget exhaustion",
        operator_reservation=holder,
        refused=budget_refused,
        positive_undispatched_release_once=True,
    )

    worker = mesh.workers[-1]
    await asyncio.to_thread(stop_process, worker, kill=True)
    assert worker.poll() is not None
    before_stopped = await asyncio.to_thread(originals, configs["producer"])
    uncertain = []
    refusal = None
    try:
        for index in range(33):
            identifier = f"capacity-uncertain-original-{index}"
            request = {**refused_request, "invocation_id": identifier}
            result = await call("producer", **request)
            if result.get("error") == "OWNER_UNRESOLVED_EFFECTS_LIMIT":
                refusal = result
                assert (await call("producer", operation="invocation", invocation_id=identifier))[
                    "invocation"
                ] is None
                break
            assert result["state"] == "unknown" and result["reservation_state"] == "held"
            uncertain.append({"request": request, "result": result})
        assert refusal is not None and uncertain
        measured = await call("producer", operation="operational_metrics")
        assert measured["database"]["unresolved_effects"] == 32
        held = await asyncio.to_thread(originals, configs["producer"])
        assert held[1]["work"] == before_stopped[1]["work"] - len(uncertain)
        await asyncio.to_thread(mesh.restart_mcp)
        # Read/retry remains possible at the ceiling; a new attempt is refused
        # even after physical service repair. Nothing settles an uncertain effect.
        for original in uncertain:
            assert await call("producer", **original["request"]) == original["result"]
        retry = await call(
            "producer", **{**refused_request, "invocation_id": "capacity-after-service-repair"}
        )
        assert retry.get("error") == "OWNER_UNRESOLVED_EFFECTS_LIMIT"
        assert await asyncio.to_thread(originals, configs["producer"]) == held
        assert all(held[0][key] == envelope for key, envelope in before_stopped[0].items())
        assert mesh.mcp_audit.read_bytes() == effects
        retain(
            "unresolved capacity exhaustion",
            maximum_unresolved=32,
            provider_pid=worker.pid,
            physical_exit=worker.returncode,
            originals=uncertain,
            refused=refusal,
            refused_after_physical_repair=retry,
            uncertain_refunds=0,
        )
    finally:
        if mesh.workers[-1].poll() is not None:
            await asyncio.to_thread(mesh.restart_mcp)
    for owner in configs:
        assert (await call(owner, operation="status"))["state"] == "ready"
