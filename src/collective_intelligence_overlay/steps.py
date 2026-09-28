"""An owner-local choice connected to the existing persistent Executor.

The only new durable fact is the immutable choice. Execution, cancellation,
allowance, expiry and uncertain results retain their existing authoritative rows.
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import JSON, Column, DateTime, String, Table, select
from sqlalchemy.dialects.postgresql import insert

from .bindings import ExecutionContext, fingerprint
from .invocations import Executor
from .models import Cost, Event, Identifier, Opportunity, Proposal, RecordRef, now, uid
from .opportunities import Opportunities
from .storage import budgets, metadata

selections = Table(
    "work_selections",
    metadata,
    Column("owner", String(160), primary_key=True),
    Column("opportunity_id", String(160), primary_key=True),
    Column("body", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False),
)


class Selection(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    owner: Identifier
    opportunity: RecordRef
    proposal: RecordRef
    invocation_id: Identifier
    reasons: tuple[Identifier, ...]
    skipped: tuple[Identifier, ...] = Field(max_length=128)
    estimates: tuple[Cost, ...] = Field(max_length=8)


class StepResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reason: str
    selection: Selection | None = None
    invocation: dict[str, Any] | None = None


class RunResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    reason: str
    rounds: int
    steps: tuple[StepResult, ...]
    discovered: int
    deduplicated: int


class Steps:
    """Host API for one bounded choice. This is not a workflow or retry engine."""

    def __init__(
        self, opportunities: Opportunities, executor: Executor, context: ExecutionContext
    ) -> None:
        if executor.registry is not opportunities.registry:
            raise ValueError("step and executor must share the same registered host")
        if context.caller != executor.identity.name or context.purpose != "reuse":
            raise ValueError("steps require an ordinary-use owner context")
        self.opportunities, self.executor = opportunities, executor
        self.context = context.model_copy(deep=True)
        self.store = executor.registry.overlay.store

    async def run(
        self,
        proposals: Callable[[Opportunity], Awaitable[tuple[tuple[str, dict[str, Any]], ...]]],
        *,
        max_steps: int = 16,
        max_candidates: int = 8,
        seconds: int = 120,
    ) -> RunResult:
        """Finite host loop over discovery and the same durable single-step API.

        The callback can collect authenticated A2A replies or run an installed
        proposer. It receives observations, not mutable goals or execution grants.
        Completed/UNKNOWN/running invocations are never assigned fresh attempts.
        """
        if not 1 <= max_steps <= 64 or not 1 <= max_candidates <= 32 or not 1 <= seconds <= 300:
            raise ValueError("invalid finite loop bounds")
        results: list[StepResult] = []
        seen: set[str] = set()
        start = rounds = discovered = deduplicated = 0
        reason = "step_limit"
        cycle_observed = False
        try:
            async with asyncio.timeout(seconds):
                for _ in range(max_steps):
                    rounds += 1
                    page = await self.opportunities.discover(
                        max_candidates=max_candidates, start=start
                    )
                    discovered += page.discovered
                    deduplicated += page.deduplicated
                    start = page.next_goal or 0
                    pending = [item for item in page.opportunities if item.id not in seen]
                    if not pending:
                        if page.next_goal is None:
                            if cycle_observed:
                                cycle_observed = False
                                continue
                            reason = "no_progress"
                            break
                        continue
                    cycle_observed = page.next_goal is not None
                    opportunity = pending[0]
                    seen.add(opportunity.id)
                    choice = await asyncio.to_thread(self._choice, opportunity.id)
                    old = (
                        None
                        if choice is None
                        else await asyncio.to_thread(
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
                    result = await self.step(opportunity.id, replies)
                    results.append(result)
                    if result.reason == "insufficient_allowance":
                        reason = "insufficient_allowance"
                        break
        except TimeoutError:
            reason = "deadline"
        return RunResult(
            reason=reason,
            rounds=rounds,
            steps=tuple(results),
            discovered=discovered,
            deduplicated=deduplicated,
        )

    def _choice(self, opportunity_id: str, proposed: Selection | None = None) -> Selection | None:
        with self.store.engine.begin() as conn:
            if proposed is not None:
                conn.execute(
                    insert(selections)
                    .values(
                        owner=self.store.owner,
                        opportunity_id=opportunity_id,
                        body=proposed.model_dump(mode="json"),
                        created_at=now(),
                    )
                    .on_conflict_do_nothing()
                )
            body = conn.execute(
                select(selections.c.body).where(
                    (selections.c.owner == self.store.owner)
                    & (selections.c.opportunity_id == opportunity_id)
                )
            ).scalar_one_or_none()
        return Selection.model_validate(body) if body is not None else None

    def _available(self) -> bool:
        with self.store.engine.connect() as conn:
            remaining = conn.execute(
                select(budgets.c.remaining).where(budgets.c.unit == self.executor.allowance.unit)
            ).scalar_one_or_none()
        return remaining is not None and remaining >= self.executor.allowance.quantity

    async def step(
        self, opportunity_id: str, envelopes: tuple[tuple[str, dict[str, Any]], ...] = ()
    ) -> StepResult:
        """Select from a complete bounded reply batch, independent of reply order.

        Tuple callers come from the authenticated transport, never payload metadata.
        Replay consults the existing invocation before revalidating stale proposals.
        """
        if len(envelopes) > 128:
            raise ValueError("proposal batch exceeds bound")
        choice = await asyncio.to_thread(self._choice, opportunity_id)
        if choice is not None:
            old = await asyncio.to_thread(
                self.executor.store.get, self.context.caller, choice.invocation_id
            )
            if old is not None:
                return StepResult(reason="existing_invocation", selection=choice, invocation=old)
        reference = await asyncio.to_thread(
            self.store.reference, "opportunity", self.store.owner, opportunity_id
        )
        opportunity = await asyncio.to_thread(self.store.resolve_reference, reference)
        if not isinstance(opportunity, Opportunity):
            raise ValueError("expected a local opportunity")
        started = time.perf_counter()
        try:
            result = await self._step(opportunity, reference, choice, envelopes)
        finally:
            # Measured inspection survives rejection. No receipt or refund is invented.
            event = Event(
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
            await asyncio.shield(
                asyncio.to_thread(self.store.put, self.executor.identity.sign(event))
            )
        if result.reason == "selected" and result.selection is not None:
            return await self._execute(result.selection)
        return result

    async def _step(
        self,
        opportunity: Opportunity,
        reference: RecordRef,
        choice: Selection | None,
        envelopes: tuple[tuple[str, dict[str, Any]], ...],
    ) -> StepResult:
        goal = self.opportunities.goal(opportunity.goal_id)
        if opportunity.expires_at <= now() or opportunity.goal_digest != goal.digest:
            return StepResult(reason="expired_or_changed_goal", selection=choice)
        if choice is None:
            candidates: dict[tuple[str, str], Proposal] = {}
            for caller, envelope in envelopes:
                proposal = await asyncio.to_thread(
                    self.opportunities.validate_proposal, envelope, caller, self.context
                )
                if proposal.opportunity != reference:
                    raise ValueError("proposal belongs to a different observation")
                await asyncio.to_thread(self.store.put, envelope)
                candidates[proposal.issuer, proposal.id] = proposal
            if not candidates:
                return StepResult(reason="no_valid_alternatives")
            if not await asyncio.to_thread(self._available):
                return StepResult(reason="insufficient_allowance")
            order = {ref.digest: i for i, ref in enumerate(goal.builders)}
            ranked = sorted(
                candidates.values(), key=lambda p: (order[p.builder.digest], p.issuer, p.id)
            )
            selected = ranked[0]
            proposal_ref = await asyncio.to_thread(
                self.store.reference, "proposal", selected.issuer, selected.id
            )
            choice = await asyncio.to_thread(
                self._choice,
                opportunity.id,
                Selection(
                    owner=self.store.owner,
                    opportunity=reference,
                    proposal=proposal_ref,
                    invocation_id="work-" + fingerprint([self.store.owner, opportunity.id]),
                    reasons=("operator_builder_order", "stable_alternative_order"),
                    skipped=tuple(p.id for p in ranked[1:]),
                    estimates=selected.estimates,
                ),
            )
            assert choice is not None
        return StepResult(reason="selected", selection=choice)

    async def _execute(self, choice: Selection) -> StepResult:
        selected_record = await asyncio.to_thread(self.store.resolve_reference, choice.proposal)
        if not isinstance(selected_record, Proposal):
            raise ValueError("stored selection is not a proposal")
        old = await asyncio.to_thread(
            self.executor.store.get, self.context.caller, choice.invocation_id
        )
        if old is not None:
            return StepResult(reason="existing_invocation", selection=choice, invocation=old)
        await asyncio.to_thread(
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
        result = await self.executor.invoke(
            choice.invocation_id,
            selected_record.builder.id,
            selected_record.builder.digest,
            selected_record.arguments,
            self.context,
        )
        return StepResult(reason="invocation_observed", selection=choice, invocation=result)
