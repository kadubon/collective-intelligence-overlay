"""Local qualification, bounded lineage and use-time enforcement."""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import TypeVar

from .models import Capability, Decision, Evidence, Outcome, Subject, UseRequest, now, uid
from .policy import Policy
from .storage import Store, subject_key

T = TypeVar("T")


class AdmissionDenied(RuntimeError):
    def __init__(self, decision: Decision) -> None:
        self.decision = decision
        super().__init__(f"{decision.outcome}: {', '.join(decision.reasons)}")


class Overlay:
    def __init__(
        self,
        store: Store,
        policy: Policy,
        *,
        max_graph_nodes: int = 256,
        persistent_sources: bool = False,
    ) -> None:
        if not 1 <= max_graph_nodes <= 1024:
            raise ValueError("invalid graph limit")
        self.store = store
        self.policy = policy
        self.max_graph_nodes = max_graph_nodes
        self.persistent_sources = persistent_sources
        # Operator/transport supplied reachability, never taken from agent content.
        self.observed_sources: dict[str, datetime] = {store.owner: now()}

    def observed(self, issuer: str) -> None:
        if self.persistent_sources:
            raise ValueError("peer freshness requires committed synchronization, not reachability")
        if issuer not in self.store.principals:
            raise ValueError("unknown source")
        self.observed_sources[issuer] = now()

    async def _sources_unchanged(self, observed: dict[str, datetime | None]) -> bool:
        if not self.persistent_sources:
            return True
        from .synchronization import Receiver

        current = await asyncio.to_thread(
            Receiver(self.store).observations, {key.rsplit(":", 1)[1] for key in observed}
        )
        return all(current.get(key) == anchor for key, anchor in observed.items())

    async def qualify(self, request: UseRequest, *, verification_granted: bool = False) -> Decision:
        try:
            async with asyncio.timeout(30):
                return await self._qualify(request, verification_granted=verification_granted)
        except TimeoutError:
            decision = self._decision(request, Outcome.UNKNOWN, ("qualification_timeout",))
            await asyncio.to_thread(self.store.save_decision, decision)
            return decision

    async def _qualify(
        self, request: UseRequest, *, verification_granted: bool = False
    ) -> Decision:
        if request.receiver != self.store.owner:
            raise ValueError("admission is local")
        revisions: dict[str, int] = {}
        used_sources: dict[str, datetime | None] = {}
        valid_until = now() + timedelta(seconds=self.policy.settings.max_source_age_seconds)
        try:
            snapshot = await asyncio.to_thread(
                self.store.admission_snapshot, request, self.max_graph_nodes
            )
            caps, evidence, revocations = (
                snapshot.capabilities,
                snapshot.evidence,
                snapshot.revocations,
            )
            revisions = snapshot.revisions
            observations: dict[str, datetime | None] = {}
            if self.persistent_sources:
                from .synchronization import Receiver

                observations = await asyncio.to_thread(
                    Receiver(self.store).observations, set(revisions)
                )
            timestamp = now()
            visited: set[tuple[str, str]] = set()
            evaluations = 0
            support_steps = 0

            def observation(issuer: str, subject: Subject) -> datetime | None:
                key = issuer + ":" + subject_key(subject)
                observed = (
                    observations.get(key)
                    if self.persistent_sources
                    else self.observed_sources.get(issuer)
                )
                if self.persistent_sources and issuer != self.store.owner:
                    used_sources[key] = observed
                return observed

            def source_current(issuer: str, subject: Subject) -> bool:
                if issuer == self.store.owner:
                    return True
                observed = observation(issuer, subject)
                return (
                    observed is not None
                    and 0
                    <= (timestamp - observed).total_seconds()
                    <= self.policy.settings.max_source_age_seconds
                )

            def matching(subject: Subject, issuer: str | None = None) -> list[Capability]:
                return [
                    c
                    for c in caps
                    if c.subject == subject and (issuer is None or c.issuer == issuer)
                ]

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
                        or not source_current(support.issuer, support.subject)
                        or (timestamp - support.created_at).total_seconds()
                        > self.policy.settings.max_evidence_age_seconds
                        or support.obligations
                        or support.scope != e.scope
                        or support.subject != e.subject
                        or support.claim != e.claim
                        or support.binding_digest != e.binding_digest
                        or not set(e.receivers).issubset(support.receivers)
                        or support.method not in self.store.principals[support.issuer].methods
                        or any(
                            r.evidence_id == eid and r.issuer == support.issuer for r in revocations
                        )
                        or not evidence_supported(support, path | {e.id})
                    ):
                        return False
                return True

            async def evaluate(
                req: UseRequest,
                path: frozenset[tuple[str, str]],
                *,
                integrity_only: bool = False,
            ) -> Decision:
                nonlocal evaluations, valid_until
                evaluations += 1
                subject = req.subject
                matches = matching(subject, req.capability_issuer)
                if len(matches) != 1:
                    return self._decision(
                        req, Outcome.UNKNOWN, ("missing_ambiguous_or_cyclic_dependency",)
                    )
                cap = matches[0]
                key = (cap.issuer, subject_key(subject))
                visited.add(key)
                if (
                    key in path
                    or len(visited) > self.max_graph_nodes
                    or evaluations > self.max_graph_nodes * 4
                    or len(path) > 64
                ):
                    return self._decision(
                        req, Outcome.UNKNOWN, ("missing_ambiguous_or_cyclic_dependency",)
                    )
                if req.binding_digest != cap.binding_digest:
                    return self._decision(req, Outcome.REQUALIFY, ("binding_evidence_required",))
                valid_until = min(valid_until, cap.expires_at)
                child_outcomes = []
                for index, dependency in enumerate(cap.dependencies):
                    dep_issuer = cap.dependency_issuers[index] if cap.dependency_issuers else None
                    candidates = matching(dependency, dep_issuer)
                    if len(candidates) != 1:
                        child_outcomes.append(Outcome.UNKNOWN)
                    else:
                        child_req = UseRequest(
                            receiver=req.receiver,
                            subject=dependency,
                            scope=candidates[0].scope,
                            semantic_fit="unknown",
                            capability_issuer=dep_issuer,
                            binding_digest=candidates[0].binding_digest,
                        )
                        child_outcomes.append(
                            (await evaluate(child_req, path | {key}, integrity_only=True)).outcome
                        )
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
                            and e.binding_digest == req.binding_digest
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
                source_fresh = all(source_current(issuer, subject) for issuer in source_issuers)
                for source_issuer in source_issuers - {self.store.owner}:
                    observed = observation(source_issuer, subject)
                    if observed is not None:
                        valid_until = min(
                            valid_until,
                            observed
                            + timedelta(seconds=self.policy.settings.max_source_age_seconds),
                        )
                facts = {
                    "verification_granted": verification_granted and req.purpose == "verification",
                    "dependency_integrity_only": integrity_only,
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
        decision = decision.model_copy(
            update={
                "revisions": revisions,
                "valid_until": valid_until,
                "source_observations": used_sources,
            }
        )
        if decision.outcome == Outcome.ACCEPT and (
            await asyncio.to_thread(self.store.revisions, set(revisions)) != revisions
            or now() >= valid_until
            or not await self._sources_unchanged(used_sources)
        ):
            decision = decision.model_copy(
                update={"outcome": Outcome.UNKNOWN, "reasons": ("state_changed_during_check",)}
            )
        await asyncio.to_thread(self.store.save_decision, decision)
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
        verification_granted: bool = False,
    ) -> T:
        """Recheck at the actual trusted actuator boundary, without cached ACCEPT."""
        if not 0 < deadline_seconds <= 3600:
            raise ValueError("timeout must be bounded")
        async with asyncio.timeout(deadline_seconds):
            decision = await self.qualify(request, verification_granted=verification_granted)
            if decision.outcome == Outcome.ACCEPT and (
                await asyncio.to_thread(self.store.revisions, set(decision.revisions))
                != decision.revisions
                or now() >= decision.valid_until
                or not await self._sources_unchanged(decision.source_observations)
            ):
                decision = decision.model_copy(
                    update={"outcome": Outcome.UNKNOWN, "reasons": ("state_changed_before_use",)}
                )
                await asyncio.to_thread(
                    self.store.save_decision, decision.model_copy(update={"id": uid()})
                )
            if decision.outcome != Outcome.ACCEPT:
                raise AdmissionDenied(decision)
            return await operation()

    @staticmethod
    def recommend(decision: Decision) -> tuple[str, ...]:
        if decision.outcome == Outcome.ACCEPT:
            if decision.request.purpose == "verification":
                return ("independent_check_result",)
            return ("reuse_with_use_time_check",)
        if "freshness_unknown" in decision.reasons:
            return ("connection", "observation")
        if decision.outcome == Outcome.REJECT:
            return ("repair", "alternative_formation")
        return ("verification", "scope_qualification")
