"""An owner-local choice connected to the existing persistent Executor.

The only new durable fact is the immutable choice. Execution, cancellation,
allowance, expiry and uncertain results retain their existing authoritative rows.
"""

from __future__ import annotations

import asyncio
import base64
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Column, DateTime, String, Table, and_, func, or_, select
from sqlalchemy.dialects.postgresql import insert

from .allocation import AllocationObservation, AllocationPolicy, allocate
from .bindings import ExecutionContext, fingerprint
from .blocking import run_blocking
from .invocations import Executor, invocation_request, invocations
from .models import (
    Cost,
    Event,
    Identifier,
    Opportunity,
    Proposal,
    RecordRef,
    WorkObservation,
    now,
    uid,
)
from .opportunities import (
    Opportunities,
    ProposalRejected,
    ProposalRejection,
    RejectionCategory,
    record_rejections,
    summarize_rejections,
)
from .proposal_exchange import CollectedProposals, ProposalBatch
from .reobservation import instances
from .security import digest, verify
from .storage import Conflict, budgets, feed_state, leases, metadata
from .storage import records as record_table

selections = Table(
    "work_selections",
    metadata,
    Column("owner", String(160), primary_key=True),
    Column("opportunity_id", String(160), primary_key=True),
    Column("body", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
    Column("cause_id", String(64)),
    Column("invocation_id", String(160)),
)


class AttemptBlocked(ValueError):
    """Expected owner-local refusal to create an execution attempt."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(reason)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner: Identifier
    opportunity: RecordRef
    proposal: RecordRef
    invocation_id: Identifier
    reasons: tuple[Identifier, ...]
    skipped: tuple[Identifier, ...] = Field(max_length=128)
    estimates: tuple[Cost, ...] = Field(max_length=8)
    allocation: AllocationObservation | None = None


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reason: str
    selection: Selection | None = None
    invocation: dict[str, Any] | None = None
    rejections: tuple[ProposalRejection, ...] = Field(default=(), max_length=128)
    unavailable: tuple[str, ...] = Field(default=(), max_length=16)


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reason: str
    rounds: int
    steps: tuple[StepResult, ...]
    discovered: int
    deduplicated: int
    allocations: tuple[AllocationObservation, ...] = ()


class Steps:
    """Host API for one bounded choice. This is not a workflow or retry engine."""

    def __init__(
        self,
        opportunities: Opportunities,
        executor: Executor,
        context: ExecutionContext,
        *,
        max_concurrent: int = 4,
    ) -> None:
        if executor.registry is not opportunities.registry:
            raise ValueError("step and executor must share the same registered host")
        if context.caller != executor.identity.name or context.purpose != "reuse":
            raise ValueError("steps require an ordinary-use owner context")
        if not 1 <= max_concurrent <= 32:
            raise ValueError("invalid owner concurrency bound")
        executor.allowance = executor.allowance.model_copy(
            update={
                "max_concurrent": min(max_concurrent, executor.allowance.max_concurrent or 32),
            }
        )
        self.opportunities, self.executor = opportunities, executor
        self.context = context.model_copy(deep=True)
        self.store = executor.registry.overlay.store

    async def run(
        self,
        proposals: Callable[[Opportunity], Awaitable[ProposalBatch]],
        *,
        max_steps: int = 16,
        max_candidates: int = 8,
        seconds: int = 120,
        allocation_policy: AllocationPolicy | None = None,
    ) -> RunResult:
        """Finite host loop over discovery and the same durable single-step API.

        The callback can collect authenticated A2A replies or run an installed
        proposer. It receives observations, not mutable goals or execution grants.
        Completed/UNKNOWN/running invocations are never assigned fresh attempts.
        """
        if not 1 <= max_steps <= 64 or not 1 <= max_candidates <= 32 or not 1 <= seconds <= 300:
            raise ValueError("invalid finite loop bounds")
        results: list[StepResult] = []
        allocations: list[AllocationObservation] = []
        seen: set[str] = set()
        rounds = discovered = deduplicated = 0
        reason = "step_limit"
        deadline = asyncio.timeout(seconds)
        try:
            async with deadline:
                for _ in range(max_steps):
                    rounds += 1
                    start = 0
                    observed: list[Opportunity] = []
                    while True:
                        page = await self.opportunities.discover(
                            max_candidates=max_candidates, start=start
                        )
                        discovered += page.discovered
                        deduplicated += page.deduplicated
                        observed.extend(page.opportunities)
                        if page.next_goal is None:
                            break
                        start = page.next_goal
                    allocation = None
                    if observed:
                        allocation = await allocate(
                            self.opportunities,
                            self.context,
                            tuple(observed),
                            allocation_policy or AllocationPolicy(),
                            await run_blocking(self.last_allocation),
                        )
                        allocations.append(allocation)
                    by_id = {item.id: item for item in observed}
                    pending = (
                        [by_id[key] for key in allocation.ordered if key not in seen]
                        if allocation
                        else []
                    )
                    if not pending:
                        reason = "no_progress"
                        break
                    opportunity = pending[0]
                    seen.add(opportunity.id)
                    choice = await run_blocking(self._choice, opportunity.id)
                    old = (
                        None
                        if choice is None
                        else await run_blocking(
                            self.executor.store.get, self.context.caller, choice.invocation_id
                        )
                    )
                    if old is not None:
                        results.append(
                            StepResult(
                                reason="existing_invocation", selection=choice, invocation=old
                            )
                        )
                        continue
                    replies = await proposals(opportunity.model_copy(deep=True))
                    result = await self.step(opportunity.id, replies, allocation=allocation)
                    results.append(result)
                    if result.reason == "insufficient_allowance":
                        reason = "insufficient_allowance"
                        break
        except TimeoutError:
            if not deadline.expired():
                raise
            reason = "deadline"
        return RunResult(
            reason=reason,
            rounds=rounds,
            steps=tuple(results),
            discovered=discovered,
            deduplicated=deduplicated,
            allocations=tuple(allocations),
        )

    def _choice(self, opportunity_id: str, proposed: Selection | None = None) -> Selection | None:
        proposal = None if proposed is None else self.store.resolve_reference(proposed.proposal)
        observation = (
            None if proposed is None else self.store.resolve_reference(proposed.opportunity)
        )
        if proposed is not None and not isinstance(proposal, Proposal):
            raise ValueError("choice requires a stored proposal")
        with self.store.engine.begin() as conn:
            if proposed is not None:
                # The existing owner feed lock serializes choice/instance publication.
                # Execution transitions retain budget -> invocation -> lease locking.
                conn.execute(
                    select(feed_state.c.sequence).where(feed_state.c.id == 1).with_for_update()
                ).one()
            body = conn.execute(
                select(selections.c.body).where(
                    (selections.c.owner == self.store.owner)
                    & (selections.c.opportunity_id == opportunity_id)
                )
            ).scalar_one_or_none()
            if body is not None or proposed is None:
                return Selection.model_validate(body) if body is not None else None
            if proposed is not None:
                if (
                    not isinstance(observation, Opportunity)
                    or observation.expires_at <= now()
                    or observation.goal_digest
                    != self.opportunities.goal(observation.goal_id).digest
                ):
                    raise AttemptBlocked("expired_or_changed_goal")
                state = (
                    conn.execute(
                        select(instances).where(
                            (instances.c.owner == self.store.owner)
                            & (instances.c.opportunity_id == opportunity_id)
                        )
                    )
                    .mappings()
                    .first()
                )
                if state is None or state["cause_id"] is None:
                    raise AttemptBlocked("reobservation_required")
                latest_id: str = conn.execute(
                    select(instances.c.opportunity_id)
                    .where(
                        (instances.c.owner == self.store.owner)
                        & (instances.c.cause_id == state["cause_id"])
                    )
                    .order_by(instances.c.issue_sequence.desc())
                    .limit(1)
                ).scalar_one()
                if latest_id != opportunity_id:
                    raise AttemptBlocked("reobservation_required")
                # NULL legacy cause cannot be silently attributed to unrelated work.
                prior = and_(
                    selections.c.owner == self.store.owner,
                    selections.c.opportunity_id != opportunity_id,
                    or_(
                        selections.c.cause_id == state["cause_id"], selections.c.cause_id.is_(None)
                    ),
                )
                history = selections.outerjoin(
                    invocations,
                    and_(
                        invocations.c.owner == selections.c.owner,
                        invocations.c.caller == self.context.caller,
                        invocations.c.id == selections.c.invocation_id,
                    ),
                ).outerjoin(leases, leases.c.task_id == invocations.c.lease_id)
                released = and_(
                    invocations.c.state.in_(("cancelled", "rejected", "unknown")),
                    or_(
                        invocations.c.phase == "reserved",
                        and_(
                            invocations.c.phase == "dispatched",
                            invocations.c.state == "cancelled",
                            invocations.c.reason == "pre_actuation_admission_denied",
                            invocations.c.release_reason == "pre_actuation_admission_denied",
                            invocations.c.receipt_id.is_not(None),
                        ),
                    ),
                    invocations.c.reservation_state == "released",
                    leases.c.state == "cancelled",
                    leases.c.worker == invocations.c.worker,
                    leases.c.fence > invocations.c.fence,
                    leases.c.actual.is_(None),
                )
                safe = func.coalesce(or_(invocations.c.state == "completed", released), False)
                if (
                    conn.execute(
                        select(selections.c.opportunity_id)
                        .select_from(history)
                        .where(prior & ~safe)
                        .limit(1)
                    ).first()
                    is not None
                ):
                    raise AttemptBlocked("reconciliation_required")
                assert isinstance(proposal, Proposal)
                content = fingerprint(
                    invocation_request(
                        self.store.owner,
                        proposal.builder.id,
                        proposal.builder.digest,
                        proposal.arguments,
                        self.context,
                    )
                )
                previous_record = record_table.alias("previous_opportunity")
                completed = (
                    conn.execute(
                        select(selections.c.body, previous_record.c.envelope)
                        .select_from(
                            history.outerjoin(
                                previous_record,
                                and_(
                                    previous_record.c.kind == "opportunity",
                                    previous_record.c.issuer == selections.c.owner,
                                    previous_record.c.record_id == selections.c.opportunity_id,
                                ),
                            )
                        )
                        .where(
                            prior
                            & (selections.c.cause_id == state["cause_id"])
                            & (invocations.c.state == "completed")
                            & (invocations.c.fingerprint == content)
                            & (
                                previous_record.c.body["observation_digest"].as_string()
                                == observation.observation_digest
                            )
                        )
                        .order_by(selections.c.created_at, selections.c.opportunity_id)
                        .limit(1)
                    )
                    .mappings()
                    .first()
                )
                if completed is not None:
                    saved = Selection.model_validate(completed["body"])
                    previous = verify(completed["envelope"], self.store.principals)
                    if (
                        not isinstance(previous, Opportunity)
                        or previous.observation_digest != observation.observation_digest
                        or digest(base64.b64decode(completed["envelope"]["payload"], validate=True))
                        != saved.opportunity.payload_digest
                    ):
                        raise ValueError("stored completed choice has inconsistent observation")
                    return saved
                if (
                    not state["new_attempt_requested"]
                    and conn.execute(
                        select(selections.c.opportunity_id).where(prior).limit(1)
                    ).first()
                    is not None
                ):
                    raise AttemptBlocked("new_attempt_required")
                conn.execute(
                    insert(selections)
                    .values(
                        owner=self.store.owner,
                        opportunity_id=opportunity_id,
                        body=proposed.model_dump(mode="json"),
                        created_at=now(),
                        cause_id=state["cause_id"],
                        invocation_id=proposed.invocation_id,
                    )
                    .on_conflict_do_nothing()
                )
        return proposed

    def last_allocation(self) -> AllocationObservation | None:
        """Read the latest persisted owner choice for bounded host-loop cooldown."""
        with self.store.engine.connect() as conn:
            body = conn.execute(
                select(selections.c.body)
                .where(selections.c.owner == self.store.owner)
                .order_by(selections.c.created_at.desc())
                .limit(1)
            ).scalar_one_or_none()
        if body is None:
            return None
        return Selection.model_validate(body).allocation

    def _available(self) -> bool:
        with self.store.engine.connect() as conn:
            remaining = conn.execute(
                select(budgets.c.remaining).where(budgets.c.unit == self.executor.allowance.unit)
            ).scalar_one_or_none()
        return remaining is not None and remaining >= (
            self.executor.allowance.quantity + self.executor.allowance.minimum_remaining
        )

    async def step(
        self,
        opportunity_id: str,
        envelopes: ProposalBatch = (),
        *,
        allocation: AllocationObservation | None = None,
    ) -> StepResult:
        """Select from a complete bounded reply batch, independent of reply order.

        Tuple callers come from the authenticated transport, never payload metadata.
        Replay consults the existing invocation before revalidating stale proposals.
        """
        collected = envelopes if isinstance(envelopes, CollectedProposals) else None
        replies = collected.replies if collected is not None else envelopes
        if not isinstance(replies, tuple):
            raise ValueError("expected a bounded proposal batch")
        if len(replies) > 128:
            raise ValueError("proposal batch exceeds bound")
        choice = await run_blocking(self._choice, opportunity_id)
        if choice is not None:
            old = await run_blocking(
                self.executor.store.get, self.context.caller, choice.invocation_id
            )
            if old is not None:
                return StepResult(reason="existing_invocation", selection=choice, invocation=old)
        reference = await run_blocking(
            self.store.reference, "opportunity", self.store.owner, opportunity_id
        )
        opportunity = await run_blocking(self.store.resolve_reference, reference)
        if not isinstance(opportunity, Opportunity):
            raise ValueError("expected a local opportunity")
        started = time.perf_counter()
        observation_result = "interrupted"
        try:
            result = await self._step(opportunity, reference, choice, replies, allocation)
            if collected is not None:
                combined = summarize_rejections(
                    [
                        (rejection.peer, rejection.category)
                        for rejection in (*collected.rejections, *result.rejections)
                        for _ in range(rejection.count)
                    ]
                )
                reason = result.reason
                if (
                    reason == "no_valid_alternatives"
                    and not combined
                    and collected.unavailable
                    and set(collected.unavailable)
                    == set(self.opportunities.goal(opportunity.goal_id).peers)
                ):
                    reason = "peers_unavailable"
                result = result.model_copy(
                    update={
                        "rejections": combined,
                        "unavailable": collected.unavailable,
                        "reason": reason,
                    }
                )
            observation_result = result.reason
        finally:
            # Measured inspection survives rejection. No receipt or refund is invented.
            event = Event(
                schema_version="3",
                work=WorkObservation(
                    receiver=self.store.owner,
                    scope=opportunity.scope,
                    policy_digest=self.opportunities.registry.overlay.policy.digest,
                    goal_id=opportunity.goal_id,
                    goal_digest=opportunity.goal_digest,
                    opportunity_id=opportunity.id,
                    work_kind=opportunity.work_kind,
                    stage="selection",
                    result=observation_result,
                    proposals_received=len(replies),
                ),
                issuer=self.store.owner,
                subject=opportunity.subject,
                action="recommendation",
                task_id=opportunity.id,
                attempt_id=uid(),
                correlation_id=opportunity.id,
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
            await asyncio.shield(run_blocking(self.store.put, self.executor.identity.sign(event)))
        if result.reason == "selected" and result.selection is not None:
            executed = await self._execute(result.selection)
            return executed.model_copy(
                update={"rejections": result.rejections, "unavailable": result.unavailable}
            )
        return result

    async def _step(
        self,
        opportunity: Opportunity,
        reference: RecordRef,
        choice: Selection | None,
        envelopes: tuple[tuple[str, dict[str, Any]], ...],
        allocation: AllocationObservation | None,
    ) -> StepResult:
        goal = self.opportunities.goal(opportunity.goal_id)
        if opportunity.expires_at <= now() or opportunity.goal_digest != goal.digest:
            return StepResult(reason="expired_or_changed_goal", selection=choice)
        if choice is None:
            candidates: dict[tuple[str, str], Proposal] = {}
            signed: dict[tuple[str, str], dict[str, Any]] = {}
            conflicted: set[tuple[str, str]] = set()
            rejected: list[tuple[str, RejectionCategory]] = []
            for caller, envelope in envelopes:
                try:
                    proposal = await run_blocking(
                        self.opportunities.validate_proposal, envelope, caller, self.context
                    )
                    if proposal.opportunity != reference:
                        raise ProposalRejected(
                            "reference", "proposal belongs to a different observation"
                        )
                except ProposalRejected as exc:
                    rejected.append((caller, exc.category))
                    continue
                key = (proposal.issuer, proposal.id)
                if key in conflicted:
                    rejected.append((caller, "conflict"))
                    continue
                if key in candidates and signed[key]["payload"] != envelope["payload"]:
                    # Both members of an ambiguous batch are excluded before any
                    # save, so arrival order cannot choose its favored content.
                    conflicted.add(key)
                    candidates.pop(key)
                    signed.pop(key)
                    rejected.extend(((caller, "conflict"), (caller, "conflict")))
                    continue
                candidates[key], signed[key] = proposal, envelope
            for key in tuple(candidates):
                try:
                    await run_blocking(self.store.put, signed[key])
                except Conflict:
                    # Store.put raises this only for an immutable record ID clash.
                    # SQL/migration/verification faults remain visible.
                    rejected.append((key[0], "conflict"))
                    candidates.pop(key)
            rejections = summarize_rejections(rejected)
            if rejections:
                await run_blocking(
                    record_rejections, self.store, self.executor.identity, opportunity, rejections
                )
            if not candidates:
                return StepResult(reason="no_valid_alternatives", rejections=rejections)
            if not await run_blocking(self._available):
                return StepResult(reason="insufficient_allowance", rejections=rejections)
            order = {ref.digest: i for i, ref in enumerate(goal.builders)}
            ranked = sorted(
                candidates.values(), key=lambda p: (order[p.builder.digest], p.issuer, p.id)
            )
            selected = ranked[0]
            proposal_ref = await run_blocking(
                self.store.reference, "proposal", selected.issuer, selected.id
            )
            proposed = Selection(
                owner=self.store.owner,
                opportunity=reference,
                proposal=proposal_ref,
                invocation_id="work-" + fingerprint([self.store.owner, opportunity.id]),
                reasons=("operator_builder_order", "stable_alternative_order"),
                skipped=tuple(p.id for p in ranked[1:]),
                estimates=selected.estimates,
                allocation=allocation,
            )
            try:
                choice = await run_blocking(self._choice, opportunity.id, proposed)
            except AttemptBlocked as exc:
                return StepResult(reason=exc.reason, rejections=rejections)
            assert choice is not None
            if choice.opportunity.id != opportunity.id:
                old = await run_blocking(
                    self.executor.store.get, self.context.caller, choice.invocation_id
                )
                return StepResult(
                    reason="existing_invocation",
                    selection=choice,
                    invocation=old,
                    rejections=rejections,
                )
            return StepResult(reason="selected", selection=choice, rejections=rejections)
        return StepResult(reason="selected", selection=choice)

    async def _execute(self, choice: Selection) -> StepResult:
        selected_record = await run_blocking(self.store.resolve_reference, choice.proposal)
        if not isinstance(selected_record, Proposal):
            raise ValueError("stored selection is not a proposal")
        old = await run_blocking(self.executor.store.get, self.context.caller, choice.invocation_id)
        if old is not None:
            return StepResult(reason="existing_invocation", selection=choice, invocation=old)
        await run_blocking(
            self.opportunities._validate_proposal,
            selected_record,
            selected_record.issuer,
            self.context,
        )
        # Check current grants even after a crash between choice and invocation.
        # Executor independently repeats checks at its dispatch boundary.
        self.executor.registry.prepare(
            selected_record.builder.id,
            selected_record.builder.digest,
            selected_record.arguments,
            self.context,
        )
        opportunity = await run_blocking(self.store.resolve_reference, choice.opportunity)
        reserve = self.executor.allowance.minimum_remaining
        if (
            isinstance(opportunity, Opportunity)
            and opportunity.work_kind == "formation"
            and choice.allocation
        ):
            reserve = max(
                reserve, self.executor.allowance.quantity * choice.allocation.reserve_operations
            )
        try:
            result = await self.executor.invoke(
                choice.invocation_id,
                selected_record.builder.id,
                selected_record.builder.digest,
                selected_record.arguments,
                self.context,
                minimum_remaining=reserve,
            )
        except Conflict:
            old = await run_blocking(
                self.executor.store.get, self.context.caller, choice.invocation_id
            )
            if old is None:
                return StepResult(reason="allowance_or_capacity_deferred", selection=choice)
            return StepResult(reason="existing_invocation", selection=choice, invocation=old)
        return StepResult(reason="invocation_observed", selection=choice, invocation=result)
