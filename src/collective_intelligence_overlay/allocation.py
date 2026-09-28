"""Small owner rules over bounded observations; not a global optimizer."""

import asyncio
import time
from collections import Counter
from decimal import Decimal
from typing import Literal

from jsonschema import ValidationError as SchemaError  # type: ignore[import-untyped]
from pydantic import AwareDatetime, BaseModel, ConfigDict, Field

from .bindings import ExecutionContext, fingerprint
from .models import (
    BindingRef,
    Cost,
    Digest,
    Event,
    Identifier,
    Opportunity,
    Outcome,
    RecordRef,
    WorkKind,
    now,
    uid,
)
from .opportunities import Opportunities


class AllocationPolicy(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    mode: Literal["static", "adaptive"] = "adaptive"
    minimum_samples: int = Field(default=2, ge=1, le=32)
    verification_threshold: int = Field(default=2, ge=1, le=32)
    connection_threshold: int = Field(default=2, ge=1, le=32)
    unverified_limit: int = Field(default=8, ge=1, le=32)
    reserve_operations: int = Field(default=1, ge=0, le=16)
    cooldown_seconds: int = Field(default=10, ge=0, le=3600)


class AllocationObservation(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    receiver: Identifier
    rule_digest: Digest
    policy_digest: Digest
    started_at: AwareDatetime
    finished_at: AwareDatetime
    observations: tuple[RecordRef, ...] = Field(max_length=32)
    sample_count: int
    counts: dict[WorkKind, int]
    qualified_checkers: tuple[BindingRef, ...] = Field(max_length=32)
    checker_decisions: tuple[RecordRef, ...] = Field(max_length=32)
    reasons: tuple[Identifier, ...]
    ordered: tuple[Identifier, ...] = Field(max_length=32)
    deferred: dict[Identifier, Identifier] = Field(max_length=32)
    reserve_operations: int = Field(default=0, ge=0, le=16)
    preferred_kind: WorkKind | None = None
    priority_since: AwareDatetime | None = None


async def allocate(
    host: Opportunities,
    context: ExecutionContext,
    observations: tuple[Opportunity, ...],
    policy: AllocationPolicy,
    previous: AllocationObservation | None = None,
) -> AllocationObservation:
    if not 1 <= len(observations) <= 32:
        raise ValueError("allocation requires a bounded observation page")
    started = time.perf_counter()
    try:
        return await _allocate(host, context, observations, policy, previous)
    finally:
        event = Event(
            issuer=host.identity.name,
            subject=observations[0].subject,
            action="recommendation",
            task_id=observations[0].id,
            attempt_id=uid(),
            correlation_id=observations[0].id,
            costs=(
                Cost(
                    category="overhead",
                    status="measured",
                    unit="wall_seconds",
                    quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                ),
                Cost(category="overhead", status="unavailable", unit="USD", quantity=None),
            ),
        )
        await asyncio.shield(
            asyncio.to_thread(host.registry.overlay.store.put, host.identity.sign(event))
        )


async def _allocate(
    host: Opportunities,
    context: ExecutionContext,
    observations: tuple[Opportunity, ...],
    policy: AllocationPolicy,
    previous: AllocationObservation | None,
) -> AllocationObservation:
    if not 1 <= len(observations) <= 32 or len({o.id for o in observations}) != len(observations):
        raise ValueError("allocation requires a bounded distinct observation page")
    started = now()
    counts = Counter(o.work_kind for o in observations)
    reasons = ["registered_goal_order"]
    refs, check_decisions, checkers = [], [], []
    deferred: dict[str, str] = {}
    eligible = list(observations)
    preferred: WorkKind | None = None
    priority_since = None
    store = host.registry.overlay.store
    for observation in observations:
        ref = await asyncio.to_thread(store.reference, "opportunity", store.owner, observation.id)
        actual = await asyncio.to_thread(store.resolve_reference, ref)
        if actual != observation:
            raise ValueError("allocation observation differs from its signed record")
        refs.append(ref)
    if policy.mode == "adaptive":
        for observation in observations:
            if observation.work_kind != "verification":
                continue
            goal = host.goal(observation.goal_id)
            deferred[observation.id] = "checker_unavailable"
            try:
                binding = host.registry.inspect(goal.checker.id)
                if binding.issuer != goal.checker.issuer:
                    continue
                prepared = host.registry.prepare(
                    binding.id, goal.checker.digest, goal.checker_arguments, context
                )
            except (ValueError, SchemaError):
                continue
            decision = await host.registry.overlay.qualify(prepared.request)
            check_decisions.append(
                await asyncio.to_thread(store.reference, "decision", store.owner, decision.id)
            )
            if decision.outcome == Outcome.ACCEPT:
                deferred.pop(observation.id, None)
                if goal.checker not in checkers:
                    checkers.append(goal.checker)
        if counts["verification"] >= policy.unverified_limit:
            deferred.update(
                {o.id: "unverified_queue_limit" for o in observations if o.work_kind == "formation"}
            )
            reasons.append("unverified_queue_limit")
        if len(observations) < policy.minimum_samples:
            reasons.append("insufficient_samples_use_static_order")
        else:
            if counts["repair"]:
                preferred = "repair"
                reasons.append("known_failure_requires_repair")
            elif counts["verification"] >= policy.verification_threshold and checkers:
                preferred = "verification"
                reasons.append("verification_backlog_with_qualified_checker")
            elif counts["connection"] >= policy.connection_threshold:
                preferred = "connection"
                reasons.append("connection_backlog")
            elif counts["observation"]:
                preferred = "observation"
                reasons.append("insufficient_observations")
        eligible = [o for o in eligible if o.id not in deferred]
        if preferred is not None:
            priority_since = started
        if (
            previous is not None
            and previous.receiver == store.owner
            and previous.rule_digest == fingerprint(policy.model_dump(mode="json"))
            and previous.policy_digest == host.registry.overlay.policy.digest
            and previous.preferred_kind is not None
            and previous.priority_since is not None
        ):
            if previous.preferred_kind == preferred:
                priority_since = previous.priority_since
            elif (
                preferred != "repair"
                and preferred is not None
                and 0
                <= (started - previous.priority_since).total_seconds()
                < policy.cooldown_seconds
                and any(o.work_kind == previous.preferred_kind for o in eligible)
            ):
                preferred, priority_since = previous.preferred_kind, previous.priority_since
                reasons.append("retain_qualified_priority_during_cooldown")
        if preferred is not None:
            eligible.sort(key=lambda o: o.work_kind != preferred)
    return AllocationObservation(
        receiver=store.owner,
        rule_digest=fingerprint(policy.model_dump(mode="json")),
        policy_digest=host.registry.overlay.policy.digest,
        started_at=started,
        finished_at=now(),
        observations=tuple(refs),
        sample_count=len(observations),
        counts=dict(counts),
        qualified_checkers=tuple(checkers),
        checker_decisions=tuple(check_decisions),
        reasons=tuple(reasons),
        ordered=tuple(o.id for o in eligible),
        deferred=deferred,
        preferred_kind=preferred,
        priority_since=priority_since,
        reserve_operations=policy.reserve_operations
        if checkers and policy.mode == "adaptive"
        else 0,
    )
