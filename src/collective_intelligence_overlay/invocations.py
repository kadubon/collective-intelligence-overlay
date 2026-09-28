"""Durable invocation identity, bounded execution and uncertain-effect retention."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import time
from decimal import Decimal
from typing import Any

from pydantic import Field, TypeAdapter
from sqlalchemy import JSON, Column, DateTime, Integer, String, Table, insert, select, update

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
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("updated_at", DateTime(timezone=True), nullable=False),
)


class Reservation(Model):
    """Operator allowance, not a measurement or a model-supplied spending authority."""

    unit: Identifier = "work"
    quantity: Decimal = Field(default=Decimal(1), gt=0, max_digits=24, decimal_places=9)
    seconds: int = Field(default=30, ge=1, le=300)


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
        )
    }
    for key in ("created_at", "updated_at"):
        result[key] = row[key].isoformat()
    result["purpose"] = row["request"].get("purpose", "reuse")
    return result


class InvocationStore:
    def __init__(self, store: Store) -> None:
        self.store = store

    def get(self, caller: str, invocation_id: str) -> dict[str, Any] | None:
        selector = _selector(caller, invocation_id)
        with self.store.engine.begin() as conn:
            row = (
                conn.execute(select(invocations).where(selector).with_for_update())
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            if row["state"] == "running":
                lease = (
                    conn.execute(
                        select(leases).where(leases.c.task_id == row["lease_id"]).with_for_update()
                    )
                    .mappings()
                    .one()
                )
                if lease["expires_at"] <= now() or lease["state"] != "active":
                    conn.execute(
                        update(invocations)
                        .where(selector)
                        .values(
                            state="unknown",
                            reason="worker_lost_or_expired",
                            updated_at=now(),
                        )
                    )
                    conn.execute(
                        update(leases)
                        .where(leases.c.task_id == row["lease_id"])
                        .values(state="cancelled", actual=None)
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
            conn.execute(
                select(budgets.c.remaining)
                .where(budgets.c.unit == allowance.unit)
                .with_for_update()
            ).scalar_one()
            old = (
                conn.execute(select(invocations).where(selector).with_for_update())
                .mappings()
                .one_or_none()
            )
            if old:
                if old["fingerprint"] != request_hash:
                    raise Conflict("invocation ID reused with different request")
                return dict(old), False
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
        row = (
            conn.execute(
                select(invocations).where(_selector(claim["caller"], claim["id"])).with_for_update()
            )
            .mappings()
            .one()
        )
        lease = (
            conn.execute(
                select(leases).where(leases.c.task_id == row["lease_id"]).with_for_update()
            )
            .mappings()
            .one()
        )
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
            self._owned(conn, claim)
            self.store._insert(conn, event, identity.sign(event))
            conn.execute(
                update(invocations)
                .where(_selector(claim["caller"], claim["id"]))
                .values(
                    state="unknown" if reason else "completed",
                    result=result,
                    result_digest=fingerprint(result) if reason is None else None,
                    reason=reason,
                    receipt_id=event.id,
                    updated_at=now(),
                )
            )
            conn.execute(
                update(leases)
                .where(leases.c.task_id == claim["lease_id"])
                .values(state="cancelled" if reason else "complete", actual=None)
            )

    def cancel(self, caller: str, invocation_id: str) -> dict[str, Any] | None:
        with self.store.engine.begin() as conn:
            selector = _selector(caller, invocation_id)
            row = (
                conn.execute(select(invocations).where(selector).with_for_update())
                .mappings()
                .one_or_none()
            )
            if row is None:
                return None
            if row["state"] == "running":
                conn.execute(
                    select(leases).where(leases.c.task_id == row["lease_id"]).with_for_update()
                )
                conn.execute(
                    update(leases)
                    .where(leases.c.task_id == row["lease_id"])
                    .values(state="cancelled", fence=leases.c.fence + 1, actual=None)
                )
                conn.execute(
                    update(invocations)
                    .where(selector)
                    .values(
                        state="unknown" if row["phase"] == "dispatched" else "cancelled",
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
        if identity.name != self.store.store.owner:
            raise ValueError("executor identity must own resources")

    async def invoke(
        self,
        invocation_id: str,
        binding_id: str,
        binding_digest: str,
        arguments: dict[str, Any],
        context: ExecutionContext,
    ) -> dict[str, Any]:
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
        claim, fresh = await asyncio.to_thread(
            self.store.claim,
            context.caller,
            invocation_id,
            binding_id,
            binding_digest,
            request,
            self.allowance,
        )
        if not fresh:
            existing = _public(claim)
            self._observe(existing)
            return existing
        started = time.perf_counter()
        parent_invocation = active_invocation.get()
        invocation_token = active_invocation.set(
            fingerprint([self.identity.name, context.caller, invocation_id])
        )

        def event(failed: bool, output: Any = None) -> Event:
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

        async def boundary() -> None:
            await asyncio.to_thread(self.store.dispatched, claim)

        try:
            async with asyncio.timeout(self.allowance.seconds):
                result = await self.registry.execute(
                    binding_id, binding_digest, arguments, context, before_call=boundary
                )
                completed_event = event(False, result)
                await asyncio.to_thread(
                    self.store.finish, claim, result, self.identity, completed_event
                )
        except BaseException as exc:
            reason = "admission_denied" if isinstance(exc, AdmissionDenied) else "execution_unknown"
            with contextlib.suppress(Conflict):
                await asyncio.shield(
                    asyncio.to_thread(
                        self.store.finish, claim, None, self.identity, event(True), reason=reason
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
