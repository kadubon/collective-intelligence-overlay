"""Local qualification, bounded lineage and use-time enforcement."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import TypeVar

from .models import Capability, Decision, Evidence, Outcome, Subject, UseRequest, now, uid
from .policy import Policy
from .storage import Store

T = TypeVar("T")


class AdmissionDenied(RuntimeError):
    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        super().__init__(f"{decision.outcome}: {', '.join(decision.reasons)}")


class Overlay:
    def __init__(self, store: Store, policy: Policy, *, max_graph_nodes: int = 256) -> None:
        if not 1 <= max_graph_nodes <= 1024:
            raise ValueError("invalid graph limit")
        self.store = store
        self.policy = policy
        self.max_graph_nodes = max_graph_nodes
        # Operator/transport supplied reachability, never taken from agent content.
        self.observed_sources: dict[str, datetime] = {store.owner: now()}

    def observed(self, issuer: str) -> None:
        if issuer not in self.store.principals:
            raise ValueError("unknown source")
        self.observed_sources[issuer] = now()

    async def qualify(self, request: UseRequest) -> Decision:
        try:
            async with asyncio.timeout(30):
                return await self._qualify(request)
        except TimeoutError:
            decision = self._decision(request, Outcome.UNKNOWN, ("qualification_timeout",))
            self.store.save_decision(decision)
            return decision

    async def _qualify(self, request: UseRequest) -> Decision:
        if request.receiver != self.store.owner:
            raise ValueError("admission is local")
        epoch = self.store.record_count()
        valid_until = now() + timedelta(seconds=self.policy.settings.max_source_age_seconds)
        try:
            caps = self.store.capabilities()
            evidence = self.store.evidence()
            revocations = self.store.revocations()
            timestamp = now()
            visited: set[str] = set()
            evaluations = 0
            support_steps = 0

            def source_current(issuer: str) -> bool:
                if issuer == self.store.owner:
                    return True
                observed = self.observed_sources.get(issuer)
                return (
                    observed is not None
                    and 0
                    <= (timestamp - observed).total_seconds()
                    <= self.policy.settings.max_source_age_seconds
                )

            def matching(subject: Subject) -> list[Capability]:
                return [c for c in caps if c.subject == subject]

            def evidence_supported(e: Evidence, path: frozenset[str]) -> bool:
                nonlocal support_steps
                support_steps += 1
                if support_steps > self.max_graph_nodes * 4:
                    return False
                if e.id in path or len(path) >= self.max_graph_nodes:
                    return False
                for eid in e.evidence_dependencies:
                    candidates = [x for x in evidence if x.id == eid]
                    if len(candidates) != 1:
                        return False
                    support = candidates[0]
                    if (
                        support.verdict != "PASS"
                        or not support.created_at <= timestamp < support.expires_at
                        or not source_current(support.issuer)
                        or (timestamp - support.created_at).total_seconds()
                        > self.policy.settings.max_evidence_age_seconds
                        or support.obligations
                        or support.scope != e.scope
                        or support.subject != e.subject
                        or support.claim != e.claim
                        or not set(e.receivers).issubset(support.receivers)
                        or support.method not in self.store.principals[support.issuer].methods
                        or any(
                            r.evidence_id == eid and r.issuer == support.issuer for r in revocations
                        )
                        or not evidence_supported(support, path | {e.id})
                    ):
                        return False
                return True

            async def evaluate(req: UseRequest, path: frozenset[str]) -> Decision:
                nonlocal evaluations, valid_until
                evaluations += 1
                subject = req.subject
                key = subject.key
                visited.add(key)
                matches = matching(subject)
                if (
                    key in path
                    or len(visited) > self.max_graph_nodes
                    or len(matches) != 1
                    or evaluations > self.max_graph_nodes * 4
                    or len(path) > 64
                ):
                    return self._decision(
                        req, Outcome.UNKNOWN, ("missing_ambiguous_or_cyclic_dependency",)
                    )
                cap = matches[0]
                valid_until = min(valid_until, cap.expires_at)
                child_outcomes = []
                for dependency in cap.dependencies:
                    candidates = matching(dependency)
                    if len(candidates) != 1:
                        child_outcomes.append(Outcome.UNKNOWN)
                    else:
                        child_req = UseRequest(
                            receiver=req.receiver,
                            subject=dependency,
                            scope=candidates[0].scope,
                            semantic_fit=req.semantic_fit,
                        )
                        child_outcomes.append((await evaluate(child_req, path | {key})).outcome)
                order = [Outcome.REJECT, Outcome.UNKNOWN, Outcome.REQUALIFY, Outcome.ACCEPT]
                dependency_state = next((s for s in order if s in child_outcomes), Outcome.ACCEPT)
                applicable_evidence = []
                for e in evidence:
                    if e.subject != subject:
                        continue
                    if e.created_at <= timestamp < e.expires_at and e.scope == req.scope:
                        valid_until = min(
                            valid_until,
                            e.expires_at,
                            e.created_at
                            + timedelta(seconds=self.policy.settings.max_evidence_age_seconds),
                        )
                    issuer = self.store.principals[e.issuer]
                    producer = self.store.principals[cap.issuer]
                    withdrawn = any(
                        r.evidence_id == e.id and r.issuer == e.issuer for r in revocations
                    )
                    applicable_evidence.append(
                        {
                            "id": e.id,
                            "verdict": e.verdict,
                            "applicable": e.scope == req.scope
                            and e.claim == cap.claim
                            and req.receiver in e.receivers,
                            "fresh": e.created_at <= timestamp < e.expires_at
                            and not withdrawn
                            and (timestamp - e.created_at).total_seconds()
                            <= self.policy.settings.max_evidence_age_seconds,
                            "authorized": e.method in issuer.methods,
                            "independent": e.issuer != cap.issuer
                            and issuer.trust_group != producer.trust_group,
                            "obligations": e.obligations,
                            "support_valid": evidence_supported(e, frozenset()),
                        }
                    )
                source_issuers = {cap.issuer} | {
                    e.issuer
                    for e in evidence
                    if e.subject == subject
                    and e.scope == req.scope
                    and e.claim == cap.claim
                    and req.receiver in e.receivers
                    and e.method in self.store.principals[e.issuer].methods
                }
                source_fresh = all(source_current(issuer) for issuer in source_issuers)
                for source_issuer in source_issuers - {self.store.owner}:
                    if source_issuer in self.observed_sources:
                        valid_until = min(
                            valid_until,
                            self.observed_sources[source_issuer]
                            + timedelta(seconds=self.policy.settings.max_source_age_seconds),
                        )
                facts = {
                    "capability": cap.model_dump(mode="json"),
                    "request": req.model_dump(mode="json"),
                    "subject_valid": True,
                    "source_fresh": source_fresh,
                    "capability_fresh": cap.created_at <= timestamp < cap.expires_at,
                    "revoked": any(
                        r.subject == subject and r.evidence_id is None and r.issuer == cap.issuer
                        for r in revocations
                    ),
                    "dependency_state": dependency_state,
                    "evidence": applicable_evidence,
                }
                outcome, reasons = await self.policy.decide(facts)
                return self._decision(
                    req, outcome, reasons, tuple(str(e["id"]) for e in applicable_evidence)
                )

            decision = await evaluate(request, frozenset())
        except (ValueError, RecursionError):
            decision = self._decision(request, Outcome.UNKNOWN, ("invalid_or_excessive_records",))
        decision = decision.model_copy(update={"record_count": epoch, "valid_until": valid_until})
        if decision.outcome == Outcome.ACCEPT and (
            self.store.record_count() != epoch or now() >= valid_until
        ):
            decision = decision.model_copy(
                update={"outcome": Outcome.UNKNOWN, "reasons": ("state_changed_during_check",)}
            )
        self.store.save_decision(decision)
        return decision

    def _decision(
        self,
        request: UseRequest,
        outcome: Outcome,
        reasons: tuple[str, ...],
        evidence: tuple[str, ...] = (),
    ) -> Decision:
        return Decision(
            request=request,
            outcome=outcome,
            reasons=reasons,
            policy_digest=self.policy.digest,
            evidence_ids=evidence,
        )

    async def execute(
        self,
        request: UseRequest,
        operation: Callable[[], Awaitable[T]],
        *,
        deadline_seconds: float = 30,
    ) -> T:
        """Recheck at the actual trusted actuator boundary, without cached ACCEPT."""
        if not 0 < deadline_seconds <= 3600:
            raise ValueError("timeout must be bounded")
        async with asyncio.timeout(deadline_seconds):
            decision = await self.qualify(request)
            if decision.outcome == Outcome.ACCEPT and (
                self.store.record_count() != decision.record_count or now() >= decision.valid_until
            ):
                decision = decision.model_copy(
                    update={"outcome": Outcome.UNKNOWN, "reasons": ("state_changed_before_use",)}
                )
                self.store.save_decision(decision.model_copy(update={"id": uid()}))
            if decision.outcome != Outcome.ACCEPT:
                raise AdmissionDenied(decision)
            return await operation()

    @staticmethod
    def recommend(decision: Decision) -> tuple[str, ...]:
        if decision.outcome == Outcome.ACCEPT:
            return ("reuse_with_use_time_check",)
        if "freshness_unknown" in decision.reasons:
            return ("connection", "observation")
        if decision.outcome == Outcome.REJECT:
            return ("repair", "alternative_formation")
        return ("verification", "scope_qualification")
