"""Durable invocation identity, bounded execution and uncertain-effect retention."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import time
from decimal import Decimal
from typing import Any

from pydantic import Field, TypeAdapter
from sqlalchemy import JSON, Column, DateTime, Integer, String, Table, func, insert, select, update

from .bindings import (
    ExecutionContext,
    Registry,
    active_invocation,
    fingerprint,
    formation_receipts,
    formation_steps,
)
from .models import Cost, Event, ExecutionReceipt, Identifier, Model, ReceiptRef, Verdict, now, uid
from .overlay import AdmissionDenied
from .security import Identity
from .storage import Conflict, Store, budgets, leases, metadata

invocations = Table(
    "invocations",
    metadata,
    Column("caller", String(160), primary_key=True),
    Column("id", String(160), primary_key=True),
    Column("owner", String(160), nullable=False),
    Column("fingerprint", String(64), nullable=False),
    Column("binding_id", String(160), nullable=False),
    Column("binding_digest", String(64), nullable=False),
    Column("request", JSON, nullable=False),
    Column("lease_id", String(160), nullable=False, unique=True),
    Column("worker", String(160), nullable=False),
    Column("fence", Integer, nullable=False),
    Column("state", String(32), nullable=False),
    Column("phase", String(32), nullable=False),
    Column("result", JSON),
    Column("result_digest", String(64)),
    Column("reason", String(160)),
    Column("receipt_id", String(160)),
    Column("reservation_state", String(32), nullable=False, server_default="legacy_unknown"),
    Column("release_reason", String(160)),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class Reservation(Model):
    """Operator allowance, not a measurement or a model-supplied spending authority."""

    unit: Identifier = "work"
    quantity: Decimal = Field(default=Decimal(1), gt=0, max_digits=24, decimal_places=9)
    seconds: int = Field(default=30, ge=1, le=300)
    minimum_remaining: Decimal = Field(default=Decimal(0), ge=0, max_digits=24, decimal_places=9)
    max_concurrent: int | None = Field(default=None, ge=1, le=32)


def _selector(caller: str, invocation_id: str) -> Any:
    TypeAdapter(Identifier).validate_python(caller)
    TypeAdapter(Identifier).validate_python(invocation_id)
    return (invocations.c.caller == caller) & (invocations.c.id == invocation_id)


def _public(row: Any) -> dict[str, Any]:
    result = {
        key: row[key]
        for key in (
            "caller",
            "id",
            "owner",
            "binding_id",
            "binding_digest",
            "fingerprint",
            "state",
            "phase",
            "result",
            "result_digest",
            "reason",
            "created_at",
            "updated_at",
            "receipt_id",
            "reservation_state",
            "release_reason",
        )
    }
    for key in ("created_at", "updated_at"):
        result[key] = row[key].isoformat()
    result["purpose"] = row["request"].get("purpose", "reuse")
    return result


class InvocationStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    @staticmethod
    def _locked(conn: Any, caller: str, invocation_id: str) -> tuple[Any, Any]:
        selector = _selector(caller, invocation_id)
        # Unit/lease identity is immutable. This first read grants no authority.
        unit = conn.execute(
            select(leases.c.unit)
            .select_from(invocations.join(leases, invocations.c.lease_id == leases.c.task_id))
            .where(selector)
        ).scalar_one_or_none()
        if unit is None:
            return None, None
        # Every invocation transition follows claim's budget -> invocation -> lease
        # order. A concurrent claim of the same ID cannot deadlock with release.
        conn.execute(select(budgets.c.unit).where(budgets.c.unit == unit).with_for_update()).one()
        row = conn.execute(select(invocations).where(selector).with_for_update()).mappings().one()
        lease = (
            conn.execute(
                select(leases).where(leases.c.task_id == row["lease_id"]).with_for_update()
            )
            .mappings()
            .one()
        )
        return row, lease

    @staticmethod
    def _release(conn: Any, row: Any, lease: Any, reason: str) -> bool:
        if not (
            row["state"] == "running"
            and row["phase"] == "reserved"
            and row["reservation_state"] == "held"
            and lease["state"] == "active"
            and row["worker"] == lease["worker"]
            and row["fence"] == lease["fence"]
        ):
            return False
        # The caller holds all three locks. Revoke dispatch ownership in this same
        # transaction before making the reserved allowance available again.
        conn.execute(
            update(leases)
            .where(leases.c.task_id == row["lease_id"])
            .values(state="cancelled", fence=leases.c.fence + 1, actual=None)
        )
        conn.execute(
            update(invocations)
            .where(_selector(row["caller"], row["id"]))
            .values(reservation_state="released", release_reason=reason)
        )
        conn.execute(
            update(budgets)
            .where(budgets.c.unit == lease["unit"])
            .values(remaining=budgets.c.remaining + lease["reservation"])
        )
        return True

    def get(self, caller: str, invocation_id: str) -> dict[str, Any] | None:
        selector = _selector(caller, invocation_id)
        with self.store.engine.begin() as conn:
            row, lease = self._locked(conn, caller, invocation_id)
            if row is None:
                return None
            if row["state"] == "running":
                if (
                    lease["expires_at"] <= now()
                    or lease["state"] != "active"
                    or lease["worker"] != row["worker"]
                    or lease["fence"] != row["fence"]
                ):
                    released = self._release(conn, row, lease, "worker_lost_or_expired")
                    conn.execute(
                        update(invocations)
                        .where(selector)
                        .values(
                            state="cancelled" if released else "unknown",
                            reason="worker_lost_or_expired",
                            updated_at=now(),
                        )
                    )
                    if not released:
                        conn.execute(
                            update(leases)
                            .where(
                                (leases.c.task_id == row["lease_id"])
                                & (leases.c.worker == row["worker"])
                                & (leases.c.fence == row["fence"])
                                & (leases.c.state == "active")
                            )
                            .values(state="cancelled", fence=leases.c.fence + 1, actual=None)
                        )
                    row = conn.execute(select(invocations).where(selector)).mappings().one()
            return _public(row)

    def claim(
        self,
        caller: str,
        invocation_id: str,
        binding_id: str,
        binding_digest: str,
        request: dict[str, Any],
        allowance: Reservation,
    ) -> tuple[dict[str, Any], bool]:
        selector = _selector(caller, invocation_id)
        request_hash = fingerprint(request)
        lease_id = "invoke-" + fingerprint([self.store.owner, caller, invocation_id])
        with self.store.engine.begin() as conn:
            # Serialize all allowance claims before locking invocation/lease/feed.
            remaining: Decimal = conn.execute(
                select(budgets.c.remaining)
                .where(budgets.c.unit == allowance.unit)
                .with_for_update()
            ).scalar_one()
            # Owner-local serialization across budget units. No other owner is
            # excluded, and finish/dispatch retain budget -> invocation -> lease.
            owner_lock = int(fingerprint(["invocation-capacity", self.store.owner])[:15], 16)
            conn.execute(select(func.pg_advisory_xact_lock(owner_lock)))
            old = (
                conn.execute(select(invocations).where(selector).with_for_update())
                .mappings()
                .one_or_none()
            )
            if old:
                if old["fingerprint"] != request_hash:
                    raise Conflict("invocation ID reused with different request")
                return dict(old), False
            if remaining < allowance.quantity + allowance.minimum_remaining:
                raise Conflict("budget exhausted or protected allowance would be consumed")
            if allowance.max_concurrent is not None:
                running = conn.execute(
                    select(invocations.c.id)
                    .where(
                        (invocations.c.owner == self.store.owner)
                        & (invocations.c.state == "running")
                    )
                    .limit(allowance.max_concurrent)
                ).all()
                if len(running) >= allowance.max_concurrent:
                    raise Conflict("owner invocation capacity exhausted")
            if (
                conn.execute(
                    select(leases.c.task_id).where(leases.c.task_id == lease_id).with_for_update()
                ).one_or_none()
                is not None
            ):
                raise Conflict("invocation lease exists without matching identity; reconcile")
            worker = uid()
            fence = self.store._acquire(
                conn, lease_id, worker, allowance.unit, allowance.quantity, allowance.seconds
            )
            values = dict(
                caller=caller,
                id=invocation_id,
                owner=self.store.owner,
                fingerprint=request_hash,
                binding_id=binding_id,
                binding_digest=binding_digest,
                request=request,
                lease_id=lease_id,
                worker=worker,
                fence=fence,
                state="running",
                phase="reserved",
                result=None,
                result_digest=None,
                reason=None,
                receipt_id=None,
                reservation_state="held",
                release_reason=None,
                created_at=now(),
                updated_at=now(),
            )
            conn.execute(insert(invocations).values(**values))
            return values, True

    def dispatched(self, claim: dict[str, Any]) -> None:
        with self.store.engine.begin() as conn:
            self._owned(conn, claim)
            conn.execute(
                update(invocations)
                .where(_selector(claim["caller"], claim["id"]))
                .values(phase="dispatched", updated_at=now())
            )

    @staticmethod
    def _owned(conn: Any, claim: dict[str, Any]) -> None:
        row, lease = InvocationStore._locked(conn, claim["caller"], claim["id"])
        if (
            row["state"] != "running"
            or row["worker"] != claim["worker"]
            or row["fence"] != claim["fence"]
            or lease["worker"] != claim["worker"]
            or lease["fence"] != claim["fence"]
            or lease["state"] != "active"
            or lease["expires_at"] <= now()
        ):
            raise Conflict("invocation worker lost execution ownership")

    def finish(
        self,
        claim: dict[str, Any],
        result: Any,
        identity: Identity,
        event: Event,
        *,
        reason: str | None = None,
    ) -> None:
        if identity.name != self.store.owner or event.issuer != self.store.owner:
            raise ValueError("invocation completion belongs to resource owner")
        with self.store.engine.begin() as conn:
            row, lease = self._locked(conn, claim["caller"], claim["id"])
            if row["worker"] != claim["worker"] or row["fence"] != claim["fence"]:
                raise Conflict("invocation worker changed")
            if row["receipt_id"] is not None:
                raise Conflict("invocation receipt already recorded")
            if reason is None:
                self._owned(conn, claim)
                if row["phase"] != "dispatched":
                    raise Conflict("completion requires durable dispatch")
            elif row["state"] == "completed":
                raise Conflict("completed invocation cannot become failed")
            released = reason is not None and self._release(conn, row, lease, reason)
            if (
                reason is not None
                and row["phase"] == "reserved"
                and row["reservation_state"] in {"held", "released"}
            ):
                # Inspection used resources even when its execution allowance is
                # released. Sign this observation once; never negate an old cost.
                event = event.model_copy(
                    update={
                        "costs": tuple(
                            cost.model_copy(update={"category": "overhead"}) for cost in event.costs
                        )
                    }
                )
            self.store._insert(conn, event, identity.sign(event))
            terminal = row["state"] != "running"
            conn.execute(
                update(invocations)
                .where(_selector(claim["caller"], claim["id"]))
                .values(
                    state=row["state"] if terminal else "unknown" if reason else "completed",
                    result=result,
                    result_digest=fingerprint(result) if reason is None else None,
                    reason=row["reason"] if terminal else reason,
                    receipt_id=event.id,
                    updated_at=now(),
                    reservation_state="released"
                    if released
                    else "consumed"
                    if reason is None and row["reservation_state"] == "held"
                    else row["reservation_state"],
                )
            )
            if not terminal and not released:
                conn.execute(
                    update(leases)
                    .where(
                        (leases.c.task_id == claim["lease_id"])
                        & (leases.c.worker == claim["worker"])
                        & (leases.c.fence == claim["fence"])
                        & (leases.c.state == "active")
                    )
                    .values(state="cancelled" if reason else "complete", actual=None)
                )

    def cancel(self, caller: str, invocation_id: str) -> dict[str, Any] | None:
        with self.store.engine.begin() as conn:
            selector = _selector(caller, invocation_id)
            row, lease = self._locked(conn, caller, invocation_id)
            if row is None:
                return None
            if row["state"] == "running":
                released = self._release(conn, row, lease, "cancelled_by_caller")
                if not released:
                    conn.execute(
                        update(leases)
                        .where(
                            (leases.c.task_id == row["lease_id"])
                            & (leases.c.worker == row["worker"])
                            & (leases.c.fence == row["fence"])
                            & (leases.c.state == "active")
                        )
                        .values(state="cancelled", fence=leases.c.fence + 1, actual=None)
                    )
                conn.execute(
                    update(invocations)
                    .where(selector)
                    .values(
                        state="cancelled" if released else "unknown",
                        reason="cancelled_by_caller",
                        updated_at=now(),
                    )
                )
                row = conn.execute(select(invocations).where(selector)).mappings().one()
            return _public(row)


class Executor:
    """Finite execution; retrieval/cancellation do not manufacture truth evidence."""

    def __init__(self, registry: Registry, identity: Identity, allowance: Reservation) -> None:
        self.registry, self.identity, self.allowance = registry, identity, allowance
        self.store = InvocationStore(registry.overlay.store)
        self._cleanup: set[asyncio.Task[None]] = set()
        if identity.name != self.store.store.owner:
            raise ValueError("executor identity must own resources")

    async def invoke(
        self,
        invocation_id: str,
        binding_id: str,
        binding_digest: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
        *,
        minimum_remaining: Decimal | None = None,
    ) -> dict[str, Any]:
        allowance = (
            self.allowance
            if minimum_remaining is None
            else Reservation.model_validate(
                {
                    **self.allowance.model_dump(),
                    "minimum_remaining": max(self.allowance.minimum_remaining, minimum_remaining),
                }
            )
        )
        arguments = copy.deepcopy(arguments)
        context = context.model_copy(deep=True)
        steps = formation_steps.get()
        if steps is not None:
            if steps[0] >= steps[1]:
                raise ValueError("formation invocation step budget exhausted")
            steps[0] += 1
        request = {
            "owner": self.identity.name,
            "caller": context.caller,
            "purpose": context.purpose,
            "binding": binding_id,
            "binding_digest": binding_digest,
            "arguments": arguments,
            "environment": context.environment,
            "permissions": sorted(context.permissions),
        }
        old = await asyncio.to_thread(self.store.get, context.caller, invocation_id)
        if old:
            if old["fingerprint"] != fingerprint(request):
                raise Conflict("invocation ID reused with different request")
            self._observe(old)
            return old
        prepared = self.registry.prepare(binding_id, binding_digest, arguments, context)
        started = time.perf_counter()
        parent_invocation = active_invocation.get()

        def event(claim: dict[str, Any], failed: bool, output: Any = None) -> Event:
            return Event(
                schema_version="2",
                id=claim["lease_id"],
                issuer=self.identity.name,
                subject=prepared.binding.subject,
                action="failure" if failed else context.purpose,
                task_id=invocation_id,
                attempt_id=claim["lease_id"],
                correlation_id=invocation_id,
                outcome=Verdict.UNKNOWN,
                costs=(
                    Cost(
                        category="failure"
                        if failed
                        else "verification"
                        if context.purpose == "verification"
                        else "use",
                        status="measured",
                        quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                        unit="wall_seconds",
                    ),
                    Cost(
                        category="verification" if context.purpose == "verification" else "use",
                        status="unavailable",
                        quantity=None,
                        unit="USD",
                    ),
                ),
                execution=ExecutionReceipt(
                    purpose=context.purpose,
                    invocation_id=invocation_id,
                    caller=context.caller,
                    resource_owner=self.identity.name,
                    capability_issuer=prepared.binding.issuer,
                    binding_digest=binding_digest,
                    arguments_digest=prepared.arguments_digest,
                    result_digest=None if failed else fingerprint(output),
                    scope=prepared.request.scope,
                    policy_digest=self.registry.overlay.policy.digest,
                    state="unknown" if failed else "completed",
                    transport=prepared.binding.target.kind,
                    parent_invocation=parent_invocation,
                ),
            )

        claiming = asyncio.create_task(
            asyncio.to_thread(
                self.store.claim,
                context.caller,
                invocation_id,
                binding_id,
                binding_digest,
                request,
                allowance,
            )
        )
        try:
            claim, fresh = await asyncio.shield(claiming)
        except asyncio.CancelledError:

            async def settle() -> None:
                # Cancellation of the await says nothing about the thread's
                # commit. Only a confirmed fresh claim may be settled here.
                with contextlib.suppress(Exception):
                    delayed_claim, is_fresh = await claiming
                    if is_fresh:
                        await asyncio.to_thread(
                            self.store.finish,
                            delayed_claim,
                            None,
                            self.identity,
                            event(delayed_claim, True),
                            reason="cancelled_during_claim",
                        )

            cleanup = asyncio.create_task(settle())
            self._cleanup.add(cleanup)
            cleanup.add_done_callback(self._cleanup.discard)
            await asyncio.shield(cleanup)
            raise
        if not fresh:
            existing = _public(claim)
            self._observe(existing)
            return existing
        invocation_token = active_invocation.set(
            fingerprint([self.identity.name, context.caller, invocation_id])
        )

        async def boundary() -> None:
            await asyncio.to_thread(self.store.dispatched, claim)

        try:
            async with asyncio.timeout(self.allowance.seconds):
                result = await self.registry.execute(
                    binding_id, binding_digest, arguments, context, before_call=boundary
                )
                completed_event = event(claim, False, result)
                await asyncio.to_thread(
                    self.store.finish, claim, result, self.identity, completed_event
                )
        except BaseException as exc:
            reason = "admission_denied" if isinstance(exc, AdmissionDenied) else "execution_unknown"
            with contextlib.suppress(Conflict):
                await asyncio.shield(
                    asyncio.to_thread(
                        self.store.finish,
                        claim,
                        None,
                        self.identity,
                        event(claim, True),
                        reason=reason,
                    )
                )
            if not isinstance(exc, Exception):
                raise
        finally:
            active_invocation.reset(invocation_token)
        result_record = await asyncio.to_thread(self.store.get, context.caller, invocation_id)
        assert result_record is not None
        self._observe(result_record)
        return result_record

    def _observe(self, result: dict[str, Any]) -> None:
        sink = formation_receipts.get()
        if (
            sink is not None
            and result["state"] == "completed"
            and result.get("receipt_id")
            and result.get("purpose") == "reuse"
        ):
            ref = ReceiptRef(issuer=result["owner"], id=result["receipt_id"])
            if ref not in sink:
                if len(sink) >= 64:
                    raise ValueError("formation receipt budget exceeded")
                sink.append(ref)
