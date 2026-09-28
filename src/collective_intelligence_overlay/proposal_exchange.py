"""Explicitly configured proposal exchange over the existing authenticated A2A route."""

import asyncio
import json
import time
from collections.abc import Awaitable, Callable
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .config import Config
from .models import (
    BindingRef,
    Cost,
    Digest,
    Event,
    Identifier,
    Opportunity,
    Proposal,
    Scope,
    Subject,
    now,
    uid,
)
from .opportunities import Goal, ProposalDrafts, propose
from .security import Identity, verify
from .storage import Store

Proposer = Callable[[Opportunity], Awaitable[ProposalDrafts]]


class ProposalContract(BaseModel):
    """Operator-approved public proposal scope, with no private checker inputs."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    owner: Identifier
    id: Identifier
    goal_digest: Digest
    contract_digest: Digest
    subject: Subject
    scope: Scope
    checker: BindingRef
    builders: tuple[BindingRef, ...] = Field(min_length=1, max_length=32)
    peers: tuple[Identifier, ...] = Field(max_length=16)
    lifetime_seconds: int = Field(ge=1, le=86400)

    @classmethod
    def from_goal(cls, goal: Goal) -> "ProposalContract":
        return cls(
            owner=goal.request.receiver,
            id=goal.id,
            goal_digest=goal.digest,
            contract_digest=goal.contract_digest,
            subject=goal.request.subject,
            scope=goal.request.scope,
            checker=goal.checker,
            builders=goal.builders,
            peers=goal.peers,
            lifetime_seconds=goal.lifetime_seconds,
        ).model_copy(deep=True)


class CollectedProposals(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    replies: tuple[tuple[str, dict[str, Any]], ...]
    unavailable: tuple[str, ...]


async def collect(
    config: Config, store: Store, identity: Identity, goal: Goal, opportunity_id: str
) -> CollectedProposals:
    """Ask only the registered peers and retain each alternative, including dissent."""
    from .adapters.a2a import send

    if (
        config.owner != identity.name
        or store.owner != identity.name
        or goal.request.receiver != identity.name
    ):
        raise ValueError("proposal collection belongs to the local goal owner")
    configured = {peer.identity for peer in config.peers}
    if not set(goal.peers) <= configured:
        raise ValueError("goal includes a peer without a configured destination")
    reference = await asyncio.to_thread(
        store.reference, "opportunity", identity.name, opportunity_id
    )
    opportunity = await asyncio.to_thread(store.resolve_reference, reference)
    if not isinstance(opportunity, Opportunity) or opportunity.goal_digest != goal.digest:
        raise ValueError("opportunity does not match the registered goal")
    if not set(goal.peers) <= set(opportunity.receivers) or opportunity.expires_at <= now():
        raise ValueError("opportunity is not shared with these peers or has expired")
    envelope = await asyncio.to_thread(store.signed_record, reference)
    limit = asyncio.Semaphore(min(config.max_concurrency, 16))

    async def ask(peer: str) -> tuple[str, list[dict[str, Any]] | None]:
        async with limit:
            started = time.perf_counter()
            try:
                response = await send(
                    config,
                    identity,
                    peer,
                    {
                        "operation": "propose",
                        "envelope": envelope,
                    },
                )
                items = response.get("proposals")
                if not isinstance(items, list) or len(items) > 8:
                    raise ValueError("invalid bounded proposal reply")
                for item in items:
                    record = verify(item, store.principals)
                    if (
                        not isinstance(record, Proposal)
                        or record.issuer != peer
                        or record.opportunity != reference
                    ):
                        raise ValueError("reply origin or opportunity mismatch")
                return peer, items
            except Exception:
                # No retry and no partial promotion; unavailable is not disagreement
                # or a verification failure. Do not expose credential-bearing errors.
                return peer, None
            finally:
                event = Event(
                    issuer=identity.name,
                    subject=opportunity.subject,
                    action="proposal",
                    task_id=opportunity.id,
                    attempt_id=uid(),
                    correlation_id=opportunity.id,
                    costs=(
                        Cost(
                            category="transfer",
                            status="measured",
                            unit="wall_seconds",
                            quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                        ),
                        Cost(category="transfer", status="unavailable", unit="USD", quantity=None),
                    ),
                )
                await asyncio.shield(asyncio.to_thread(store.put, identity.sign(event)))

    async with asyncio.timeout(min(config.max_seconds, 60)):
        results = await asyncio.gather(*(ask(peer) for peer in goal.peers))
    return CollectedProposals(
        replies=tuple(
            (peer, item) for peer, items in results if items is not None for item in items
        ),
        unavailable=tuple(peer for peer, items in results if items is None),
    )


class ProposalExchange:
    """Foreign goals are operator-approved contracts, not delegated execution grants."""

    def __init__(
        self,
        store: Store,
        identity: Identity,
        goals: tuple[Goal | ProposalContract, ...],
        proposer: Proposer,
        *,
        seconds: int = 10,
        allow_target_updates: bool = False,
    ) -> None:
        if identity.name != store.owner or not 1 <= len(goals) <= 32 or not 1 <= seconds <= 30:
            raise ValueError("invalid proposal exchange owner or bounds")
        contracts = tuple(
            ProposalContract.from_goal(g) if isinstance(g, Goal) else g for g in goals
        )
        keys = [(g.owner, g.id) for g in contracts]
        if len(set(keys)) != len(keys):
            raise ValueError("duplicate proposal contract")
        for goal in contracts:
            if identity.name not in goal.peers or goal.owner not in store.principals:
                raise ValueError("proposal contract must name configured owners and this proposer")
        self.store, self.identity, self.proposer, self.seconds = store, identity, proposer, seconds
        self.allow_target_updates = allow_target_updates
        self._goals = {
            key: goal.model_copy(deep=True) for key, goal in zip(keys, contracts, strict=True)
        }

    async def respond(self, caller: str, envelope: dict[str, Any]) -> dict[str, Any]:
        opportunity = verify(envelope, self.store.principals)
        if not isinstance(opportunity, Opportunity) or opportunity.issuer != caller:
            raise ValueError("opportunity must be signed by the authenticated owner")
        goal = self._goals.get((caller, opportunity.goal_id))
        candidate_update = (
            goal is not None
            and self.allow_target_updates
            and opportunity.goal_contract_digest == goal.contract_digest
            and opportunity.subject.id == goal.subject.id
        )
        if goal is None or (
            (
                not candidate_update
                and (
                    opportunity.goal_digest != goal.goal_digest
                    or opportunity.subject != goal.subject
                )
            )
            or opportunity.goal_contract_digest not in {None, goal.contract_digest}
            or opportunity.scope != goal.scope
            or opportunity.checker != goal.checker
            or opportunity.expected_contract != goal.scope.output_contract
            or opportunity.permissions != goal.scope.permissions
            or (opportunity.expires_at - opportunity.created_at).total_seconds()
            > goal.lifetime_seconds
            or self.identity.name not in opportunity.receivers
            or opportunity.expires_at <= now()
        ):
            raise ValueError("opportunity is outside the registered proposal contract")
        # A commitment is an authenticated owner assertion, not proof that its
        # private decision is sound. Proposals remain bound to the original local
        # builder allowlist; the owner validates its exact live goal before use.
        started = time.perf_counter()
        try:
            await asyncio.to_thread(self.store.put, envelope)
            reference = await asyncio.to_thread(
                self.store.reference, "opportunity", caller, opportunity.id
            )
            async with asyncio.timeout(self.seconds):
                drafts = await self.proposer(opportunity.model_copy(deep=True))
            drafts = ProposalDrafts.model_validate(drafts.model_dump())
            if any(draft.builder not in goal.builders for draft in drafts.alternatives):
                raise ValueError("proposer attempted an unregistered builder")
            proposals = propose(opportunity, reference, self.identity, drafts)
            signed = [self.identity.sign(item) for item in proposals]
            response = {"proposals": signed}
            if len(json.dumps(response).encode()) > 196608:
                raise ValueError("proposal reply exceeds byte bound")
            for item in signed:
                await asyncio.to_thread(self.store.put, item)
            return response
        finally:
            event = Event(
                issuer=self.identity.name,
                subject=opportunity.subject,
                action="proposal",
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
            await asyncio.shield(asyncio.to_thread(self.store.put, self.identity.sign(event)))
