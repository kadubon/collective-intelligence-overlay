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
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import uvicorn
from document_application import ENVIRONMENT, DocumentService

from collective_intelligence_overlay.adapters.a2a import application, send, synchronize
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
    Opportunity,
    Proposal,
    Scope,
    Subject,
    UseRequest,
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
        self.contracts = tuple(ProposalContract.model_validate(item) for item in data["contracts"])
        if config.owner == "verifier":
            self.checker_binding = checker_binding()
            self.registry.register_local(
                self.checker_binding,
                self.check_requested_candidate,
                lambda args: args["name"] in {"report", "triage"},
            )
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
                if page.items:
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
        if opportunity.work_kind != "formation":
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
                    arguments={"text": text},
                    alternative=self.config.owner + "-calibration",
                ),
            )
        )

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
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
            return await self.check_requested_candidate(prepared.arguments)
        if data.get("operation") == "adaptive-run":
            if caller != self.config.owner or caller != "receiver":
                raise ValueError("only the receiver owner may start its finite application")
            if self._run_lock.locked():
                return {"reason": "already_running", "history": [], "pid": os.getpid()}
            async with self._run_lock:
                return await self.run(int(data.get("max_steps", 8)))
        return await super().handle(caller, data)

    async def check_requested_candidate(self, data: dict[str, Any]) -> dict[str, Any]:
        name = str(data["name"])
        if name not in {"report", "triage"}:
            raise ValueError("checker contract does not cover this target")
        result = await self.check(
            {
                "provider": "receiver",
                "name": name,
                "attempt": str(data["attempt"]),
                "arguments": {"text": "independent\tvalidation 文書\nwith separate contents"},
            }
        )
        if result["evidence"]["binding_digest"] != data["binding_digest"]:
            raise ValueError("checked candidate changed during the request")
        return result

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
                pending = [item for item in discovery.opportunities if item.id not in seen]
                # Fixed domain rule: check an existing candidate before forming
                # another. This is separate from the core adaptive allocator.
                pending.sort(key=lambda item: item.work_kind != "verification")
                if not pending:
                    reason = "no_progress"
                    break
                observation = pending[0]
                seen.add(observation.id)
                goal = self.opportunities.goal(observation.goal_id)
                if observation.work_kind == "verification":
                    if self.config.max_rechecks == 0:
                        reason = "checking_disabled"
                        break
                    checked = await send(
                        self.config,
                        self.identity,
                        "verifier",
                        {
                            "operation": "request-document-check",
                            "name": goal.id,
                            "attempt": "check-" + observation.id,
                            "checker_digest": goal.checker.digest,
                            "binding_digest": goal.request.binding_digest,
                        },
                    )
                    history.append(
                        {
                            "opportunity": observation.id,
                            "kind": "verification",
                            "evidence": checked["evidence"],
                        }
                    )
                    continue
                if observation.work_kind != "formation":
                    reason = "requires_" + observation.work_kind
                    break
                replies = await collect(
                    self.config, self.overlay.store, self.identity, goal, observation.id
                )
                if not replies.replies:
                    reason = "proposers_unavailable"
                    break
                if self.config.max_children == 0:
                    reason = "child_limit"
                    break
                async with FormationSession(
                    self.registry,
                    self.identity,
                    max_steps=min(8, self.config.max_children),
                    max_seconds=min(30, self.config.max_seconds),
                ) as formation:
                    result = await self.steps.step(observation.id, replies.replies)
                    if result.invocation is None or result.invocation["state"] != "completed":
                        history.append(
                            {"kind": "formation", "step": result.model_dump(mode="json")}
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
                    if goal.id == "report":
                        render = self.installed["render"]
                        rendered = await self.executor.invoke(
                            "render-" + observation.id,
                            render.id,
                            render.digest,
                            computation["result"],
                            self.context,
                        )
                        if rendered["state"] != "completed":
                            raise ValueError("selected count could not connect to the renderer")
                        binding = self.installed["report"]
                        dependencies = tuple(self.installed[n] for n in ("remote-words", "render"))
                    else:
                        threshold = int(computation["result"]["report"].split(": ")[1])
                        binding = self.install_triage(threshold)
                        dependencies = tuple(
                            self.installed[n] for n in ("remote-words", "render", "report")
                        )
                    event = await formation.publish(
                        binding.id, self.candidate(binding, dependencies)
                    )
                reference = self.overlay.store.reference(
                    "capability", self.config.owner, binding.subject.key
                )
                self.opportunities.select_target(goal.id, goal.digest, binding.id, reference)
                self.save_goals()
                history.append(
                    {
                        "opportunity": observation.id,
                        "kind": "formation",
                        "target": binding.id,
                        "step": result.model_dump(mode="json"),
                        "formation": event.model_dump(mode="json"),
                        "proposers": [caller for caller, _ in replies.replies],
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
                "name": {"enum": ["report", "triage"]},
                "attempt": {"type": "string", "minLength": 1, "maxLength": 160},
                "binding_digest": {"type": "string", "pattern": "^[a-f0-9]{64}$"},
            },
        },
        output_schema={"type": "object", "required": ["evidence", "observed"]},
        callers=("receiver", "verifier"),
        effects="read-only",
    )


def configure_application(configs: dict[str, Config], training_text: str) -> None:
    """Operator setup only: install primitives/templates and export public contracts."""
    if not training_text.strip() or len(training_text) > 4000:
        raise ValueError("invalid calibration document")
    services = {name: DocumentService(config) for name, config in configs.items()}
    try:
        receiver = services["receiver"]
        remote = receiver.install_remote(services["producer"].installed["words"])
        receiver.publish(remote, (services["producer"].installed["words"],), imported=True)
        report = receiver.install_report()
        checker = binding_ref(checker_binding())
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
                    subject=report.subject
                    if name == "report"
                    else Subject(
                        id="documents.triage",
                        version="pending",
                        digest=fingerprint({"intent": "triage"}),
                    ),
                    binding_digest=report.digest
                    if name == "report"
                    else fingerprint({"intent": "triage-binding"}),
                ),
                checker=checker,
                builders=(binding_ref(remote if name == "report" else report),),
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
