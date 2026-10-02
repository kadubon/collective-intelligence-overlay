"""Owner review and finite current-effect projection over the existing signed Store."""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel, ConfigDict, TypeAdapter
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert

from .bindings import ExecutionContext, Registry, fingerprint
from .blocking import run_blocking
from .calls import RemoteCalls, remote_calls
from .config import Config
from .invocations import InvocationStore, _public, invocation_resolutions, invocations
from .models import (
    Cost,
    Digest,
    Event,
    Identifier,
    Outcome,
    ReceiptRef,
    ResolutionReceipt,
    Verdict,
    now,
    uid,
)
from .security import Identity, verify
from .storage import Conflict, budgets, feed_state, leases, records, subject_key

if TYPE_CHECKING:
    from .reconciliation import Reconciliations


class ResolutionObservation(BaseModel):
    """Installed application query must positively inventory all local/remote effects.

    It must also establish physical worker/actuator quiescence; a cancelled lease
    alone proves neither that fact nor absence of an effect. Unknown fails closed.
    """

    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)
    caller: Identifier
    invocation_id: Identifier
    state_digest: Digest
    effect: Literal["confirmed", "absent", "unknown"]
    all_effects_checked: bool
    all_results_checked: bool
    worker_quiescent: bool
    observation_digest: Digest
    reason: Identifier


class Resolutions:
    def __init__(
        self,
        registry: Registry,
        config: Config,
        identity: Identity,
        reconciliations: Reconciliations,
        *,
        maximum_observation_age: int = 300,
    ) -> None:
        if not 1 <= maximum_observation_age <= 300:
            raise ValueError("resolution observation age must be 1..300 seconds")
        self.registry, self.config, self.identity = registry, config, identity
        self.reconciliations, self.store = reconciliations, registry.overlay.store
        self.maximum_observation_age = maximum_observation_age
        self._queries: dict[str, str] = {}

    def register(self, binding_id: str) -> None:
        binding = self.registry.inspect(binding_id)
        if (
            binding.issuer != self.store.owner
            or binding.effects != "read-only"
            or self.store.owner not in binding.verification_callers
            or binding_id in self._queries
            or len(self._queries) >= 32
        ):
            raise ValueError("resolution needs one owner-approved read-only whole-invocation query")
        self._queries[binding_id] = binding.digest

    def _event(self, conn: Any, ref: ReceiptRef) -> Event:
        if ref.issuer != self.store.owner:
            raise ValueError("resolution observations must belong to the local owner")
        envelope = conn.execute(
            select(records.c.envelope).where(
                (records.c.kind == "event")
                & (records.c.issuer == ref.issuer)
                & (records.c.record_id == ref.id)
            )
        ).scalar_one_or_none()
        if envelope is None:
            raise ValueError("resolution observation missing")
        event = verify(envelope, self.store.principals)
        if not isinstance(event, Event):
            raise ValueError("resolution observation is not an event")
        return event

    def _snapshot(
        self,
        conn: Any,
        caller: str,
        invocation_id: str,
        checker: str,
        observations: tuple[ReceiptRef, ...],
    ) -> tuple[dict[str, Any], dict[str, int]]:
        row = (
            conn.execute(
                select(invocations).where(
                    (invocations.c.owner == self.store.owner)
                    & (invocations.c.caller == caller)
                    & (invocations.c.id == invocation_id)
                )
            )
            .mappings()
            .one_or_none()
        )
        if (
            row is None
            or row["state"] not in {"unknown", "cancelled", "rejected"}
            or row["reservation_state"] not in {"held", "legacy_unknown"}
            or row["receipt_id"] is None
        ):
            raise ValueError("resolution requires an original terminal uncertain receipt")
        lease = (
            conn.execute(select(leases).where(leases.c.task_id == row["lease_id"])).mappings().one()
        )
        if (
            lease["state"] == "active"
            or lease["worker"] != row["worker"]
            or lease["fence"] < row["fence"]
        ):
            raise ValueError("original worker is not logically fenced")
        original_ref = ReceiptRef(issuer=self.store.owner, id=row["receipt_id"])
        original = self._event(conn, original_ref)
        if (
            original.execution is None
            or original.execution.state == "completed"
            or original.execution.resource_owner != self.store.owner
            or original.execution.invocation_id != invocation_id
            or original.execution.caller != caller
            or original.execution.binding_digest != row["binding_digest"]
            or row["fingerprint"] != fingerprint(row["request"])
            or "arguments" not in row["request"]
            or original.execution.arguments_digest != fingerprint(row["request"]["arguments"])
        ):
            raise ValueError("original uncertain receipt or legacy request is incomplete")
        binding = self.registry.inspect(row["binding_id"], expected_digest=row["binding_digest"])
        if original.execution.scope != binding.scope:
            raise ValueError("original uncertain receipt scope does not match its manifest")
        invocation_context = fingerprint([self.store.owner, caller, invocation_id])
        rows = (
            conn.execute(
                select(remote_calls)
                .where(
                    (remote_calls.c.owner == self.store.owner)
                    & (remote_calls.c.caller == caller)
                    & (remote_calls.c.invocation_context == invocation_context)
                )
                .order_by(remote_calls.c.call_key)
                .limit(65)
            )
            .mappings()
            .all()
        )
        if (
            len(rows) > 64
            or len(observations) != len(rows)
            or len({ref.id for ref in observations}) != len(observations)
        ):
            raise ValueError(
                "resolution must review every saved remote child within the finite bound"
            )
        calls = [RemoteCalls._reference(value) for value in rows]
        mapped = {value.call_key: value for value in calls}
        observed = {}
        support = {
            subject_key(binding.subject),
            subject_key(self.registry.inspect(checker).subject),
        }
        for ref in observations:
            event = self._event(conn, ref)
            r = event.reconciliation
            if r is None or r.call_key not in mapped or r.call_key in observed:
                raise ValueError("resolution remote observation does not match the complete map")
            saved = mapped[r.call_key]
            if (
                r.caller != caller
                or r.original_invocation_id != invocation_id
                or r.original_receipt != original_ref
                or r.effect == "unknown"
                or r.reported_state not in {"completed", "cancelled", "rejected"}
                or r.provider != saved.provider
                or r.provider_invocation_id != saved.remote_invocation_id
                or r.local_binding_digest != saved.binding_digest
                or r.provider_binding_digest != saved.provider_binding_digest
                or r.arguments_digest != saved.arguments_digest
                or saved.arguments_digest is None
                or r.request_fingerprint != saved.request_fingerprint
                or r.effect_observation_digest is None
                or r.reconciler_binding_digest is None
            ):
                raise ValueError("remote effect/result remains unknown or mismatched")
            if r.effect == "confirmed" and (
                r.reported_state != "completed" or r.provider_result_digest is None
            ):
                raise ValueError("confirmed remote result is incomplete")
            observed_at = conn.execute(select(func.clock_timestamp())).scalar_one()
            if event.occurred_at > observed_at + timedelta(
                seconds=5
            ) or observed_at - event.occurred_at > timedelta(seconds=self.maximum_observation_age):
                raise ValueError("resolution remote observation is stale")
            query = self.reconciliations.installed_query(r.reconciler_binding_digest)
            support.add(subject_key(self.registry.inspect(query).subject))
            observed[r.call_key] = event.model_dump(mode="json")
        if conn.execute(
            select(feed_state.c.restore_pending).where(feed_state.c.id == 1)
        ).scalar_one():
            raise ValueError("restored state requires separate recovery review before resolution")
        state = {
            "invocation": _public(row),
            "binding": binding.model_dump(mode="json"),
            "lease": {name: lease[name] for name in ("task_id", "worker", "fence", "state")},
            "remote_calls": [value.model_dump(mode="json") for value in calls],
            "observations": observed,
        }
        state["state_digest"] = fingerprint(state)
        return state, self.store._revisions(conn, support)

    def active(self, caller: str, invocation_id: str) -> bool:
        with self.store.engine.connect() as conn:
            return bool(
                conn.execute(
                    select(invocation_resolutions.c.closed).where(
                        (invocation_resolutions.c.owner == self.store.owner)
                        & (invocation_resolutions.c.caller == caller)
                        & (invocation_resolutions.c.invocation_id == invocation_id)
                    )
                ).scalar_one_or_none()
            )

    async def review(
        self,
        actor: str,
        invocation_id: str,
        command_id: str,
        checker: str,
        observations: tuple[ReceiptRef, ...],
        *,
        original_caller: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> Event:
        # Failed explicit owner reviews also incur inspection/query overhead.
        # Retain it as an UNKNOWN failure event, never as a closure receipt.
        if actor != self.store.owner or self.identity.name != actor:
            raise ValueError("resolution is owner-only")
        TypeAdapter(Identifier).validate_python(invocation_id)
        TypeAdapter(Identifier).validate_python(command_id)
        binding = self.registry.inspect(checker)
        started = time.perf_counter()
        try:
            return await self._review(
                actor,
                invocation_id,
                command_id,
                checker,
                observations,
                original_caller=original_caller,
                arguments=arguments,
            )
        except BaseException:
            failed = Event(
                id="resolve-failed-" + uid(),
                issuer=actor,
                subject=binding.subject,
                action="failure",
                task_id=invocation_id,
                attempt_id=command_id,
                correlation_id=fingerprint([actor, invocation_id, command_id]),
                outcome=Verdict.UNKNOWN,
                costs=(
                    Cost(
                        category="observation",
                        status="measured",
                        unit="wall_seconds",
                        quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                    ),
                ),
            )
            await run_blocking(self.store.put, self.identity.sign(failed))
            raise

    async def _review(
        self,
        actor: str,
        invocation_id: str,
        command_id: str,
        checker: str,
        observations: tuple[ReceiptRef, ...],
        *,
        original_caller: str | None = None,
        arguments: dict[str, Any] | None = None,
    ) -> Event:
        if actor != self.store.owner or self.identity.name != actor:
            raise ValueError("resolution is owner-only")
        caller = RemoteCalls(self.store).lookup_caller(actor, original_caller)
        TypeAdapter(Identifier).validate_python(invocation_id)
        TypeAdapter(Identifier).validate_python(command_id)
        if len(observations) > 64:
            raise ValueError("resolution observation bound exceeded")
        pinned = self._queries[checker]
        if self.registry.inspect(checker).digest != pinned:
            raise ValueError("resolution query changed")
        command_digest = fingerprint(
            [
                caller,
                invocation_id,
                pinned,
                [r.model_dump(mode="json") for r in observations],
                arguments or {},
            ]
        )
        event_id = "resolve-" + fingerprint([actor, command_id])
        with self.store.engine.connect() as conn:
            previous = conn.execute(
                select(records.c.envelope).where(
                    (records.c.kind == "event")
                    & (records.c.issuer == actor)
                    & (records.c.record_id == event_id)
                )
            ).scalar_one_or_none()
            if previous is not None:
                old = verify(previous, self.store.principals)
                if (
                    not isinstance(old, Event)
                    or old.resolution is None
                    or old.resolution.command_digest != command_digest
                ):
                    raise Conflict("resolution command changed its review contract")
                return old
            state, revisions = self._snapshot(conn, caller, invocation_id, checker, observations)
        started = time.perf_counter()
        valid_until = now() + timedelta(seconds=self.maximum_observation_age)
        context = ExecutionContext(
            caller=actor,
            purpose="verification",
            environment=self.config.execution_environment,
            permissions=frozenset(self.config.policy.permissions),
        )
        for observation in state["observations"].values():
            r = observation["reconciliation"]
            query = self.reconciliations.installed_query(r["reconciler_binding_digest"])
            call = next(
                value for value in state["remote_calls"] if value["call_key"] == r["call_key"]
            )
            prepared = self.registry.prepare(
                query,
                r["reconciler_binding_digest"],
                {"call": call, "provider_report": {}},
                context,
            )
            decision = await self.registry.overlay.qualify(
                prepared.request, verification_granted=True
            )
            if decision.outcome != Outcome.ACCEPT:
                raise ValueError("resolution remote query support is withdrawn or unavailable")
            if any(revisions.get(key, value) != value for key, value in decision.revisions.items()):
                raise Conflict("resolution support changed during review")
            revisions.update(decision.revisions)
            valid_until = min(valid_until, decision.valid_until)
        review_state = {
            "state_digest": state["state_digest"],
            "invocation": state["invocation"],
            "binding_digest": state["invocation"]["binding_digest"],
            "lease": state["lease"],
            "remote_call_keys": [value["call_key"] for value in state["remote_calls"]],
            "observation_refs": [value.model_dump(mode="json") for value in observations],
        }
        query_arguments = {"state": review_state, "arguments": arguments or {}}
        prepared = self.registry.prepare(checker, pinned, query_arguments, context)
        decision = await self.registry.overlay.qualify(prepared.request, verification_granted=True)
        if decision.outcome != Outcome.ACCEPT:
            raise ValueError("whole-invocation query support is withdrawn or unavailable")
        if any(revisions.get(key, value) != value for key, value in decision.revisions.items()):
            raise Conflict("resolution support changed during review")
        revisions.update(decision.revisions)
        valid_until = min(valid_until, decision.valid_until)
        # Read-only query uses the installed verification grant without a normal
        # Executor claim. It remains bounded and records observation costs.
        import asyncio

        async with asyncio.timeout(min(self.config.max_seconds, 300)):
            result = ResolutionObservation.model_validate(
                await self.registry.execute(
                    checker,
                    pinned,
                    query_arguments,
                    context,
                    call_id=command_id,
                    call_scope="resolution/" + invocation_id,
                )
            )
        if (
            result.caller != caller
            or result.invocation_id != invocation_id
            or result.state_digest != state["state_digest"]
            or result.effect == "unknown"
            or not result.all_effects_checked
            or not result.all_results_checked
            or not result.worker_quiescent
        ):
            raise ValueError(
                "whole-invocation effects/results or physical quiescence remain unknown"
            )
        receipt = ResolutionReceipt(
            caller=caller,
            invocation_id=invocation_id,
            original_receipt=ReceiptRef(issuer=actor, id=state["invocation"]["receipt_id"]),
            original_fingerprint=state["invocation"]["fingerprint"],
            state_digest=state["state_digest"],
            remote_calls_digest=fingerprint(state["remote_calls"]),
            observations=observations,
            review_binding_digest=pinned,
            review_observation_digest=result.observation_digest,
            effect=result.effect,
            all_results_checked=True,
            worker_quiescent=True,
            reason=result.reason,
            command_digest=command_digest,
        )
        event = Event(
            schema_version="5",
            id=event_id,
            issuer=actor,
            subject=self.registry.inspect(checker).subject,
            action="recommendation",
            task_id=invocation_id,
            attempt_id=command_id,
            correlation_id=state["state_digest"],
            causation_id=receipt.original_receipt.id,
            resolution=receipt,
            costs=(
                Cost(
                    category="observation",
                    status="measured",
                    quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                    unit="wall_seconds",
                ),
            ),
        )
        await run_blocking(
            self._commit,
            caller,
            invocation_id,
            checker,
            observations,
            state,
            revisions,
            valid_until,
            event,
        )
        return event

    def _commit(
        self,
        caller: str,
        invocation_id: str,
        checker: str,
        observations: tuple[ReceiptRef, ...],
        state: dict[str, Any],
        revisions: dict[str, int],
        valid_until: datetime,
        event: Event,
    ) -> None:
        with self.store.engine.begin() as conn:
            # Same budget -> owner capacity -> invocation -> lease -> feed order
            # as claim. No allowance or original invocation is changed here.
            unit: str = conn.execute(
                select(leases.c.unit).where(leases.c.task_id == state["lease"]["task_id"])
            ).scalar_one()
            conn.execute(
                select(budgets.c.unit).where(budgets.c.unit == unit).with_for_update()
            ).one()
            conn.execute(
                select(
                    func.pg_advisory_xact_lock(
                        int(fingerprint(["invocation-capacity", self.store.owner])[:15], 16)
                    )
                )
            )
            InvocationStore._locked(conn, caller, invocation_id)
            # Feed lock also excludes simultaneous evidence withdrawal/restore.
            conn.execute(
                select(feed_state.c.sequence).where(feed_state.c.id == 1).with_for_update()
            ).one()
            current, current_revisions = self._snapshot(
                conn, caller, invocation_id, checker, observations
            )
            current_revisions.update(self.store._revisions(conn, set(revisions)))
            if (
                current != state
                or current_revisions != revisions
                or conn.execute(select(func.clock_timestamp())).scalar_one() >= valid_until
            ):
                raise Conflict("resolution original state or support changed during review")
            closed = conn.execute(
                select(invocation_resolutions.c.closed).where(
                    (invocation_resolutions.c.owner == self.store.owner)
                    & (invocation_resolutions.c.caller == caller)
                    & (invocation_resolutions.c.invocation_id == invocation_id)
                )
            ).scalar_one_or_none()
            if closed:
                raise Conflict("invocation already resolved; use its original resolution receipt")
            self.store._insert(conn, event, self.identity.sign(event))
            values = dict(
                caller=caller,
                invocation_id=invocation_id,
                owner=self.store.owner,
                invocation_context=fingerprint([self.store.owner, caller, invocation_id]),
                receipt_id=event.id,
                state_digest=state["state_digest"],
                revisions=revisions,
                closed=True,
                closed_at=now(),
            )
            conn.execute(
                insert(invocation_resolutions)
                .values(**values)
                .on_conflict_do_update(index_elements=["caller", "invocation_id"], set_=values)
            )
