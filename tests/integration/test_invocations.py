import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select, update

from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Registry,
    Target,
    callable_digest,
)
from collective_intelligence_overlay.invocations import Executor, InvocationStore, Reservation
from collective_intelligence_overlay.models import (
    Capability,
    Event,
    Evidence,
    Revocation,
    Subject,
    now,
)
from collective_intelligence_overlay.storage import Conflict, Store, budgets, leases


def registered(overlay, identities, records, operation):
    cap, checked = records
    subject = Subject(id="invocation-tool", version="1", digest=callable_digest(operation))
    binding = Binding(
        id="invocation-tool",
        revision="1",
        issuer="producer",
        registrar="receiver",
        subject=subject,
        scope=cap.scope,
        target=Target(
            kind="local",
            name="operation",
            implementation_identity="installed",
            interface_digest=callable_digest(operation),
        ),
        input_schema={
            "type": "object",
            "properties": {"value": {"type": "integer"}},
            "required": ["value"],
            "additionalProperties": False,
        },
        output_schema={"type": "integer"},
        callers=("receiver",),
        effects="read-only",
    )
    for model, source in ((Capability, cap), (Evidence, checked)):
        record = model.model_validate(
            {
                **source.model_dump(),
                "subject": subject,
                "schema_version": "2",
                "binding_digest": binding.digest,
                **({"id": "invocation-check"} if model is Evidence else {}),
            }
        )
        overlay.store.put(identities[record.issuer].sign(record))
    registry = Registry(overlay)
    registry.register_local(binding, operation, lambda _: True)
    overlay.store.set_budget("work", Decimal(10))
    return (
        Executor(registry, identities["receiver"], Reservation()),
        binding,
        ExecutionContext(
            caller="receiver",
            environment=cap.scope.environment,
        ),
    )


async def test_completed_result_survives_restart_and_exact_retry(overlay, identities, records):
    effects = []

    async def operation(arguments):
        effects.append(arguments["value"])
        return arguments["value"] * 2

    executor, binding, context = registered(overlay, identities, records, operation)
    result = await executor.invoke("stable-id", binding.id, binding.digest, {"value": 5}, context)
    assert result["state"] == "completed" and result["result"] == 10
    assert effects == [5]
    again = await executor.invoke("stable-id", binding.id, binding.digest, {"value": 5}, context)
    assert again == result and effects == [5]
    with pytest.raises(Conflict):
        await executor.invoke("stable-id", binding.id, binding.digest, {"value": 6}, context)
    reopened = Store(
        overlay.store.engine.url.render_as_string(hide_password=False),
        overlay.store.owner,
        overlay.store.principals,
    )
    try:
        assert InvocationStore(reopened).get("receiver", "stable-id") == result
        assert InvocationStore(reopened).get("other", "stable-id") is None
        assert InvocationStore(reopened).cancel("other", "stable-id") is None
        assert InvocationStore(reopened).cancel("receiver", "stable-id")["state"] == "completed"
        with reopened.engine.connect() as conn:
            assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal(9)
            assert conn.execute(select(leases.c.actual)).scalar_one() is None
    finally:
        reopened.close()


async def test_concurrent_duplicate_returns_running_and_cancel_fences_result(
    overlay, identities, records
):
    started = asyncio.Event()
    release = asyncio.Event()
    count = 0

    async def operation(arguments):
        nonlocal count
        count += 1
        started.set()
        await release.wait()
        return arguments["value"]

    executor, binding, context = registered(overlay, identities, records, operation)
    task = asyncio.create_task(
        executor.invoke("race", binding.id, binding.digest, {"value": 1}, context)
    )
    await asyncio.wait_for(started.wait(), 5)
    duplicate = await executor.invoke("race", binding.id, binding.digest, {"value": 1}, context)
    assert duplicate["state"] == "running"
    cancelled = await asyncio.to_thread(executor.store.cancel, "receiver", "race")
    assert cancelled["state"] == "unknown"
    release.set()
    assert (await task)["state"] == "unknown"
    assert count == 1
    assert (await executor.invoke("race", binding.id, binding.digest, {"value": 1}, context))[
        "state"
    ] == "unknown"


def test_atomic_reservation_race_and_expired_dispatched_worker(store, identities, records):
    store.set_budget("work", Decimal(2))
    ledger = InvocationStore(store)
    request = {"binding": "b", "arguments": {"value": 1}}
    with ThreadPoolExecutor(max_workers=4) as pool:
        claims = list(
            pool.map(
                lambda _: ledger.claim("receiver", "one-id", "b", "a" * 64, request, Reservation()),
                range(4),
            )
        )
    assert sum(fresh for _, fresh in claims) == 1
    claim = claims[0][0]
    ledger.dispatched(claim)
    with store.engine.begin() as conn:
        conn.execute(update(leases).values(expires_at=now() - timedelta(seconds=1)))
    assert ledger.get("receiver", "one-id")["state"] == "unknown"
    event = Event(
        issuer="receiver",
        subject=records[0].subject,
        action="reuse",
        task_id="one-id",
        attempt_id="one-id",
        correlation_id="one-id",
    )
    with pytest.raises(Conflict):
        ledger.finish(claim, 1, identities["receiver"], event)
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal(1)


async def test_external_effect_then_failure_is_retained_without_retry(overlay, identities, records):
    effects = []

    async def operation(arguments):
        effects.append(arguments["value"])
        raise RuntimeError("response lost after external effect")

    executor, binding, context = registered(overlay, identities, records, operation)
    result = await executor.invoke("uncertain", binding.id, binding.digest, {"value": 2}, context)
    assert result["state"] == "unknown" and result["result"] is None
    assert (
        await executor.invoke("uncertain", binding.id, binding.digest, {"value": 2}, context)
    ) == result
    assert effects == [2]
    assert overlay.store.events()[-1].outcome == "UNKNOWN"


async def test_revocation_during_dispatch_commit_prevents_actuation(
    overlay, identities, records, monkeypatch
):
    effects = []

    async def operation(arguments):
        effects.append(arguments)
        return arguments["value"]

    executor, binding, context = registered(overlay, identities, records, operation)
    dispatch = executor.store.dispatched

    def withdrawing(claim):
        dispatch(claim)
        overlay.store.put(
            identities["producer"].sign(
                Revocation(
                    issuer="producer",
                    subject=binding.subject,
                    reason="withdrawn at execution boundary",
                )
            )
        )

    monkeypatch.setattr(executor.store, "dispatched", withdrawing)
    result = await executor.invoke("withdraw", binding.id, binding.digest, {"value": 1}, context)
    assert result["state"] == "unknown" and result["reason"] == "admission_denied"
    assert effects == []


def test_process_dies_after_effect_before_result_commit(store, tmp_path):
    import os
    import subprocess
    import sys

    store.set_budget("work", Decimal(2))
    marker = tmp_path / "external-effect.txt"
    script = """
import os
from pathlib import Path
from collective_intelligence_overlay.storage import Store
from collective_intelligence_overlay.invocations import InvocationStore, Reservation
store = Store(os.environ['CIO_CRASH_TEST_DB'], 'receiver', {})
claim, fresh = InvocationStore(store).claim('receiver', 'crash', 'registered', 'a'*64,
                                          {'effect': 'append'}, Reservation())
assert fresh
InvocationStore(store).dispatched(claim)
Path(os.environ['CIO_CRASH_TEST_MARKER']).write_text('effect happened once')
os._exit(17)
"""
    process = subprocess.run(
        [sys.executable, "-c", script],
        check=False,
        capture_output=True,
        timeout=15,
        env={
            **os.environ,
            "CIO_CRASH_TEST_DB": store.engine.url.render_as_string(hide_password=False),
            "CIO_CRASH_TEST_MARKER": str(marker),
        },
    )
    assert process.returncode == 17
    assert marker.read_text() == "effect happened once"
    ledger = InvocationStore(store)
    assert ledger.get("receiver", "crash")["state"] == "running"
    with store.engine.begin() as conn:
        conn.execute(update(leases).values(expires_at=now() - timedelta(seconds=1)))
    assert ledger.get("receiver", "crash")["state"] == "unknown"
    previous, fresh = ledger.claim(
        "receiver", "crash", "registered", "a" * 64, {"effect": "append"}, Reservation()
    )
    assert not fresh and previous["state"] == "unknown"
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal(1)
