"""Small operator-owned application composition over existing execution APIs."""

from __future__ import annotations

import importlib
import re
from typing import Any

from .bindings import Binding, ExecutionContext
from .blocking import run_blocking
from .config import Config
from .models import Capability, Opportunity
from .operations import Operations, OwnerLock
from .opportunities import Goal, Opportunities
from .peer import PeerService
from .proposal_exchange import (
    CollectedProposals,
    ProposalContract,
    ProposalExchange,
    Proposer,
    collect,
)
from .queries import RecordQuery
from .reconciliation import Reconciliations
from .recovery import Recovery
from .steps import Steps


class ApplicationHost(PeerService):
    """An installed factory registers business contracts; this class grants none.

    Factories receive this trusted host at startup. Runtime requests cannot select
    imports, register code, replace goals or change checker contracts.
    """

    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.opportunities: Opportunities | None = None
        self.steps: Steps | None = None
        self._goal_ids: tuple[str, ...] = ()
        self.operations: Operations | None = None
        self.reconciliations = Reconciliations(self.registry, config, self.identity)
        self.recovery = Recovery(self.registry, config, self.identity)

    def close(self) -> None:
        if self.operations is not None:
            self.operations.close()
        self.overlay.store.close()

    def publish_candidate(self, binding: Binding, candidate: Capability) -> Capability:
        """Publish generated status only; retain the original candidate on restart."""
        if (
            binding.issuer != self.config.owner
            or candidate.issuer != self.config.owner
            or candidate.subject != binding.subject
            or candidate.scope != binding.scope
            or candidate.binding_digest != binding.digest
        ):
            raise ValueError("candidate must match the owner's exact registered binding")
        # Validate the public binding lookup, not an invented second registry.
        if self.registry.inspect(binding.id).digest != binding.digest:
            raise ValueError("candidate binding is not the registered revision")
        page = self.overlay.store.record_page(
            RecordQuery(kinds=("capability",), issuer=candidate.issuer, subject=candidate.subject),
            limit=1,
        )
        if page.items:
            saved = page.items[0]
            if not isinstance(saved, Capability) or saved.binding_digest != binding.digest:
                raise ValueError("persisted candidate differs from installed binding")
            return saved
        self.overlay.store.put(self.identity.sign(candidate))
        return candidate

    def register_goals(self, goals: tuple[Goal, ...]) -> None:
        """Connect owner-approved goals to the same Registry and Executor."""
        if self.opportunities is not None:
            raise ValueError("goals already registered; use their explicit revision APIs")
        self.opportunities = Opportunities(self.registry, self.identity, goals)
        self._goal_ids = tuple(g.id for g in goals)
        self.steps = Steps(
            self.opportunities,
            self.executor,
            ExecutionContext(
                caller=self.config.owner,
                environment=self.config.execution_environment,
                permissions=frozenset(self.config.policy.permissions),
            ),
            max_concurrent=self.config.max_concurrency,
        )

    def register_proposer(
        self, contracts: tuple[ProposalContract, ...], proposer: Proposer
    ) -> None:
        if self.proposal_exchange is not None:
            raise ValueError("proposer already registered")
        self.proposal_exchange = ProposalExchange(
            self.overlay.store, self.identity, contracts, proposer, allow_target_updates=True
        )

    async def _collect(self, opportunity: Opportunity) -> CollectedProposals:
        if self.opportunities is None:
            raise ValueError("no registered goals")
        goal = self.opportunities.goal(opportunity.goal_id)
        return await collect(self.config, self.overlay.store, self.identity, goal, opportunity.id)

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        operation = data.get("operation")
        if operation in {"recovery_state", "recovery_review"}:
            if caller != self.config.owner:
                raise ValueError("recovery operations are owner-only")
            if operation == "recovery_state":
                return await run_blocking(self.recovery.inspect)
            return await self.recovery.review(
                caller, str(data["command_id"]), str(data["checker"]), data.get("arguments", {})
            )
        if operation in {"remote_calls", "reconcile"}:
            if caller != self.config.owner:
                raise ValueError("original-call recovery is owner-only")
            if operation == "remote_calls":
                calls = await run_blocking(
                    self.registry.remote_calls,
                    ExecutionContext(caller=caller, environment=self.config.execution_environment),
                    invocation_id=data.get("invocation_id"),
                    call_scope=data.get("call_scope"),
                    limit=int(data.get("limit", 32)),
                    after=data.get("after"),
                )
                return {"calls": [call.model_dump(mode="json") for call in calls]}
            event = await self.reconciliations.observe(
                caller,
                str(data["call_key"]),
                str(data["command_id"]),
                invocation_id=data.get("invocation_id"),
                reconciler=data.get("reconciler"),
            )
            return {
                "event": event.model_dump(mode="json"),
                "envelope": self.identity.sign(event),
                "invocation_unchanged": True,
                "allowance_unchanged": True,
            }
        if operation not in {"goals", "opportunities", "step", "run"}:
            return await super().handle(caller, data)
        if caller != self.config.owner or self.opportunities is None or self.steps is None:
            raise ValueError("owner operation requires installed goal registration")
        if operation == "goals":
            return {
                "goals": [
                    self.opportunities.goal(goal_id).model_dump(mode="json")
                    for goal_id in self._goal_ids
                ]
            }
        if operation == "opportunities":
            return (
                await self.opportunities.discover(
                    max_candidates=int(data.get("max_candidates", 8)),
                    start=int(data.get("start", 0)),
                )
            ).model_dump(mode="json")
        if operation == "step":
            opportunity_id = str(data["opportunity_id"])
            reference = await run_blocking(
                self.overlay.store.reference, "opportunity", caller, opportunity_id
            )
            opportunity = await run_blocking(self.overlay.store.resolve_reference, reference)
            if not isinstance(opportunity, Opportunity):
                raise ValueError("expected registered opportunity")
            return (
                await self.steps.step(opportunity_id, await self._collect(opportunity))
            ).model_dump(mode="json")
        max_steps = int(data.get("max_steps", self.config.max_steps))
        seconds = int(data.get("seconds", self.config.max_seconds))
        if not 1 <= max_steps <= min(self.config.max_steps, 64) or not 1 <= seconds <= min(
            self.config.max_seconds, 300
        ):
            raise ValueError("requested run exceeds the configured owner bounds")
        return (
            await self.steps.run(
                self._collect,
                max_steps=max_steps,
                max_candidates=int(data.get("max_candidates", 8)),
                seconds=seconds,
            )
        ).model_dump(mode="json")


def load_application(config: Config, factory: str | None = None) -> ApplicationHost:
    """Import only the explicit operator-selected, already installed module."""
    name = factory or config.application
    if name is None or not re.fullmatch(r"[A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*:[A-Za-z_]\w*", name):
        raise ValueError("specify an installed application as module:factory")
    module_name, attribute = name.split(":")
    configure = getattr(importlib.import_module(module_name), attribute)
    if not callable(configure):
        raise ValueError("application factory is not callable")
    host = ApplicationHost(config)
    try:
        lock = OwnerLock(host.overlay.store)
        lock.acquire()
        host.operations = Operations(host, lock)
        result = configure(host)
        if result is not None:
            raise ValueError("application factory configures its host and returns None")
        return host
    except BaseException:
        host.close()
        raise
