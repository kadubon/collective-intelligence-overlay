"""Durable invocation identity, bounded execution and uncertain-effect retention."""

from __future__ import annotations

import asyncio
import contextlib
import copy
import time
from contextvars import ContextVar
from datetime import datetime
from decimal import Decimal
from typing import Any, Literal, cast

from pydantic import Field, TypeAdapter
from sqlalchemy import (
    JSON,
    Boolean,
    Column,
    DateTime,
    Integer,
    String,
    Table,
    func,
    insert,
    or_,
    select,
    update,
)

from .bindings import (
    ExecutionContext,
    Registry,
    active_invocation,
    fingerprint,
    formation_receipts,
    formation_steps,
)
from .blocking import BlockingCapacity, run_blocking
from .calls import ProviderResponseMismatch
from .models import (
    Cost,
    Event,
    ExecutionReceipt,
    Identifier,
    InvocationObservation,
    Model,
    ReceiptRef,
    Verdict,
    now,
    uid,
)
from .overlay import AdmissionDenied
from .security import Identity, verify
from .storage import Conflict, Store, budgets, leases, metadata, records

_allowance_floors: ContextVar[dict[tuple[str, str], Decimal] | None] = ContextVar(
    "allowance_floors", default=None
)

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

invocation_resolutions = Table(
    "invocation_resolutions",
    metadata,
    Column("caller", String(160), primary_key=True),
    Column("invocation_id", String(160), primary_key=True),
    Column("owner", String(160), nullable=False),
    Column("invocation_context", String(64), nullable=False, unique=True),
    Column("receipt_id", String(160), nullable=False),
    Column("state_digest", String(64), nullable=False),
    Column("revisions", JSON, nullable=False),
    Column("closed", Boolean, nullable=False),
    Column("closed_at", DateTime(timezone=True), nullable=False),
)


def uncertain_effects(owner: str, *, current: bool = True) -> Any:
    """One predicate for the admission gate and owner-local operational counts."""
    predicate = (
        (invocations.c.owner == owner)
        & invocations.c.state.in_(("unknown", "cancelled", "rejected"))
        & invocations.c.reservation_state.in_(("held", "legacy_unknown"))
    )
    if current:
        predicate &= (
            ~select(invocation_resolutions.c.invocation_id)
            .where(
                (invocation_resolutions.c.owner == invocations.c.owner)
                & (invocation_resolutions.c.caller == invocations.c.caller)
                & (invocation_resolutions.c.invocation_id == invocations.c.id)
                & invocation_resolutions.c.closed.is_(True)
            )
            .exists()
        )
    return predicate


class Reservation(Model):
    """Operator allowance, not a measurement or a model-supplied spending authority."""

    unit: Identifier = "work"
    quantity: Decimal = Field(default=Decimal(1), gt=0, max_digits=24, decimal_places=9)
    seconds: int = Field(default=30, ge=1, le=300)
    minimum_remaining: Decimal = Field(default=Decimal(0), ge=0, max_digits=24, decimal_places=9)
    max_concurrent: int | None = Field(default=None, ge=1, le=32)
    max_unresolved: int = Field(default=32, ge=1, le=1024)


class _MaintenanceRequired(Conflict):
    """A stopped new claim may make one bounded maintenance pass before retrying."""

    def __init__(self, message: str, reason: str) -> None:
        super().__init__(message)
        self.reason = reason


class UnresolvedEffectsLimit(Conflict):
    """Owner policy refuses further work until original uncertain effects are reconciled."""


def invocation_request(
    owner: str,
    binding_id: str,
    binding_digest: str,
    arguments: dict[str, Any],
    context: ExecutionContext,
) -> dict[str, Any]:
    """The existing immutable content contract, independent of invocation identity."""
    return {
        "owner": owner,
        "caller": context.caller,
        "purpose": context.purpose,
        "binding": binding_id,
        "binding_digest": binding_digest,
        "arguments": arguments,
        "environment": context.environment,
        "permissions": sorted(context.permissions),
    }


def released_before_dispatch(row: Any, lease: Any) -> bool:
    """Positive persisted proof; absence, timeout and cancellation alone prove nothing."""
    return bool(
        row is not None
        and lease is not None
        and row["state"] in {"cancelled", "rejected", "unknown"}
        and row["phase"] == "reserved"
        and row["reservation_state"] == "released"
        and lease["state"] == "cancelled"
        and lease["worker"] == row["worker"]
        and lease["fence"] > row["fence"]
        and lease["actual"] is None
    )


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
    result["arguments_digest"] = (
        fingerprint(row["request"]["arguments"]) if "arguments" in row["request"] else None
    )
    return result


def invocation_basis_id(owner: str, caller: str, invocation_id: str, phase: str) -> str:
    return "invocation-" + fingerprint([owner, caller, invocation_id, phase])


class InvocationStore:
    def __init__(
        self, store: Store, identity: Identity | None = None, registry: Registry | None = None
    ) -> None:
        self.store, self.identity, self.registry = store, identity, registry
        if (identity is None) != (registry is None) or (identity and identity.name != store.owner):
            raise ValueError("invocation transaction signer must own the installed registry")

    def _anchor(self, conn: Any, row: Any, phase: Literal["accepted", "dispatched"]) -> None:
        if self.identity is None or self.registry is None:
            # Low-level legacy callers are not silently upgraded into signed facts.
            return
        binding = self.registry.inspect(row["binding_id"], expected_digest=row["binding_digest"])
        accepted_ref = None
        accepted_observation = None
        parent = active_invocation.get()
        if phase == "dispatched":
            accepted_ref = ReceiptRef(
                issuer=self.store.owner,
                id=invocation_basis_id(self.store.owner, row["caller"], row["id"], "accepted"),
            )
            envelope = conn.execute(
                select(records.c.envelope).where(
                    (records.c.issuer == self.store.owner)
                    & (records.c.kind == "event")
                    & (records.c.record_id == accepted_ref.id)
                )
            ).scalar_one()
            accepted = verify(envelope, self.store.principals)
            if not isinstance(accepted, Event) or accepted.invocation_observation is None:
                raise Conflict("invocation acceptance anchor missing")
            accepted_observation = accepted.invocation_observation
            parent = accepted_observation.parent_invocation
        anchor = InvocationObservation(
            caller=row["caller"],
            invocation_id=row["id"],
            resource_owner=self.store.owner,
            binding_id=row["binding_id"],
            binding_digest=row["binding_digest"],
            request_fingerprint=row["fingerprint"],
            arguments_digest=fingerprint(row["request"]["arguments"]),
            scope=binding.scope,
            lease_id=row["lease_id"],
            worker=row["worker"],
            fence=row["fence"],
            phase=phase,
            origin="execution_transaction",
            accepted_receipt=accepted_ref,
            parent_invocation=parent,
        )
        if (
            accepted_observation is not None
            and accepted_observation.model_copy(
                update={"phase": "dispatched", "accepted_receipt": accepted_ref}
            )
            != anchor
        ):
            raise Conflict("invocation acceptance content changed before dispatch")
        event = Event(
            schema_version="6",
            id=invocation_basis_id(self.store.owner, row["caller"], row["id"], phase),
            issuer=self.store.owner,
            subject=binding.subject,
            action="recommendation",
            task_id=row["id"],
            attempt_id=row["lease_id"],
            correlation_id=row["fingerprint"],
            causation_id=accepted_ref.id if accepted_ref else None,
            invocation_observation=anchor,
        )
        self.store._insert(conn, event, self.identity.sign(event))

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
    def _releasable(row: Any, lease: Any) -> bool:
        return bool(
            row["state"] == "running"
            and row["phase"] == "reserved"
            and row["reservation_state"] == "held"
            and lease["state"] == "active"
            and row["worker"] == lease["worker"]
            and row["fence"] == lease["fence"]
            and lease["actual"] is None
        )

    @staticmethod
    def _release(conn: Any, row: Any, lease: Any, reason: str) -> bool:
        if not InvocationStore._releasable(row, lease):
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

    @classmethod
    def _expire_locked(cls, conn: Any, row: Any, lease: Any) -> Any:
        # The stored timestamptz deadline and PostgreSQL wall clock are authoritative.
        observed: datetime = conn.execute(select(func.clock_timestamp())).scalar_one()
        if row["state"] != "running" or (
            lease["expires_at"] > observed
            and lease["state"] == "active"
            and lease["worker"] == row["worker"]
            and lease["fence"] == row["fence"]
        ):
            return row
        selector = _selector(row["caller"], row["id"])
        released = cls._release(conn, row, lease, "worker_lost_or_expired")
        conn.execute(
            update(invocations)
            .where(selector)
            .values(
                state="cancelled" if released else "unknown",
                reason="worker_lost_or_expired",
                updated_at=observed,
            )
        )
        if not released:
            # Never cancel a replacement lease owned by a different worker/fence.
            conn.execute(
                update(leases)
                .where(
                    (leases.c.task_id == row["lease_id"])
                    & (leases.c.worker == row["worker"])
                    & (leases.c.fence == row["fence"])
                    & (leases.c.state == "active")
                )
                .values(state="cancelled", fence=leases.c.fence + 1)
            )
        return conn.execute(select(invocations).where(selector)).mappings().one()

    def get(self, caller: str, invocation_id: str) -> dict[str, Any] | None:
        with self.store.engine.begin() as conn:
            row, lease = self._locked(conn, caller, invocation_id)
            return None if row is None else _public(self._expire_locked(conn, row, lease))

    def cleanup_expired(
        self, *, owner: str, limit: int = 32, seconds: int = 5, dry_run: bool = False
    ) -> dict[str, Any]:
        """Inspect/fence a finite owner-local batch; never invoke or infer external effects.

        ``seconds`` bounds database work after connection acquisition. The Store's
        separate finite pool/connect timeouts still apply. A DB timeout/failure is
        raised; committed earlier rows remain safe to inspect and rerun.
        """
        if owner != self.store.owner:
            raise ValueError("invocation cleanup belongs to the configured owner")
        if not 1 <= limit <= 128 or not 1 <= seconds <= 30:
            raise ValueError("cleanup bounds: limit 1..128, seconds 1..30")
        deadline = time.monotonic() + seconds

        def bounded(conn: Any) -> bool:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return False
            # Each row uses fewer than 16 statements, with no cross-unit transaction.
            ms = str(max(1, int(remaining * 1000 / 16)))
            conn.execute(select(func.set_config("statement_timeout", ms, True)))
            conn.execute(select(func.set_config("lock_timeout", ms, True)))
            return True

        with self.store.engine.begin() as conn:
            if not bounded(conn):
                raise Conflict("cleanup time budget ended before candidate query; rerun")
            candidates = conn.execute(
                select(invocations.c.caller, invocations.c.id)
                .select_from(
                    invocations.outerjoin(leases, invocations.c.lease_id == leases.c.task_id)
                )
                .where(
                    (invocations.c.owner == owner)
                    & (invocations.c.state == "running")
                    & or_(
                        leases.c.task_id.is_(None),
                        leases.c.expires_at <= func.clock_timestamp(),
                        leases.c.state != "active",
                        leases.c.worker != invocations.c.worker,
                        leases.c.fence != invocations.c.fence,
                    )
                )
                .order_by(invocations.c.created_at, invocations.c.caller, invocations.c.id)
                .limit(limit + 1)
            ).all()
        items = []
        processed = 0
        for candidate in candidates[:limit]:
            caller, invocation_id = cast(str, candidate[0]), cast(str, candidate[1])
            with self.store.engine.begin() as conn:
                if not bounded(conn):
                    break
                row, lease = self._locked(conn, caller, invocation_id)
                if row is None:
                    raise Conflict(
                        "invocation lease mapping missing; operator reconciliation required"
                    )
                if row["owner"] != owner:
                    raise Conflict("invocation owner changed")
                observed: datetime = conn.execute(select(func.clock_timestamp())).scalar_one()
                eligible = row["state"] == "running" and (
                    lease["expires_at"] <= observed
                    or lease["state"] != "active"
                    or lease["worker"] != row["worker"]
                    or lease["fence"] != row["fence"]
                )
                before = row["state"]
                action = (
                    "release_undispatched"
                    if eligible and self._releasable(row, lease)
                    else "retain_unknown_effect"
                    if eligible
                    else "no_longer_eligible"
                )
                if eligible and not dry_run:
                    row = self._expire_locked(conn, row, lease)
                    lease = (
                        conn.execute(select(leases).where(leases.c.task_id == row["lease_id"]))
                        .mappings()
                        .one()
                    )
                items.append(
                    {
                        "caller": caller,
                        "id": invocation_id,
                        "previous_state": before,
                        "state": row["state"],
                        "phase": row["phase"],
                        "reservation_state": row["reservation_state"],
                        "reason": row["reason"],
                        "lease_state": lease["state"],
                        "lease_expires_at": lease["expires_at"].isoformat(),
                        "observed_at": observed.isoformat(),
                        "eligible": eligible,
                        "action": action,
                        "logical_slot_recovered": eligible and not dry_run,
                        "physical_task": "not_observed",
                        "external_effect": "not_dispatched"
                        if action == "release_undispatched"
                        else "unconfirmed",
                    }
                )
            processed += 1
        return {
            "owner": owner,
            "dry_run": dry_run,
            "items": items,
            "has_more": len(candidates) > processed,
            "required": "query original IDs; cleanup does not confirm external effect completion",
        }

    def claim(
        self,
        caller: str,
        invocation_id: str,
        binding_id: str,
        binding_digest: str,
        request: dict[str, Any],
        allowance: Reservation,
    ) -> tuple[dict[str, Any], bool]:
        try:
            return self._claim(
                caller, invocation_id, binding_id, binding_digest, request, allowance
            )
        except _MaintenanceRequired:
            # Roll back the stopped claim first. Cleanup locks exactly one budget
            # unit per transaction, never while holding claim's owner advisory lock.
            self.cleanup_expired(owner=self.store.owner, limit=32, seconds=5)
            return self._claim(
                caller, invocation_id, binding_id, binding_digest, request, allowance
            )

    def _claim(
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
                raise _MaintenanceRequired(
                    "budget exhausted or protected allowance would be consumed",
                    "owner_budget_refused",
                )
            unresolved = conn.execute(
                select(invocations.c.id)
                .where(uncertain_effects(self.store.owner))
                .limit(allowance.max_unresolved)
            ).all()
            if len(unresolved) >= allowance.max_unresolved:
                raise UnresolvedEffectsLimit(
                    "owner unresolved effects limit reached; query original IDs and reconcile"
                )
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
                    raise _MaintenanceRequired(
                        "owner invocation capacity exhausted", "owner_execution_capacity_refused"
                    )
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
            self._anchor(conn, values, "accepted")
            return values, True

    def dispatched(self, claim: dict[str, Any]) -> None:
        with self.store.engine.begin() as conn:
            self._owned(conn, claim)
            self._anchor(conn, claim, "dispatched")
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
            or lease["expires_at"] <= conn.execute(select(func.clock_timestamp())).scalar_one()
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
        self.store = InvocationStore(registry.overlay.store, identity, registry)
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
        floor_key = (self.identity.name, self.allowance.unit)
        allowance = Reservation.model_validate(
            {
                **self.allowance.model_dump(),
                "minimum_remaining": max(
                    self.allowance.minimum_remaining,
                    (_allowance_floors.get() or {}).get(floor_key, Decimal(0)),
                    Decimal(0) if minimum_remaining is None else minimum_remaining,
                ),
            }
        )
        arguments = copy.deepcopy(arguments)
        context = context.model_copy(deep=True)
        steps = formation_steps.get()
        if steps is not None:
            if steps[0] >= steps[1]:
                raise ValueError("formation invocation step budget exhausted")
            steps[0] += 1
        request = invocation_request(
            self.identity.name, binding_id, binding_digest, arguments, context
        )
        old = await run_blocking(self.store.get, context.caller, invocation_id)
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
            run_blocking(
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
                        await run_blocking(
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
        floor_token = _allowance_floors.set(
            {**(_allowance_floors.get() or {}), floor_key: allowance.minimum_remaining}
        )

        async def boundary() -> None:
            await run_blocking(self.store.dispatched, claim)

        try:
            async with asyncio.timeout(self.allowance.seconds):
                result = await self.registry.execute(
                    binding_id,
                    binding_digest,
                    arguments,
                    context,
                    before_call=boundary,
                    call_id=invocation_id,
                )
                completed_event = event(claim, False, result)
                await run_blocking(self.store.finish, claim, result, self.identity, completed_event)
        except BaseException as exc:
            if isinstance(exc, AdmissionDenied):
                reason = "admission_denied"
            elif isinstance(exc, _MaintenanceRequired):
                reason = exc.reason
            elif isinstance(exc, UnresolvedEffectsLimit):
                reason = "owner_unresolved_effects_refused"
            elif isinstance(exc, BlockingCapacity):
                reason = "owner_blocking_capacity_refused"
            elif isinstance(exc, ProviderResponseMismatch):
                reason = exc.reason
            elif isinstance(exc, TimeoutError):
                reason = "execution_timed_out"
            elif isinstance(exc, asyncio.CancelledError):
                reason = "execution_cancelled"
            else:
                reason = "execution_unknown"
            with contextlib.suppress(Conflict):
                await asyncio.shield(
                    run_blocking(
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
            _allowance_floors.reset(floor_token)
            active_invocation.reset(invocation_token)
        result_record = await run_blocking(self.store.get, context.caller, invocation_id)
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
