import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from decimal import Decimal
from functools import partial
from threading import Barrier
from threading import Event as ThreadEvent

import pytest
from sqlalchemy import select, update

from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Registry,
    Target,
    callable_digest,
)
from collective_intelligence_overlay.invocations import (
    Executor,
    InvocationStore,
    Reservation,
    invocations,
)
from collective_intelligence_overlay.lineage import FormationSession
from collective_intelligence_overlay.models import (
    Capability,
    Event,
    Evidence,
    Revocation,
    Subject,
    now,
)
from collective_intelligence_overlay.storage import Conflict, Store, budgets, leases


def test_concurrent_formation_start_reservations_preserve_floor(store):
    store.set_budget("work", Decimal(2))
    barrier = Barrier(4)

    def acquire(index):
        barrier.wait(timeout=5)
        try:
            return store.acquire(
                f"formation-{index}",
                "receiver",
                "work",
                Decimal(1),
                minimum_remaining=Decimal(1),
            )
        except Conflict:
            return None

    with ThreadPoolExecutor(max_workers=4) as pool:
        results = list(pool.map(acquire, range(4)))
    assert results.count(1) == 1 and results.count(None) == 3
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 1
        assert len(conn.execute(select(leases)).all()) == 1


def test_protected_allowance_and_capacity_are_atomic_across_units(store):
    store.set_budget("work", Decimal(2))
    store.set_budget("tokens", Decimal(2))
    api = InvocationStore(store)
    barrier = Barrier(2)

    def claim(unit):
        barrier.wait(timeout=5)
        try:
            row, fresh = api.claim(
                "receiver",
                "capacity-" + unit,
                "binding",
                "a" * 64,
                {"unit": unit},
                Reservation(unit=unit, max_concurrent=1, minimum_remaining=1),
            )
            return unit, row, fresh
        except Conflict:
            return unit, None, False

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(claim, ("work", "tokens")))
    successful = [(unit, row) for unit, row, fresh in results if fresh]
    assert len(successful) == 1
    unit, row = successful[0]
    api.cancel("receiver", row["id"])
    # Cancelling known-undispatched work returns capacity and allowance once.
    next_row, fresh = api.claim(
        "receiver",
        "after-cancel",
        "binding",
        "a" * 64,
        {"unit": unit},
        Reservation(unit=unit, max_concurrent=1, minimum_remaining=1),
    )
    assert fresh and next_row["reservation_state"] == "held"
    with pytest.raises(Conflict, match="protected allowance"):
        api.claim(
            "receiver",
            "would-consume-reserve",
            "binding",
            "a" * 64,
            {"unit": unit},
            Reservation(unit=unit, minimum_remaining=1),
        )
    with store.engine.connect() as conn:
        assert (
            conn.execute(select(budgets.c.remaining).where(budgets.c.unit == unit)).scalar_one()
            == 1
        )
    # An operator-authorized checking operation can use the retained unit.
    checked, fresh = api.claim(
        "receiver", "checking-work", "binding", "a" * 64, {"checking": True}, Reservation(unit=unit)
    )
    assert fresh and checked["state"] == "running"


def registered(
    overlay,
    identities,
    records,
    operation,
    assess=None,
    *,
    identifier="invocation-tool",
    components=(),
    initialize_budget=True,
):
    cap, checked = records
    subject = Subject(id=identifier, version="1", digest=callable_digest(operation))
    binding = Binding(
        id=identifier,
        components=components,
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
                **({"id": identifier + "-check"} if model is Evidence else {}),
            }
        )
        overlay.store.put(identities[record.issuer].sign(record))
    registry = Registry(overlay)
    registry.register_local(binding, operation, assess or (lambda _: True))
    if initialize_budget:
        overlay.store.set_budget("work", Decimal(10))
    return (
        Executor(registry, identities["receiver"], Reservation()),
        binding,
        ExecutionContext(
            caller="receiver",
            environment=cap.scope.environment,
        ),
    )


@pytest.mark.parametrize("refusal", ["budget", "capacity"])
async def test_dispatched_parent_retains_the_actual_child_claim_refusal(
    overlay, identities, records, refusal
):
    child_effects = []

    async def child_operation(arguments):
        child_effects.append(arguments)
        return arguments["value"]

    _, child, _ = registered(
        overlay, identities, records, child_operation, identifier="bounded-child"
    )

    async def parent_operation(arguments):
        result = await child_runner.invoke(
            "refused-child", child.id, child.digest, arguments, context
        )
        return result["result"]

    executor, parent, context = registered(
        overlay,
        identities,
        records,
        parent_operation,
        components=(child.digest,),
        initialize_budget=False,
    )
    executor.registry.register_local(child, child_operation, lambda _: True)
    allowance = Reservation(max_concurrent=1 if refusal == "capacity" else 4)
    child_runner = Executor(executor.registry, identities["receiver"], allowance)
    executor.allowance = allowance
    if refusal == "budget":
        with overlay.store.engine.begin() as conn:
            conn.execute(update(budgets).where(budgets.c.unit == "work").values(remaining=1))
    result = await executor.invoke(
        "bounded-parent", parent.id, parent.digest, {"value": 1}, context
    )
    expected = "owner_budget_refused" if refusal == "budget" else "owner_execution_capacity_refused"
    assert result["state"] == "unknown" and result["reason"] == expected
    assert result["reservation_state"] == "held" and result["phase"] == "dispatched"
    assert not child_effects and child_runner.store.get("receiver", "refused-child") is None
    original = overlay.store.reference("event", "receiver", result["receipt_id"])
    event = overlay.store.resolve_reference(original)
    assert event.outcome == "UNKNOWN" and event.execution.state == "unknown"
    with overlay.store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == (
            0 if refusal == "budget" else 9
        )
    assert (
        await executor.invoke("bounded-parent", parent.id, parent.digest, {"value": 1}, context)
        == result
    )


@pytest.mark.parametrize("child_unit", ["work", "tokens"])
async def test_nested_calls_keep_floor_and_independent_request_can_spend_it(
    overlay, identities, records, child_unit
):
    effects = []
    overlay.store.set_budget("tokens", Decimal(1))

    async def leaf(arguments):
        effects.append(0)
        return 0

    _, child, _ = registered(overlay, identities, records, leaf, identifier="child")

    async def operation(arguments):
        value = arguments["value"]
        effects.append(value)
        if value:
            await child_runner.invoke(
                "nested-child",
                child.id,
                child.digest,
                {"value": 0},
                context,
                minimum_remaining=Decimal(0),
            )
        return value

    executor, binding, context = registered(
        overlay,
        identities,
        records,
        operation,
        components=(child.digest,),
        initialize_budget=False,
    )
    executor.registry.register_local(child, leaf, lambda _: True)
    child_runner = Executor(executor.registry, identities["receiver"], Reservation(unit=child_unit))
    result = await executor.invoke(
        "protected-parent",
        binding.id,
        binding.digest,
        {"value": 1},
        context,
        minimum_remaining=Decimal(9),
    )
    assert result["state"] == ("unknown" if child_unit == "work" else "completed")
    assert effects == ([1] if child_unit == "work" else [1, 0])
    with overlay.store.engine.connect() as conn:
        assert (
            conn.execute(select(budgets.c.remaining).where(budgets.c.unit == "work")).scalar_one()
            == 9
        )
    assert (
        await executor.invoke("protected-parent", binding.id, binding.digest, {"value": 1}, context)
        == result
    )
    independent = await executor.invoke(
        "independent-check", binding.id, binding.digest, {"value": 0}, context
    )
    assert independent["state"] == "completed"
    assert effects == ([1, 0] if child_unit == "work" else [1, 0, 0])
    with overlay.store.engine.connect() as conn:
        assert (
            conn.execute(select(budgets.c.remaining).where(budgets.c.unit == "work")).scalar_one()
            == 8
        )

    with overlay.store.engine.connect() as conn:
        assert conn.execute(
            select(budgets.c.remaining).where(budgets.c.unit == "tokens")
        ).scalar_one() == (1 if child_unit == "work" else 0)


async def test_formation_overhead_and_direct_calls_preserve_checking_floor(
    overlay, identities, records
):
    effects = []

    async def operation(arguments):
        effects.append(arguments["value"])
        return arguments["value"]

    executor, binding, context = registered(overlay, identities, records, operation)
    async with FormationSession(
        executor.registry, identities["receiver"], minimum_remaining=Decimal(9)
    ):
        with pytest.raises(Conflict, match="protected allowance"):
            await executor.invoke(
                "formation-child", binding.id, binding.digest, {"value": 1}, context
            )
    with pytest.raises(Conflict, match="budget exhausted"):
        async with FormationSession(
            executor.registry, identities["receiver"], minimum_remaining=Decimal(9)
        ):
            pytest.fail("formation overhead consumed protected allowance")
    assert effects == []
    with overlay.store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 9
        assert len(conn.execute(select(leases)).all()) == 1
    checked = await executor.invoke(
        "after-formation", binding.id, binding.digest, {"value": 3}, context
    )
    assert checked["state"] == "completed" and effects == [3]


async def test_rejected_requests_release_execution_allowance_and_keep_overhead(
    overlay, identities, records
):
    effects = []

    async def operation(arguments):
        effects.append(arguments["value"])
        return arguments["value"]

    executor, binding, context = registered(
        overlay, identities, records, operation, assess=lambda args: args["value"] >= 0
    )
    for attempt in range(12):
        result = await executor.invoke(
            f"refused-{attempt}", binding.id, binding.digest, {"value": -3}, context
        )
        assert result["state"] in {"unknown", "rejected"}
        assert effects == []
        with overlay.store.engine.connect() as conn:
            assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal(10)
        assert (
            await executor.invoke(
                f"refused-{attempt}", binding.id, binding.digest, {"value": -3}, context
            )
            == result
        )
    assert any(
        cost.category == "overhead"
        and cost.unit == "wall_seconds"
        and cost.status == "measured"
        and cost.quantity > 0
        for event in overlay.store.events()
        for cost in event.costs
    )
    assert (await executor.invoke("eligible", binding.id, binding.digest, {"value": 4}, context))[
        "state"
    ] == "completed"
    assert effects == [4]


def test_reserved_cancel_releases_once_and_fences_late_dispatch(store):
    store.set_budget("work", Decimal(2))
    ledger = InvocationStore(store)
    claim, fresh = ledger.claim("receiver", "cancel-before", "b", "a" * 64, {}, Reservation())
    assert fresh
    assert ledger.cancel("receiver", "cancel-before")["state"] == "cancelled"
    ledger.cancel("receiver", "cancel-before")
    with pytest.raises(Conflict):
        ledger.dispatched(claim)
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == Decimal(2)


@pytest.mark.parametrize("dispatch_first", [False, True])
def test_cancel_dispatch_claim_cleanup_race_preserves_allowance(store, dispatch_first):
    store.set_budget("work", Decimal(2))
    ledger = InvocationStore(store)
    claim, _ = ledger.claim("receiver", "race-budget", "b", "a" * 64, {}, Reservation())
    if dispatch_first:
        ledger.dispatched(claim)
    else:
        ledger.cancel("receiver", "race-budget")

    def dispatch():
        try:
            ledger.dispatched(claim)
        except Conflict:
            pass

    with ThreadPoolExecutor(max_workers=4) as pool:
        tasks = [
            pool.submit(fn)
            for fn in (
                dispatch,
                lambda: ledger.cancel("receiver", "race-budget"),
                lambda: ledger.get("receiver", "race-budget"),
                lambda: ledger.claim("receiver", "race-budget", "b", "a" * 64, {}, Reservation()),
            )
        ]
        for task in tasks:
            task.result(timeout=10)
    result = ledger.get("receiver", "race-budget")
    assert result["reservation_state"] == ("held" if dispatch_first else "released")
    with store.engine.connect() as conn:
        remaining = conn.execute(select(budgets.c.remaining)).scalar_one()
        reservation = conn.execute(select(leases.c.reservation)).scalar_one()
        assert remaining + (reservation if dispatch_first else 0) == Decimal(2)


@pytest.mark.parametrize("legacy", [False, True])
def test_expired_reserved_cleanup_fences_or_preserves_unknown_legacy(store, legacy):
    store.set_budget("work", Decimal(2))
    ledger = InvocationStore(store)
    claim, _ = ledger.claim("receiver", "expired-reserved", "b", "a" * 64, {}, Reservation())
    with store.engine.begin() as conn:
        conn.execute(update(leases).values(expires_at=now() - timedelta(seconds=1)))
        if legacy:
            conn.execute(update(invocations).values(reservation_state="legacy_unknown"))
    result = ledger.get("receiver", "expired-reserved")
    assert result["reservation_state"] == ("legacy_unknown" if legacy else "released")
    assert result["state"] == ("unknown" if legacy else "cancelled")
    assert ledger.get("receiver", "expired-reserved") == result
    with pytest.raises(Conflict):
        ledger.dispatched(claim)
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == (1 if legacy else 2)


@pytest.mark.parametrize("commit_before_cancel", [False, True])
async def test_cancelled_await_does_not_cancel_dispatch_db_thread(
    overlay, identities, records, monkeypatch, commit_before_cancel
):
    effects = []
    entered, release, finished = ThreadEvent(), ThreadEvent(), ThreadEvent()

    async def operation(arguments):
        effects.append(arguments)
        return arguments["value"]

    executor, binding, context = registered(overlay, identities, records, operation)
    original = executor.store.dispatched

    def delayed(claim):
        try:
            if commit_before_cancel:
                original(claim)
            entered.set()
            assert release.wait(8)
            if not commit_before_cancel:
                original(claim)
        finally:
            finished.set()

    monkeypatch.setattr(executor.store, "dispatched", delayed)
    task = asyncio.create_task(
        executor.invoke("late-thread", binding.id, binding.digest, {"value": 1}, context)
    )
    assert await asyncio.to_thread(entered.wait, 8)
    try:
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        result = executor.store.get("receiver", "late-thread")
        assert result["reservation_state"] == ("held" if commit_before_cancel else "released")
    finally:
        release.set()
        assert await asyncio.to_thread(finished.wait, 8)
    assert effects == []
    with overlay.store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == (
            9 if commit_before_cancel else 10
        )


@pytest.mark.parametrize("commit_before_cancel", [False, True])
async def test_cancelled_claim_waits_for_confirmed_commit_before_release(
    overlay, identities, records, monkeypatch, commit_before_cancel
):
    entered, release = ThreadEvent(), ThreadEvent()
    effects = []

    async def operation(arguments):
        effects.append(arguments)
        return arguments["value"]

    executor, binding, context = registered(overlay, identities, records, operation)
    original = executor.store.claim

    def delayed(*args):
        if commit_before_cancel:
            result = original(*args)
        entered.set()
        assert release.wait(8)
        return result if commit_before_cancel else original(*args)

    monkeypatch.setattr(executor.store, "claim", delayed)
    task = asyncio.create_task(
        executor.invoke("claim-cancel", binding.id, binding.digest, {"value": 1}, context)
    )
    assert await asyncio.to_thread(entered.wait, 8)
    task.cancel()
    await asyncio.sleep(0)
    assert not task.done()
    release.set()
    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, 8)
    result = executor.store.get("receiver", "claim-cancel")
    assert result["reservation_state"] == "released"
    assert result["reason"] == "cancelled_during_claim"
    assert effects == []
    assert len(overlay.store.events()) == 1
    with overlay.store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 10


async def test_child_admission_denied_after_parent_effect_does_not_release(
    overlay, identities, records
):
    from collective_intelligence_overlay.models import Decision, Outcome, UseRequest
    from collective_intelligence_overlay.overlay import AdmissionDenied

    effects = []

    async def operation(arguments):
        effects.append(arguments)
        raise AdmissionDenied(
            Decision(
                request=UseRequest(
                    receiver="receiver", subject=records[0].subject, scope=records[0].scope
                ),
                outcome=Outcome.REJECT,
                reasons=("child_denied",),
                policy_digest=overlay.policy.digest,
            )
        )

    executor, binding, context = registered(overlay, identities, records, operation)
    result = await executor.invoke(
        "parent-effect", binding.id, binding.digest, {"value": 1}, context
    )
    assert effects == [{"value": 1}]
    assert result["state"] == "unknown" and result["reservation_state"] == "held"
    assert result["reason"] == "admission_denied"
    with overlay.store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 9


def test_concurrent_transitions_have_one_disposition_and_conserve_each_unit(
    store, identities, records
):
    ledger = InvocationStore(store)
    for unit in ("work", "other-work"):
        store.set_budget(unit, Decimal(10))
        for attempt in range(4):
            identifier = f"contended-{unit}-{attempt}"
            allowance = Reservation(unit=unit, quantity=Decimal("0.5"))
            claim, _ = ledger.claim("receiver", identifier, "b", "a" * 64, {}, allowance)
            barrier = Barrier(5)
            event = Event(
                issuer="receiver",
                subject=records[0].subject,
                action="reuse",
                task_id=identifier,
                attempt_id=identifier,
                correlation_id=identifier,
            )

            def run(fn, barrier=barrier):
                barrier.wait(timeout=8)
                try:
                    return fn()
                except Conflict:
                    return "conflict"

            with ThreadPoolExecutor(max_workers=5) as pool:
                tasks = [
                    pool.submit(run, fn)
                    for fn in (
                        partial(ledger.dispatched, claim),
                        partial(ledger.cancel, "receiver", identifier),
                        partial(ledger.get, "receiver", identifier),
                        partial(ledger.claim, "receiver", identifier, "b", "a" * 64, {}, allowance),
                        partial(ledger.finish, claim, 1, identities["receiver"], event),
                    )
                ]
                for task in tasks:
                    task.result(timeout=12)
            ledger.cancel("receiver", identifier)
        with store.engine.connect() as conn:
            remaining = conn.execute(
                select(budgets.c.remaining).where(budgets.c.unit == unit)
            ).scalar_one()
            rows = conn.execute(
                select(invocations.c.reservation_state, leases.c.reservation)
                .select_from(invocations.join(leases, invocations.c.lease_id == leases.c.task_id))
                .where(leases.c.unit == unit)
            ).all()
            assert (
                remaining + sum(quantity for state, quantity in rows if state != "released") == 10
            )


async def test_timeout_before_dispatch_releases_allowance_but_keeps_inspection_cost(
    overlay, identities, records, monkeypatch
):
    effects = []

    async def operation(arguments):
        effects.append(arguments)
        return arguments["value"]

    executor, binding, context = registered(overlay, identities, records, operation)
    executor.allowance = Reservation(seconds=1)
    decide = overlay.policy.decide

    async def slow(facts):
        await asyncio.sleep(2)
        return await decide(facts)

    monkeypatch.setattr(overlay.policy, "decide", slow)
    result = await executor.invoke(
        "timeout-check", binding.id, binding.digest, {"value": 1}, context
    )
    assert effects == [] and result["reservation_state"] == "released"
    assert overlay.store.events()[-1].costs[0].category == "overhead"
    assert overlay.store.events()[-1].costs[0].quantity > 0
    with overlay.store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 10


def test_release_and_failure_record_rollback_together(store, identities, records, monkeypatch):
    store.set_budget("work", Decimal(2))
    ledger = InvocationStore(store)
    claim, _ = ledger.claim("receiver", "rollback-release", "b", "a" * 64, {}, Reservation())
    event = Event(
        issuer="receiver",
        subject=records[0].subject,
        action="failure",
        task_id="rollback-release",
        attempt_id="rollback-release",
        correlation_id="rollback-release",
    )
    original = store._insert

    def crash(*args):
        original(*args)
        raise RuntimeError("interrupted before transaction commit")

    monkeypatch.setattr(store, "_insert", crash)
    with pytest.raises(RuntimeError, match="transaction commit"):
        ledger.finish(claim, None, identities["receiver"], event, reason="admission_denied")
    assert ledger.get("receiver", "rollback-release")["reservation_state"] == "held"
    assert store.events() == []
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 1
    monkeypatch.setattr(store, "_insert", original)
    ledger.finish(claim, None, identities["receiver"], event, reason="admission_denied")
    assert ledger.get("receiver", "rollback-release")["reservation_state"] == "released"
    with store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 2


@pytest.mark.parametrize("transition", ["get", "cancel", "failed_finish"])
def test_old_invocation_cannot_release_or_cancel_replacement_lease(
    store, identities, records, transition
):
    store.set_budget("work", Decimal(10))
    ledger = InvocationStore(store)
    claim, _ = ledger.claim("receiver", "stale-lease", "b", "a" * 64, {}, Reservation())
    with store.engine.begin() as conn:
        conn.execute(update(leases).values(expires_at=now() - timedelta(seconds=1)))
    # The lower-level trusted-host API has a newer fence. An old invocation may
    # report lost ownership, but cannot settle or cancel this different worker.
    fence = store.acquire(claim["lease_id"], "replacement", "work", Decimal(1))
    if transition == "failed_finish":
        event = Event(
            issuer="receiver",
            subject=records[0].subject,
            action="failure",
            task_id="stale-lease",
            attempt_id="stale-lease",
            correlation_id="stale-lease",
        )
        ledger.finish(claim, None, identities["receiver"], event, reason="execution_unknown")
    else:
        getattr(ledger, transition)("receiver", "stale-lease")
    result = ledger.get("receiver", "stale-lease")
    assert result["reservation_state"] == "held" and result["state"] == "unknown"
    with store.engine.connect() as conn:
        lease = conn.execute(select(leases)).mappings().one()
        assert (lease["worker"], lease["fence"], lease["state"]) == ("replacement", fence, "active")
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 8


def test_orphaned_old_lease_is_not_reclaimed_as_new_releasable_work(store):
    from collective_intelligence_overlay.bindings import fingerprint

    store.set_budget("work", Decimal(10))
    lease_id = "invoke-" + fingerprint([store.owner, "receiver", "orphan"])
    store.acquire(lease_id, "old-worker", "work", Decimal(2))
    with store.engine.begin() as conn:
        conn.execute(
            update(leases).values(expires_at=now() - timedelta(seconds=1), actual=Decimal(1))
        )
    with pytest.raises(Conflict, match="reconcile"):
        InvocationStore(store).claim("receiver", "orphan", "b", "a" * 64, {}, Reservation())
    with store.engine.connect() as conn:
        row = conn.execute(select(leases)).mappings().one()
        assert row["worker"] == "old-worker" and row["actual"] == 1 and row["reservation"] == 2
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 8


async def test_unknown_claim_commit_is_not_refund_or_execution_authority(
    overlay, identities, records, monkeypatch
):
    effects = []

    async def operation(arguments):
        effects.append(arguments)
        return arguments["value"]

    executor, binding, context = registered(overlay, identities, records, operation)
    original = executor.store.claim

    def response_lost(*args):
        original(*args)
        raise RuntimeError("commit response lost")

    monkeypatch.setattr(executor.store, "claim", response_lost)
    with pytest.raises(RuntimeError, match="commit response lost"):
        await executor.invoke("claim-unknown", binding.id, binding.digest, {"value": 1}, context)
    result = await executor.invoke(
        "claim-unknown", binding.id, binding.digest, {"value": 1}, context
    )
    assert result["state"] == "running" and result["reservation_state"] == "held"
    assert effects == []
    with overlay.store.engine.connect() as conn:
        assert conn.execute(select(budgets.c.remaining)).scalar_one() == 9


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


@pytest.mark.parametrize("effect_happened", [False, True])
def test_process_dies_after_dispatch_before_result_commit(store, tmp_path, effect_happened):
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
if os.environ['CIO_CRASH_TEST_EFFECT'] == 'yes':
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
            "CIO_CRASH_TEST_EFFECT": "yes" if effect_happened else "no",
        },
    )
    assert process.returncode == 17
    assert marker.exists() is effect_happened
    if effect_happened:
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
