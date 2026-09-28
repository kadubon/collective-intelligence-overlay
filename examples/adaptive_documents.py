"""Finite, observation-driven document formation using public overlay APIs.

Initial setup supplies checked primitives and fixed application contracts. The
receiver selects actual peer alternatives; the harness never names later work.
The installed application materializes the selected computation's result into a
callable. This is a deterministic domain application, not an LLM benchmark.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from contextlib import AsyncExitStack
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from document_application import ENVIRONMENT, CandidateChanged, DocumentService

from collective_intelligence_overlay.adapters.a2a import application, send, synchronize
from collective_intelligence_overlay.allocation import AllocationPolicy, allocate
from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Target,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.config import Config, load_config
from collective_intelligence_overlay.lineage import FormationSession
from collective_intelligence_overlay.models import (
    BindingRef,
    Event,
    Evidence,
    Opportunity,
    Proposal,
    Scope,
    Subject,
    UseRequest,
    now,
)
from collective_intelligence_overlay.opportunities import (
    Goal,
    Opportunities,
    ProposalDraft,
    ProposalDrafts,
)
from collective_intelligence_overlay.proposal_exchange import (
    ProposalContract,
    ProposalExchange,
    collect,
)
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.steps import Steps
from collective_intelligence_overlay.storage import Conflict


def binding_ref(binding: Any) -> BindingRef:
    return BindingRef(issuer=binding.issuer, id=binding.id, digest=binding.digest)


def write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, indent=2), encoding="utf-8")
    temporary.replace(path)


class AdaptiveDocuments(DocumentService):
    def __init__(self, config: Config) -> None:
        super().__init__(config)
        self.home = config.private_key.parent
        data = json.loads((self.home / "application.json").read_text(encoding="utf-8"))
        self.training_text = data["training_text"]
        self.report_input = data.get("report_input", "text")
        if self.report_input not in {"text", "document"}:
            raise ValueError("unsupported report input contract")
        self.allocation_policy = AllocationPolicy.model_validate(
            data.get(
                "allocation",
                {
                    "minimum_samples": 1,
                    "verification_threshold": 1,
                    "connection_threshold": 1,
                },
            )
        )
        self.contracts = tuple(ProposalContract.model_validate(item) for item in data["contracts"])
        if config.owner == "verifier":
            self.checker_binding = checker_binding()
            self.registry.register_local(
                self.checker_binding,
                self.check_requested_candidate,
                lambda args: args["name"] in {"report", "triage", "remote-words"},
            )
            self.publish(self.checker_binding)
        if config.owner in {"producer", "verifier"}:
            self.proposal_exchange = ProposalExchange(
                self.overlay.store,
                self.identity,
                self.contracts,
                self.propose,
                allow_target_updates=True,
            )
        if config.owner == "receiver":
            self._run_lock = asyncio.Lock()
            self.checker_binding = remote_checker_binding(config)
            self.registry.register_a2a(
                self.checker_binding, lambda args: True, config, self.identity
            )
            self.publish(self.checker_binding, (checker_binding(),), imported=True)
            if "report" not in self.installed:
                # An installed factory is not yet a published/verified candidate.
                self.install_report()
            goals = tuple(Goal.model_validate(item) for item in data["goals"])
            self.opportunities = Opportunities(self.registry, self.identity, goals)
            for goal in goals:
                if goal.id not in self.installed:
                    continue
                binding = self.installed[goal.id]
                page = self.overlay.store.record_page(
                    RecordQuery(
                        kinds=("capability",), issuer=config.owner, subject=binding.subject
                    ),
                    limit=1,
                )
                if page.items and binding.scope == goal.request.scope:
                    reference = self.overlay.store.reference(
                        "capability", config.owner, binding.subject.key
                    )
                    self.opportunities.select_target(goal.id, goal.digest, binding.id, reference)
            self.context = ExecutionContext(caller=config.owner, environment=ENVIRONMENT)
            self.steps = Steps(
                self.opportunities,
                self.executor,
                self.context,
                max_concurrent=min(4, config.max_concurrency),
            )
            self.save_goals()

    def save_goals(self) -> None:
        path = self.home / "application.json"
        data = json.loads(path.read_text(encoding="utf-8"))
        data["goals"] = [
            self.opportunities.goal(name).model_dump(mode="json") for name in ("report", "triage")
        ]
        write_json(path, data)

    async def propose(self, opportunity: Opportunity) -> ProposalDrafts:
        contract = next(item for item in self.contracts if item.id == opportunity.goal_id)
        if opportunity.work_kind == "verification":
            described = await send(
                self.config,
                self.identity,
                "receiver",
                {
                    "operation": "describe",
                    "name": opportunity.goal_id,
                },
            )
            binding = Binding.model_validate(described["binding"])
            if binding.subject != opportunity.subject:
                return ProposalDrafts(alternatives=())
            return ProposalDrafts(
                alternatives=(
                    ProposalDraft(
                        builder=contract.checker,
                        alternative=self.config.owner + "-check",
                        arguments={
                            "name": opportunity.goal_id,
                            "attempt": "check-" + opportunity.id,
                            "binding_digest": binding.digest,
                        },
                    ),
                )
            )
        if opportunity.work_kind not in {"formation", "connection"}:
            return ProposalDrafts(alternatives=())
        # Distinct, operator-supplied calibration hypotheses. Neither peer sees
        # the independent check corpus or the final evaluation document.
        text = self.training_text
        if self.config.owner == "verifier":
            text += " alternative"
        return ProposalDrafts(
            alternatives=(
                ProposalDraft(
                    builder=contract.builders[0],
                    arguments={
                        self.report_input if opportunity.goal_id == "triage" else "text": text
                    },
                    alternative=self.config.owner + "-calibration",
                ),
            )
        )

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        if data.get("operation") == "describe-checker":
            if self.config.owner not in {"receiver", "verifier"}:
                raise ValueError("no installed checker")
            return {"binding": self.checker_binding.model_dump(mode="json")}
        if data.get("operation") == "certify-checker":
            if caller != "producer" or self.config.owner != "producer":
                raise ValueError("checker tests belong to the producer operator")
            async with asyncio.timeout(min(self.config.max_seconds, 90)):
                return await self.certify_checker(str(data["target"]))
        if data.get("operation") == "request-document-check":
            if self.config.owner != "verifier" or caller != "receiver":
                raise ValueError("document checking requires the configured receiver")
            if data["checker_digest"] != self.checker_binding.digest:
                raise ValueError("registered checker implementation changed")
            prepared = self.registry.prepare(
                self.checker_binding.id,
                self.checker_binding.digest,
                {key: data[key] for key in ("name", "attempt", "binding_digest")},
                ExecutionContext(caller=caller, environment=ENVIRONMENT),
            )
            try:
                return await self.check_requested_candidate(prepared.arguments)
            except Conflict:
                return {"state": "conflict", "error": "CHECK_ATTEMPT_OR_ALLOWANCE_CONFLICT"}
        if data.get("operation") in {"adaptive-run", "static-run"}:
            if caller != self.config.owner or caller != "receiver":
                raise ValueError("only the receiver owner may start its finite application")
            if self._run_lock.locked():
                return {"reason": "already_running", "history": [], "pid": os.getpid()}
            async with self._run_lock:
                run = self.run_static if data["operation"] == "static-run" else self.run
                return await run(int(data.get("max_steps", 8)))
        return await super().handle(caller, data)

    async def check_requested_candidate(self, data: dict[str, Any]) -> dict[str, Any]:
        name = str(data["name"])
        if name not in {"report", "triage", "remote-words"}:
            raise ValueError("checker contract does not cover this target")
        try:
            result = await self.check(
                {
                    "provider": "receiver",
                    "name": name,
                    "attempt": str(data["attempt"]),
                    "binding_digest": data["binding_digest"],
                    "arguments": {
                        self.report_input
                        if name == "report"
                        else "text": "independent\tvalidation 文書\nwith separate contents"
                    },
                }
            )
        except CandidateChanged:
            return {"state": "rejected", "reason": "target_changed"}
        if result["evidence"]["binding_digest"] != data["binding_digest"]:
            raise ValueError("checked candidate changed during the request")
        return result

    async def certify_checker(self, target: str) -> dict[str, Any]:
        """Independent, finite black-box calibration before ordinary checker use."""
        if target not in {"verifier", "receiver"}:
            raise ValueError("unconfigured checker owner")
        expected = (
            checker_binding() if target == "verifier" else remote_checker_binding(self.config)
        )
        final_id = "checker-certified-" + expected.digest

        async def saved(identifier: str) -> dict[str, Any] | None:
            page = await asyncio.to_thread(
                self.overlay.store.record_page,
                RecordQuery(
                    kinds=("evidence",),
                    issuer=self.config.owner,
                    record_id=identifier,
                ),
                limit=1,
            )
            if not page.items:
                return None
            evidence = page.items[0]
            if not isinstance(evidence, Evidence):
                raise ValueError("stored calibration is not evidence")
            artifact = json.loads(self.artifacts.get(evidence.artifact_digest))
            return {"evidence": evidence.model_dump(mode="json"), "checks": artifact["checks"]}

        previous = await saved(final_id)
        if previous is not None:
            return previous
        started = now()
        await synchronize(self.config, self.identity, self.overlay.store, target, page_size=4)
        description = await send(
            self.config, self.identity, target, {"operation": "describe-checker"}
        )
        binding = Binding.model_validate(description["binding"])
        if binding != expected:
            raise ValueError("checker differs from installed operator contract")
        cap = self.overlay.store.record_page(
            RecordQuery(kinds=("capability",), issuer=target, subject=binding.subject), limit=1
        ).items[0]
        source = await send(
            self.config,
            self.identity,
            "receiver",
            {"operation": "describe", "name": "remote-words"},
        )
        source_binding = Binding.model_validate(source["binding"])
        transcript = []
        for name, pin in (("positive", source_binding.digest), ("changed-target", "0" * 64)):
            attempt = "checker-test-" + fingerprint([binding.digest, name])
            response = await send(
                self.config,
                self.identity,
                target,
                {
                    "operation": "invoke",
                    "purpose": "verification",
                    "invocation_id": attempt,
                    "binding_id": binding.id,
                    "binding_digest": binding.digest,
                    "arguments": {
                        "name": "remote-words",
                        "attempt": attempt,
                        "binding_digest": pin,
                    },
                },
            )
            transcript.append(response)
        positive, negative = transcript
        passed = (
            positive.get("state") == "completed"
            and positive["result"]["observed"].get("state") == "completed"
            and positive["result"]["observed"].get("binding_digest") == source_binding.digest
            and positive["result"]["observed"].get("result") == {"words": 6}
            and positive["result"]["evidence"]["verdict"] == "PASS"
            and positive["result"]["evidence"]["binding_digest"] == source_binding.digest
            and positive["result"]["evidence"]["subject"]
            == source_binding.subject.model_dump(mode="json")
            and positive["result"]["evidence"]["scope"]
            == source_binding.scope.model_dump(mode="json")
            and negative.get("state") == "completed"
            and negative.get("result") == {"state": "rejected", "reason": "target_changed"}
        )
        verdict = (
            "UNKNOWN"
            if any(item.get("state") != "completed" for item in transcript)
            else ("PASS" if passed else "FAIL")
        )
        evidence_id = (
            final_id
            if verdict != "UNKNOWN"
            else "checker-observation-" + fingerprint([binding.digest, transcript])
        )
        previous = await saved(evidence_id)
        if previous is not None:
            return previous
        observed_at = min(
            [
                started,
                *(
                    datetime.fromisoformat(item["updated_at"])
                    for item in transcript
                    if "updated_at" in item
                ),
            ]
        )
        expires_at = observed_at + timedelta(hours=1)
        if expires_at <= now():
            return {"state": "unknown", "reason": "expired_calibration"}
        artifact = self.artifacts.put(
            json.dumps(
                {"binding": binding.model_dump(mode="json"), "checks": transcript}, sort_keys=True
            ).encode()
        )
        evidence = Evidence(
            schema_version="2",
            id=evidence_id,
            issuer=self.config.owner,
            subject=binding.subject,
            binding_digest=binding.digest,
            scope=binding.scope,
            claim=cap.claim,
            receivers=("receiver", "verifier"),
            verdict=verdict,
            method="reference-check",
            verifier_version="checker-contract-tests.v1",
            artifact_digest=artifact,
            expires_at=expires_at,
        )
        try:
            self.overlay.store.put(self.identity.sign(evidence))
        except Conflict:
            previous = await saved(evidence_id)
            if previous is None:
                raise
            return previous
        return {"evidence": evidence.model_dump(mode="json"), "checks": transcript}

    async def run(self, max_steps: int) -> dict[str, Any]:
        if not 1 <= max_steps <= min(self.config.max_steps, 16):
            raise ValueError("invalid document application step bound")
        history: list[dict[str, Any]] = []
        seen: set[str] = set()
        reason = "step_limit"
        async with asyncio.timeout(min(self.config.max_seconds, 120)):
            for _ in range(max_steps):
                sync = await synchronize(
                    self.config, self.identity, self.overlay.store, "verifier", page_size=4
                )
                if not sync["complete"]:
                    reason = "incomplete_observation"
                    break
                discovery = await self.opportunities.discover(max_candidates=2)
                if discovery.satisfied == 2:
                    reason = "goals_satisfied"
                    break
                allocation = await allocate(
                    self.opportunities,
                    self.context,
                    discovery.opportunities,
                    self.allocation_policy,
                    await asyncio.to_thread(self.steps.last_allocation),
                )
                by_id = {item.id: item for item in discovery.opportunities}
                pending = [by_id[key] for key in allocation.ordered if key not in seen]
                if not pending:
                    reason = "no_progress"
                    break
                observation = pending[0]
                seen.add(observation.id)
                goal = self.opportunities.goal(observation.goal_id)
                replies = (
                    await collect(
                        self.config, self.overlay.store, self.identity, goal, observation.id
                    )
                    if observation.work_kind in {"formation", "verification", "connection"}
                    else None
                )
                if replies is not None and not replies.replies:
                    reason = "proposers_unavailable"
                    break
                if observation.work_kind == "verification":
                    if self.config.max_rechecks == 0:
                        reason = "checking_disabled"
                        break
                    assert replies is not None
                    for caller, envelope in replies.replies:
                        proposal = self.opportunities.validate_proposal(
                            envelope, caller, self.context
                        )
                        if proposal.builder != goal.checker or proposal.arguments != {
                            "name": goal.id,
                            "attempt": "check-" + observation.id,
                            "binding_digest": goal.request.binding_digest,
                        }:
                            raise ValueError("checker proposal changes the registered target")
                    checked_step = await self.steps.step(
                        observation.id, replies.replies, allocation=allocation
                    )
                    if (
                        checked_step.invocation is None
                        or checked_step.invocation["state"] != "completed"
                    ):
                        history.append(
                            {
                                "opportunity": observation.id,
                                "kind": "verification",
                                "step": checked_step.model_dump(mode="json"),
                            }
                        )
                        reason = "check_not_completed"
                        break
                    checked = checked_step.invocation["result"]
                    if "evidence" not in checked:
                        history.append(
                            {
                                "opportunity": observation.id,
                                "kind": "verification",
                                "step": checked_step.model_dump(mode="json"),
                                "unresolved": checked,
                            }
                        )
                        reason = "check_not_completed"
                        break
                    history.append(
                        {
                            "opportunity": observation.id,
                            "kind": "verification",
                            "evidence": checked["evidence"],
                            "step": checked_step.model_dump(mode="json"),
                            "allocation": allocation.model_dump(mode="json"),
                        }
                    )
                    continue
                if observation.work_kind not in {"formation", "connection"}:
                    reason = "requires_" + observation.work_kind
                    break
                assert replies is not None
                if self.config.max_children == 0:
                    reason = "child_limit"
                    break
                async with AsyncExitStack() as stack:
                    try:
                        formation = await stack.enter_async_context(
                            FormationSession(
                                self.registry,
                                self.identity,
                                max_steps=min(8, self.config.max_children),
                                max_seconds=min(30, self.config.max_seconds),
                                minimum_remaining=max(
                                    self.executor.allowance.minimum_remaining,
                                    self.executor.allowance.quantity
                                    * allocation.reserve_operations,
                                ),
                            )
                        )
                    except Conflict:
                        reason = "insufficient_allowance"
                        break
                    result = await self.steps.step(
                        observation.id, replies.replies, allocation=allocation
                    )
                    if result.invocation is None or result.invocation["state"] != "completed":
                        history.append(
                            {"kind": observation.work_kind, "step": result.model_dump(mode="json")}
                        )
                        reason = "formation_not_completed"
                        break
                    assert result.selection is not None
                    selected = self.overlay.store.resolve_reference(result.selection.proposal)
                    assert isinstance(selected, Proposal)
                    # Re-reading a completed invocation through Executor retains
                    # the original receipt in this session without new execution.
                    computation = await self.executor.invoke(
                        result.selection.invocation_id,
                        selected.builder.id,
                        selected.builder.digest,
                        selected.arguments,
                        self.context,
                    )
                    binding, event = await self.materialize(
                        formation, goal.id, computation, observation.id
                    )
                history.append(
                    {
                        "opportunity": observation.id,
                        "kind": observation.work_kind,
                        "target": binding.id,
                        "step": result.model_dump(mode="json"),
                        "formation": event.model_dump(mode="json"),
                        "proposers": [caller for caller, _ in replies.replies],
                        "allocation": allocation.model_dump(mode="json"),
                    }
                )
        return {"reason": reason, "history": history, "pid": os.getpid()}

    async def materialize(
        self, formation: FormationSession, name: str, computation: dict[str, Any], attempt: str
    ) -> tuple[Binding, Event]:
        """Shared installed construction logic for both allocation policies."""
        if name == "report":
            render = self.installed["render"]
            rendered = await self.executor.invoke(
                "render-" + attempt, render.id, render.digest, computation["result"], self.context
            )
            if rendered["state"] != "completed":
                raise ValueError("selected count could not connect to the renderer")
            binding = self.installed["report"]
            if binding.input_schema["required"] != [self.report_input]:
                binding = self.install_report(self.report_input)
            dependencies = tuple(self.installed[n] for n in ("remote-words", "render"))
        else:
            threshold = int(computation["result"]["report"].split(": ")[1])
            binding = self.install_triage(threshold)
            dependencies = tuple(self.installed[n] for n in ("remote-words", "render", "report"))
        event = await formation.publish(binding.id, self.candidate(binding, dependencies))
        goal = self.opportunities.goal(name)
        reference = self.overlay.store.reference(
            "capability", self.config.owner, binding.subject.key
        )
        self.opportunities.select_target(goal.id, goal.digest, binding.id, reference)
        self.save_goals()
        return binding, event

    async def run_static(self, max_steps: int) -> dict[str, Any]:
        """Fixed report/check/triage/check control with ordinary admission and cache.

        No opportunity discovery, proposal exchange or adaptive allocation is called.
        Host target persistence is shared with the treatment's installed factories.
        """
        if not 1 <= max_steps <= min(self.config.max_steps, 16):
            raise ValueError("invalid document application step bound")
        history: list[dict[str, Any]] = []
        reason = "step_limit"
        async with asyncio.timeout(min(self.config.max_seconds, 120)):
            for _ in range(max_steps):
                sync = await synchronize(
                    self.config, self.identity, self.overlay.store, "verifier", page_size=4
                )
                if not sync["complete"]:
                    reason = "incomplete_observation"
                    break
                name = None
                candidate_exists = False
                needs_connection = False
                for target_name in ("report", "triage"):
                    goal = self.opportunities.goal(target_name)
                    page = await asyncio.to_thread(
                        self.overlay.store.record_page,
                        RecordQuery(
                            kinds=("capability",),
                            issuer=self.config.owner,
                            subject=goal.request.subject,
                        ),
                        limit=1,
                    )
                    if page.items:
                        decision = await self.overlay.qualify(goal.request)
                        if decision.outcome == "ACCEPT":
                            continue
                        if {
                            "known_revocation",
                            "dependency_rejected",
                            "in_scope_counterexample",
                        } & set(decision.reasons):
                            return {
                                "reason": "requires_repair",
                                "history": history,
                                "pid": os.getpid(),
                            }
                        needs_connection = "scope_mismatch" in decision.reasons
                    name, candidate_exists = target_name, bool(page.items)
                    break
                if name is None:
                    reason = "goals_satisfied"
                    break
                goal = self.opportunities.goal(name)
                if candidate_exists and not needs_connection:
                    if self.config.max_rechecks == 0:
                        reason = "checking_disabled"
                        break
                    attempt = "static-check-" + fingerprint(
                        [goal.contract_digest, goal.request.binding_digest]
                    )
                    invocation = await self.executor.invoke(
                        attempt,
                        goal.checker.id,
                        goal.checker.digest,
                        {
                            "name": name,
                            "attempt": attempt,
                            "binding_digest": goal.request.binding_digest,
                        },
                        self.context,
                    )
                    checked = invocation.get("result") or {}
                    history.append(
                        {
                            "kind": "verification",
                            "check_attempt": attempt,
                            "evidence": checked.get("evidence"),
                            "invocation": invocation,
                        }
                    )
                    if invocation["state"] != "completed" or not checked.get("evidence"):
                        reason = "check_not_completed"
                        break
                    if checked["evidence"]["verdict"] != "PASS":
                        reason = "check_not_passed"
                        break
                    continue
                if self.config.max_children == 0:
                    reason = "child_limit"
                    break
                builder = goal.builders[0]
                attempt = "static-form-" + fingerprint(
                    [goal.contract_digest, builder.digest, self.training_text]
                )
                async with AsyncExitStack() as stack:
                    try:
                        formation = await stack.enter_async_context(
                            FormationSession(
                                self.registry,
                                self.identity,
                                max_steps=min(8, self.config.max_children),
                                max_seconds=min(30, self.config.max_seconds),
                                minimum_remaining=max(
                                    self.executor.allowance.minimum_remaining,
                                    self.executor.allowance.quantity
                                    * self.allocation_policy.reserve_operations,
                                ),
                            )
                        )
                        invocation = await self.executor.invoke(
                            attempt,
                            builder.id,
                            builder.digest,
                            {self.report_input if name == "triage" else "text": self.training_text},
                            self.context,
                        )
                    except Conflict:
                        reason = "insufficient_allowance"
                        break
                    if invocation["state"] != "completed":
                        history.append(
                            {
                                "kind": "connection" if needs_connection else "formation",
                                "invocation": invocation,
                            }
                        )
                        reason = "formation_not_completed"
                        break
                    binding, event = await self.materialize(formation, name, invocation, attempt)
                    history.append(
                        {
                            "kind": "connection" if needs_connection else "formation",
                            "target": binding.id,
                            "formation": event.model_dump(mode="json"),
                            "invocation": invocation,
                        }
                    )
        return {"reason": reason, "history": history, "pid": os.getpid()}


def checker_binding() -> Binding:
    """Pin the installed adapter and its existing reference-check implementation."""
    source = callable_digest(AdaptiveDocuments.check_requested_candidate)
    return Binding(
        id="document-check",
        revision="1",
        issuer="verifier",
        registrar="verifier",
        subject=Subject(
            id="documents.checker",
            version="1",
            digest=fingerprint(
                {
                    "adapter": source,
                    "checker": callable_digest(DocumentService.check),
                }
            ),
        ),
        target=Target(
            kind="local",
            name="document-check",
            interface_digest=source,
            implementation_identity="installed",
        ),
        scope=Scope(
            task="document-check",
            input_contract="document-check.in.v1",
            output_contract="document-check.out.v1",
            environment=ENVIRONMENT,
        ),
        input_schema={
            "type": "object",
            "required": ["name", "attempt", "binding_digest"],
            "properties": {
                "name": {"enum": ["report", "triage", "remote-words"]},
                "attempt": {"type": "string", "minLength": 1, "maxLength": 160},
                "binding_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
        },
        output_schema={
            "type": "object",
            "oneOf": [
                {"required": ["evidence", "observed"]},
                {
                    "required": ["state", "reason"],
                    "properties": {
                        "state": {"const": "rejected"},
                        "reason": {"const": "target_changed"},
                    },
                },
            ],
        },
        callers=("receiver", "verifier", "producer"),
        verification_callers=("producer",),
        effects="read-only",
    )


def remote_checker_binding(config: Config) -> Binding:
    provider = checker_binding()
    endpoint = next(peer.url for peer in config.peers if peer.identity == "verifier")
    return provider.model_copy(
        update={
            "id": "remote-checker",
            "issuer": "receiver",
            "registrar": "receiver",
            "subject": Subject(
                id="documents.remote-checker",
                version="1",
                digest=fingerprint(
                    {
                        "provider": provider.model_dump(mode="json"),
                        "endpoint": endpoint,
                    }
                ),
            ),
            "target": Target(
                kind="a2a",
                name=provider.id,
                peer="verifier",
                endpoint=endpoint,
                interface_digest=provider.digest,
                implementation_identity="remote-unknown",
            ),
        }
    )


def configure_application(
    configs: dict[str, Config], training_text: str, *, connection_mismatch: bool = False
) -> None:
    """Operator setup only: install primitives/templates and export public contracts."""
    if not training_text.strip() or len(training_text) > 4000:
        raise ValueError("invalid calibration document")
    services = {name: DocumentService(config) for name, config in configs.items()}
    try:
        receiver = services["receiver"]
        remote = receiver.install_remote(services["producer"].installed["words"])
        receiver.publish(remote, (services["producer"].installed["words"],), imported=True)
        report = receiver.install_report()
        initial_report = report
        if connection_mismatch:
            # An operator-installed v1 candidate cannot satisfy a v2 input request.
            # Its publication grants no PASS or formation receipt. Both policies
            # receive the same installed adapter and pay for its later formation.
            receiver.publish(report, (remote, receiver.installed["render"]))
            report = receiver.install_report("document")
        checker = binding_ref(remote_checker_binding(configs["receiver"]))
        scopes = {
            "report": report.scope,
            "triage": Scope(
                task="triage",
                input_contract="triage.in.v1",
                output_contract="triage.out.v1",
                environment=ENVIRONMENT,
            ),
        }
        goals = tuple(
            Goal(
                id=name,
                revision="1",
                request=UseRequest(
                    receiver="receiver",
                    capability_issuer="receiver",
                    scope=scopes[name],
                    semantic_fit="confirmed",
                    subject=initial_report.subject
                    if name == "report"
                    else Subject(
                        id="documents.triage",
                        version="pending",
                        digest=fingerprint({"intent": "triage"}),
                    ),
                    binding_digest=initial_report.digest
                    if name == "report"
                    else fingerprint({"intent": "triage-binding"}),
                ),
                checker=checker,
                checker_arguments={
                    "name": "remote-words",
                    "attempt": "readiness",
                    "binding_digest": remote.digest,
                },
                builders=(binding_ref(remote if name == "report" else report), checker),
                peers=("producer", "verifier"),
            )
            for name in ("report", "triage")
        )
        public = [ProposalContract.from_goal(goal).model_dump(mode="json") for goal in goals]
        for name, config in configs.items():
            write_json(
                config.private_key.parent / "application.json",
                {
                    "training_text": training_text,
                    "report_input": "document" if connection_mismatch else "text",
                    "contracts": public,
                    **(
                        {"goals": [goal.model_dump(mode="json") for goal in goals]}
                        if name == "receiver"
                        else {}
                    ),
                },
            )
    finally:
        for service in services.values():
            service.overlay.store.close()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, required=True)
    args = parser.parse_args()
    config = load_config(args.config)
    service = AdaptiveDocuments(config)
    try:
        uvicorn.run(
            application(config, service.handle),
            host="127.0.0.1",
            port=urlsplit(config.url).port,
            log_level="warning",
        )
    finally:
        service.overlay.store.close()


if __name__ == "__main__":
    main()
