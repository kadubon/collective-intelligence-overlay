"""Bounded goal observations and untrusted alternatives to installed operations.

These APIs add no execution lifecycle. Operator registration fixes contracts and
allowlists; qualification remains with Overlay and actuation with Registry/Executor.
"""

from __future__ import annotations

import asyncio
from datetime import timedelta
from typing import Any, Self

from pydantic import BaseModel, ConfigDict, Field, JsonValue, model_validator

from .bindings import ExecutionContext, Registry, fingerprint
from .models import (
    BindingRef,
    Cost,
    Decision,
    Identifier,
    Opportunity,
    Outcome,
    Proposal,
    RecordRef,
    UseRequest,
    WorkKind,
    now,
)
from .queries import RecordQuery
from .security import Identity, verify
from .storage import Conflict, projection_digest


class Goal(BaseModel):
    """Trusted host configuration, never accepted from a proposal or model output."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    id: Identifier
    revision: Identifier
    request: UseRequest
    checker: BindingRef
    builders: tuple[BindingRef, ...] = Field(min_length=1, max_length=32)
    peers: tuple[Identifier, ...] = Field(default=(), max_length=16)
    lifetime_seconds: int = Field(default=900, ge=1, le=86400)

    @model_validator(mode="after")
    def fixed_target(self) -> Self:
        if self.request.purpose != "reuse" or not self.request.binding_digest:
            raise ValueError("goal requires an exact ordinary-use target binding")
        if not self.request.capability_issuer:
            raise ValueError("goal requires exact target issuer")
        if len({(b.issuer, b.id) for b in self.builders}) != len(self.builders):
            raise ValueError("duplicate installed builder alternative")
        return self

    @property
    def digest(self) -> str:
        return fingerprint(self.model_dump(mode="json"))


class Discovery(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    opportunities: tuple[Opportunity, ...]
    discovered: int
    deduplicated: int
    satisfied: int
    next_goal: int | None


class ProposalDraft(BaseModel):
    """Model-controlled builder input; no fields for grants, goals or checker changes."""

    model_config = ConfigDict(extra="forbid", frozen=True)
    builder: BindingRef
    arguments: dict[str, JsonValue] = Field(max_length=32)
    alternative: Identifier
    estimates: tuple[Cost, ...] = Field(default=(), max_length=8)


class ProposalDrafts(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    alternatives: tuple[ProposalDraft, ...] = Field(max_length=8)


def propose(
    opportunity: Opportunity, reference: RecordRef, identity: Identity, drafts: ProposalDrafts
) -> tuple[Proposal, ...]:
    """Deterministically wrap bounded alternatives; the receiver must validate each.

    Installed deterministic proposers and MAF structured output use this same path.
    Signing does not imply that a remote owner will accept or execute the result.
    """
    if (
        reference.kind != "opportunity"
        or reference.issuer != opportunity.issuer
        or reference.id != opportunity.id
    ):
        raise ValueError("proposal reference does not identify its opportunity")
    if identity.name not in opportunity.receivers or opportunity.expires_at <= now():
        raise ValueError("opportunity is not shared with this proposer or has expired")
    result = []
    for draft in drafts.alternatives:
        key = fingerprint(
            {
                "observation": reference.model_dump(mode="json"),
                "issuer": identity.name,
                "draft": draft.model_dump(mode="json"),
            }
        )
        result.append(
            Proposal(
                id="proposal-" + key,
                issuer=identity.name,
                subject=opportunity.subject,
                scope=opportunity.scope,
                receivers=(opportunity.issuer,),
                goal_id=opportunity.goal_id,
                goal_digest=opportunity.goal_digest,
                opportunity=reference,
                builder=draft.builder,
                arguments=draft.arguments,
                alternative=draft.alternative,
                estimates=draft.estimates,
                created_at=opportunity.created_at,
                expires_at=opportunity.expires_at,
            )
        )
    if len({item.id for item in result}) != len(result):
        raise ValueError("duplicate proposed alternative")
    return tuple(result)


def work_kind(reasons: tuple[str, ...]) -> WorkKind:
    """Operational routing only: these reasons never grant admission."""
    if {"known_revocation", "dependency_rejected", "in_scope_counterexample"} & set(reasons):
        return "repair"
    if {"scope_mismatch", "dependency_requires_requalification"} & set(reasons):
        return "connection"
    if "freshness_unknown" in reasons:
        return "observation"
    if "independent_evidence_required" in reasons or "capability_expired" in reasons:
        return "verification"
    if "ambiguous_or_missing_subject" in reasons:
        return "formation"
    return "observation"


class Opportunities:
    def __init__(self, registry: Registry, identity: Identity, goals: tuple[Goal, ...]) -> None:
        if identity.name != registry.overlay.store.owner:
            raise ValueError("opportunity identity must belong to the local owner")
        if not 1 <= len(goals) <= 32 or len({g.id for g in goals}) != len(goals):
            raise ValueError("register 1 to 32 distinct bounded goals")
        for goal in goals:
            if goal.request.receiver != identity.name:
                raise ValueError("goal admission belongs to the local receiver")
            if not set(goal.peers) <= registry.overlay.store.principals.keys():
                raise ValueError("goal contains an unconfigured peer")
        self.registry = registry
        self.identity = identity
        self._goals = {g.id: g.model_copy(deep=True) for g in goals}
        self._digests = {g.id: g.digest for g in goals}

    def goal(self, goal_id: str) -> Goal:
        goal = self._goals.get(goal_id)
        if goal is None or goal.digest != self._digests[goal_id]:
            raise ValueError("unregistered or modified goal")
        return goal.model_copy(deep=True)

    async def discover(self, *, max_candidates: int = 8, start: int = 0) -> Discovery:
        if not 1 <= max_candidates <= 32 or not 0 <= start < len(self._goals):
            raise ValueError("invalid discovery bound")
        found: list[Opportunity] = []
        discovered = deduplicated = satisfied = 0
        # Each target has an indexed bounded dependency snapshot. No all-pairs scan.
        end = min(start + max_candidates, len(self._goals))
        for goal_id in tuple(self._goals)[start:end]:
            goal = self.goal(goal_id)
            decision = await self.registry.overlay.qualify(goal.request)
            if decision.outcome == Outcome.ACCEPT:
                satisfied += 1
                continue
            semantic = {
                "goal": goal.digest,
                "outcome": decision.outcome.value,
                "reasons": sorted(decision.reasons),
                "revisions": decision.revisions,
                "evidence_ids": sorted(decision.evidence_ids),
                "policy": decision.policy_digest,
            }
            observation = fingerprint(semantic)
            opportunity_id = "op-" + observation
            query = RecordQuery(
                kinds=("opportunity",), issuer=self.identity.name, record_id=opportunity_id
            )
            store = self.registry.overlay.store
            page = await asyncio.to_thread(store.record_page, query, limit=1)
            if page.items:
                item = page.items[0]
                if not isinstance(item, Opportunity) or item.observation_digest != observation:
                    raise Conflict("opportunity identity does not match observation")
                found.append(item)
                deduplicated += 1
                continue
            kind = work_kind(decision.reasons)
            if "missing_ambiguous_or_cyclic_dependency" in decision.reasons:
                target = await asyncio.to_thread(
                    store.record_page,
                    RecordQuery(
                        kinds=("capability",),
                        issuer=goal.request.capability_issuer,
                        subject=goal.request.subject,
                    ),
                    limit=1,
                )
                if not target.items:
                    kind = "formation"
            item = Opportunity(
                id=opportunity_id,
                issuer=self.identity.name,
                subject=goal.request.subject,
                scope=goal.request.scope,
                receivers=(self.identity.name, *goal.peers),
                goal_id=goal.id,
                goal_digest=goal.digest,
                work_kind=kind,
                basis=(
                    RecordRef(
                        kind="decision",
                        issuer=self.identity.name,
                        id=decision.id,
                        payload_digest=projection_digest(decision.model_dump(mode="json")),
                    ),
                ),
                observation_digest=observation,
                policy_digest=decision.policy_digest,
                reasons=decision.reasons,
                expected_contract=goal.request.scope.output_contract,
                checker=goal.checker,
                permissions=goal.request.scope.permissions,
                expires_at=now() + timedelta(seconds=goal.lifetime_seconds),
            )
            try:
                inserted = await asyncio.to_thread(store.put, self.identity.sign(item))
            except Conflict:
                # Concurrent observers can produce distinct decision IDs/timestamps
                # for the same cause. Retain the first immutable signed observation.
                page = await asyncio.to_thread(store.record_page, query, limit=1)
                existing = page.items[0] if page.items else None
                if (
                    not isinstance(existing, Opportunity)
                    or existing.observation_digest != observation
                ):
                    raise
                item, inserted = existing, False
            discovered += int(inserted)
            deduplicated += int(not inserted)
            found.append(item)
        return Discovery(
            opportunities=tuple(found),
            discovered=discovered,
            deduplicated=deduplicated,
            satisfied=satisfied,
            next_goal=end if end < len(self._goals) else None,
        )

    def validate_proposal(
        self, envelope: dict[str, Any], caller: str, context: ExecutionContext
    ) -> Proposal:
        """Check authenticated input against host constraints, without executing it."""
        store = self.registry.overlay.store
        proposal = verify(envelope, store.principals)
        if not isinstance(proposal, Proposal) or proposal.issuer != caller:
            raise ValueError("proposal issuer must match authenticated peer")
        goal = self.goal(proposal.goal_id)
        if caller not in {self.identity.name, *goal.peers}:
            raise ValueError("peer not authorized for this goal")
        if proposal.goal_digest != goal.digest or proposal.scope != goal.request.scope:
            raise ValueError("proposal changes the registered goal or scope")
        if proposal.subject != goal.request.subject or self.identity.name not in proposal.receivers:
            raise ValueError("proposal target or receiver mismatch")
        if proposal.expires_at <= now():
            raise ValueError("proposal expired")
        opportunity = store.resolve_reference(proposal.opportunity)
        if not isinstance(opportunity, Opportunity) or (
            opportunity.issuer != self.identity.name
            or opportunity.goal_digest != goal.digest
            or opportunity.scope != goal.request.scope
            or opportunity.subject != goal.request.subject
            or opportunity.checker != goal.checker
            or opportunity.expires_at <= now()
            or opportunity.policy_digest != self.registry.overlay.policy.digest
        ):
            raise ValueError("proposal refers to an inapplicable opportunity")
        if proposal.expires_at > opportunity.expires_at:
            raise ValueError("proposal cannot extend its observation lifetime")
        for reference in opportunity.basis:
            basis = store.resolve_reference(reference)
            if isinstance(basis, Decision) and (
                basis.request != goal.request
                or basis.policy_digest != opportunity.policy_digest
                or basis.revisions != store.revisions(set(basis.revisions))
            ):
                raise ValueError("opportunity observation changed; rediscovery required")
        if proposal.builder not in goal.builders:
            raise ValueError("builder is not authorized for this goal")
        binding = self.registry.inspect(proposal.builder.id)
        if binding.issuer != proposal.builder.issuer or binding.digest != proposal.builder.digest:
            raise ValueError("installed builder identity changed")
        if context.caller != self.identity.name or context.purpose != "reuse":
            raise ValueError("proposal selection requires owner execution context")
        self.registry.prepare(binding.id, binding.digest, proposal.arguments, context)
        return proposal
