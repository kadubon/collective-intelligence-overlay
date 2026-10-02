"""Installed bounded tabular factories for the local-model experiment.

The model supplies parameters, never code, permissions or checker inputs. MAF
executes the fixed composition; Registry/Executor retain admission and receipts.
The independent evaluator is loaded only in the configured verifier process.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import time
from datetime import timedelta
from decimal import ROUND_HALF_EVEN, Decimal
from pathlib import Path
from typing import Any, Literal

from agent_framework import Message, WorkflowBuilder, WorkflowContext
from agent_framework import executor as maf_executor
from pydantic import BaseModel, ConfigDict, Field

from collective_intelligence_overlay.adapters.a2a import send, synchronize
from collective_intelligence_overlay.allocation import AllocationPolicy, allocate
from collective_intelligence_overlay.application import ApplicationHost
from collective_intelligence_overlay.bindings import (
    Binding,
    ExecutionContext,
    Target,
    active_invocation,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.blocking import run_blocking
from collective_intelligence_overlay.lineage import FormationSession
from collective_intelligence_overlay.models import (
    BindingRef,
    Capability,
    Cost,
    Event,
    Evidence,
    FormationInput,
    Opportunity,
    Proposal,
    Scope,
    Subject,
    UseRequest,
    Verdict,
    now,
)
from collective_intelligence_overlay.opportunities import Goal, ProposalDraft, ProposalDrafts
from collective_intelligence_overlay.proposal_exchange import (
    ProposalContract,
    ProposalExchange,
    collect,
)
from collective_intelligence_overlay.queries import RecordQuery

ENVIRONMENT = {"tabular": "1"}
FACTORY = "collective_intelligence_overlay.starter.tabular:configure"
NAMES = ("numeric", "status", "aggregate")


class NumericPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    decimal_separator: Literal[".", ","]
    thousands_separator: Literal["", ".", ",", " "]
    affix: str = Field(max_length=8)
    divisor: Literal[1, 100, 1000]


class StatusPlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    trim: bool
    casefold: bool
    accepted: list[str] = Field(min_length=1, max_length=4)


class AggregatePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    operation: Literal["sum", "mean", "count"]
    group_casefold: bool


PLANS: dict[str, type[BaseModel]] = {
    "numeric": NumericPlan,
    "status": StatusPlan,
    "aggregate": AggregatePlan,
}
ROWS: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["rows"],
    "properties": {
        "rows": {
            "type": "array",
            "minItems": 1,
            "maxItems": 24,
            "items": {
                "type": "object",
                "required": ["amount", "status", "group"],
                "additionalProperties": False,
                "properties": {
                    key: {"type": "string", "maxLength": 64}
                    for key in ("amount", "status", "group")
                },
            },
        }
    },
}
OUTPUTS: dict[str, dict[str, Any]] = {
    "numeric": {
        "type": "object",
        "required": ["values"],
        "additionalProperties": False,
        "properties": {"values": {"type": "array", "items": {"type": "string"}}},
    },
    "status": {
        "type": "object",
        "required": ["selected"],
        "additionalProperties": False,
        "properties": {"selected": {"type": "array", "items": {"type": "boolean"}}},
    },
    "aggregate": {
        "type": "object",
        "required": ["totals"],
        "additionalProperties": False,
        "properties": {"totals": {"type": "object", "additionalProperties": {"type": "string"}}},
    },
}


def normalize(rows: list[dict[str, str]], plan: NumericPlan) -> dict[str, Any]:
    values = []
    for row in rows:
        text = row["amount"].strip()
        if plan.affix:
            text = text.replace(plan.affix, "").strip()
        if plan.thousands_separator:
            if plan.thousands_separator == plan.decimal_separator:
                raise ValueError("decimal and thousands separators must differ")
            text = text.replace(plan.thousands_separator, "")
        text = text.replace(plan.decimal_separator, ".")
        value = Decimal(text) / plan.divisor
        if not value.is_finite() or abs(value) > 10**9:
            raise ValueError("numeric primitive finite magnitude bound")
        values.append(str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN)))
    return {"values": values}


def select_status(rows: list[dict[str, str]], plan: StatusPlan) -> dict[str, Any]:
    selected = []
    for row in rows:
        value = row["status"]
        if plan.trim:
            value = value.strip()
        if plan.casefold:
            value = value.casefold()
        selected.append(value in plan.accepted)
    return {"selected": selected}


def aggregate(
    rows: list[dict[str, str]], values: list[str], selected: list[bool], plan: AggregatePlan
) -> dict[str, Any]:
    grouped: dict[str, list[Decimal]] = {}
    for row, amount, keep in zip(rows, values, selected, strict=True):
        if keep:
            group = row["group"].casefold() if plan.group_casefold else row["group"]
            grouped.setdefault(group, []).append(Decimal(amount))
    totals = {}
    for group, amounts in grouped.items():
        value = Decimal(len(amounts)) if plan.operation == "count" else sum(amounts, Decimal(0))
        if plan.operation == "mean":
            value /= len(amounts)
        totals[group] = str(value.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))
    return {"totals": dict(sorted(totals.items()))}


def ref(binding: Binding) -> BindingRef:
    return BindingRef(issuer=binding.issuer, id=binding.id, digest=binding.digest)


class TabularApplication:
    def __init__(self, host: ApplicationHost) -> None:
        self.host, self.config = host, host.config
        self.registry, self.executor = host.registry, host.executor
        self.store, self.identity = host.overlay.store, host.identity
        self.artifacts = host.config.artifacts()
        path = host.config.application_settings
        if path is None or path.stat().st_size > 262144:
            raise ValueError("bounded operator settings required")
        self.settings = json.loads(path.read_text(encoding="utf-8"))
        self.installed: dict[str, Binding] = {}
        self.manifests: dict[str, dict[str, Any]] = {}
        self.lock = asyncio.Lock()
        self.context = ExecutionContext(caller=self.config.owner, environment=ENVIRONMENT)
        self.charged = self.attempts = 0
        self.history: list[dict[str, Any]] = []
        self.evaluator: Any = None
        if self.config.owner == "verifier":
            spec = importlib.util.spec_from_file_location(
                "private_tabular_evaluator", self.settings["evaluator"]
            )
            if spec is None or spec.loader is None:
                raise ValueError("operator-installed evaluator unavailable")
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.evaluator = module.Evaluator(self.settings["evaluation"])
            self.checker = self.install(
                "checker",
                self.check,
                {},
                {
                    "type": "object",
                    "required": ["name", "binding_digest", "attempt"],
                    "additionalProperties": False,
                    "properties": {
                        key: {"type": "string", "maxLength": 160}
                        for key in ("name", "binding_digest", "attempt")
                    },
                },
                {"type": "object"},
                publish=True,
            )
        if self.config.owner == "receiver":
            self.checker = Binding.model_validate(self.settings["checker"])
            self.registry.register_a2a(self.checker, lambda _: True, self.config, self.identity)
            self.installed["checker"] = self.checker
            self.publish(self.checker, imported=True)
            goals = []
            for name in NAMES:

                async def build(arguments: dict[str, Any], kind: str = name) -> dict[str, Any]:
                    plan = PLANS[kind].model_validate(arguments["plan"])
                    if kind == "numeric":
                        result = normalize(
                            self.settings["practice"], NumericPlan.model_validate(plan)
                        )
                    elif kind == "status":
                        result = select_status(
                            self.settings["practice"], StatusPlan.model_validate(plan)
                        )
                    else:
                        result = {"validated_parameters": True}
                    return {"plan": plan.model_dump(mode="json"), "practice_result": result}

                builder = self.install(
                    "build-" + name,
                    build,
                    {},
                    {
                        "type": "object",
                        "required": ["plan"],
                        "additionalProperties": False,
                        "properties": {"plan": PLANS[name].model_json_schema()},
                    },
                    {"type": "object"},
                    publish=True,
                )
                # An unverified placeholder fixes the goal's exact scope. It is
                # never a usable fallback and is not published as a candidate.
                target = self.install(name, self.unformed, {"unformed": True}, ROWS, OUTPUTS[name])
                goals.append(
                    Goal(
                        id=name,
                        revision="1",
                        request=UseRequest(
                            receiver="receiver",
                            capability_issuer="receiver",
                            subject=target.subject,
                            binding_digest=target.digest,
                            scope=target.scope,
                            semantic_fit="confirmed",
                        ),
                        checker=ref(self.checker),
                        checker_arguments={
                            "name": name,
                            "binding_digest": target.digest,
                            "attempt": "readiness",
                        },
                        builders=(ref(builder), ref(self.checker)),
                        peers=("producer",),
                        lifetime_seconds=900,
                    )
                )
            host.register_goals(tuple(goals))
        if self.config.owner == "producer":
            contracts = tuple(
                ProposalContract.model_validate(item) for item in self.settings["contracts"]
            )
            host.proposal_exchange = ProposalExchange(
                self.store,
                self.identity,
                contracts,
                self.propose,
                seconds=30,
                allow_target_updates=True,
                allowance_unit="work",
                allowance_quantity=Decimal(1),
                max_concurrent=1,
            )

    async def unformed(self, _: dict[str, Any]) -> dict[str, Any]:
        raise ValueError("unformed target has no callable candidate")

    def install(
        self,
        name: str,
        operation: Any,
        parameters: dict[str, Any],
        input_schema: dict[str, Any],
        output_schema: dict[str, Any],
        *,
        publish: bool = False,
        components: tuple[str, ...] = (),
    ) -> Binding:
        manifest = {
            "application": "tabular.v1",
            "name": name,
            "parameters": parameters,
            "source": callable_digest(operation),
            "components": components,
            "contract_digest": fingerprint(self.settings["public_contract"]),
        }
        artifact = self.artifacts.put(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        )
        source = callable_digest(operation)
        binding = Binding(
            id=name,
            revision=artifact[:24],
            issuer=self.config.owner,
            registrar=self.config.owner,
            subject=Subject(id="tabular." + name, version=artifact[:24], digest=artifact),
            scope=Scope(
                task=name,
                input_contract="tabular."
                + name
                + ".in."
                + fingerprint(self.settings["public_contract"])[:16],
                output_contract="tabular." + name + ".out.v1",
                environment=ENVIRONMENT,
            ),
            target=Target(
                kind="local",
                name=name,
                interface_digest=source,
                implementation_identity="installed",
            ),
            input_schema=input_schema,
            output_schema=output_schema,
            callers=("producer", "receiver", "verifier"),
            verification_callers=("producer", "receiver", "verifier"),
            effects="read-only",
            components=components,
        )
        self.registry.register_local(binding, operation, lambda _: True)
        self.installed[name], self.manifests[name] = binding, manifest
        if publish:
            self.publish(binding)
        return binding

    def candidate(self, binding: Binding, *, imported: bool = False) -> Capability:
        formed = binding.id in NAMES and "unformed" not in self.manifests.get(binding.id, {}).get(
            "parameters", {}
        )
        dependencies = (
            tuple(self.installed[n] for n in ("numeric", "status"))
            if binding.id == "aggregate"
            and "unformed" not in self.manifests.get(binding.id, {}).get("parameters", {})
            else ()
        )
        return Capability(
            schema_version="3" if formed else "2",
            issuer="receiver" if imported else self.config.owner,
            subject=binding.subject,
            binding_digest=binding.digest,
            scope=binding.scope,
            entrypoint=binding.id,
            claim="parameter-validation"
            if binding.id.startswith("build-")
            else "checker-contract"
            if binding.id == "checker"
            else "tabular-contract",
            license="Apache-2.0",
            provenance="installed finite primitives; synthetic data; model parameters only",
            classification="imported" if imported else "declared-new",
            dependencies=tuple(b.subject for b in dependencies),
            dependency_issuers=tuple(b.issuer for b in dependencies),
            formation_inputs=(
                FormationInput(
                    subject=self.installed["build-" + binding.id].subject,
                    issuer="receiver",
                    binding_digest=self.installed["build-" + binding.id].digest,
                ),
            )
            if formed
            else (),
            expires_at=now() + timedelta(hours=1),
        )

    def publish(self, binding: Binding, *, imported: bool = False) -> None:
        self.host.publish_candidate(binding, self.candidate(binding, imported=imported))

    async def child(self, name: str, rows: list[dict[str, str]]) -> dict[str, Any]:
        binding = self.installed[name]
        parent = active_invocation.get()
        if parent is None:
            raise ValueError("child requires a durable host operation identity")
        value = await self.executor.invoke(
            "child-" + fingerprint([parent, name]),
            name,
            binding.digest,
            {"rows": rows},
            self.context,
        )
        if value["state"] != "completed":
            raise ValueError("prerequisite candidate was not qualified and completed")
        return dict(value["result"])

    async def compose(self, rows: list[dict[str, str]], plan: AggregatePlan) -> dict[str, Any]:
        @maf_executor(id="numeric")
        async def numbers(data: dict[str, Any], ctx: WorkflowContext[dict[str, Any]]) -> None:
            await ctx.send_message({**data, **await self.child("numeric", data["rows"])})

        @maf_executor(id="status")
        async def statuses(data: dict[str, Any], ctx: WorkflowContext[dict[str, Any]]) -> None:
            await ctx.send_message({**data, **await self.child("status", data["rows"])})

        @maf_executor(id="aggregate")
        async def totals(
            data: dict[str, Any], ctx: WorkflowContext[dict[str, Any], dict[str, Any]]
        ) -> None:
            await ctx.yield_output(aggregate(data["rows"], data["values"], data["selected"], plan))

        workflow = (
            WorkflowBuilder(start_executor=numbers, max_iterations=4)
            .add_edge(numbers, statuses)
            .add_edge(statuses, totals)
            .build()
        )
        outputs = (await workflow.run({"rows": rows})).get_outputs()
        if len(outputs) != 1:
            raise ValueError("composition must return one result")
        return dict(outputs[0])

    async def propose(self, opportunity: Opportunity) -> ProposalDrafts:
        name = opportunity.goal_id
        contract = next(
            ProposalContract.model_validate(c)
            for c in self.settings["contracts"]
            if c["id"] == name
        )
        if opportunity.work_kind == "verification":
            description = await send(
                self.config, self.identity, "receiver", {"operation": "app.describe", "name": name}
            )
            return ProposalDrafts(
                alternatives=(
                    ProposalDraft(
                        builder=contract.checker,
                        alternative="independent-check",
                        arguments={
                            "name": name,
                            "binding_digest": description["binding"]["digest"]
                            if "digest" in description["binding"]
                            else Binding.model_validate(description["binding"]).digest,
                            "attempt": "check-" + opportunity.id,
                        },
                    ),
                )
            )
        if opportunity.work_kind not in {"formation", "repair", "connection"}:
            return ProposalDrafts(alternatives=())
        # The LLM has no tools and sees no evaluator module, hidden inputs or seed.
        from collective_intelligence_overlay.adapters.inference_observer import (
            RawInferenceTransport,
            write_new,
        )
        from collective_intelligence_overlay.adapters.ollama import local_ollama_client

        maximum = self.settings["model"]["token_budget"]
        reserved = 4096 + 512
        if (
            self.charged + reserved > maximum
            or self.attempts >= self.settings["model"]["max_requests"]
        ):
            return ProposalDrafts(alternatives=())
        index = self.attempts
        self.attempts += 1
        folder = Path(self.settings["model"]["output"]) / f"attempt-{index:03}"
        prompt = (
            "Choose parameters for the installed "
            + name
            + " primitive. Return only the typed JSON. "
            "This is a proposal; it grants no authority. Contract:\n"
            + self.settings["public_contract"][name]
            + "\nPublic practice rows:\n"
            + json.dumps(self.settings["practice"])
        )
        options = {
            "temperature": 0.2,
            "top_k": 64,
            "top_p": 0.95,
            "num_ctx": 4096,
            "num_predict": 512,
            "draft_num_predict": 0,
            "seed": self.settings["model"]["seed"] + NAMES.index(name),
        }
        observer = RawInferenceTransport(
            folder,
            identity={
                **self.settings["model"]["identity"],
                "peer": "producer",
                "attempt": str(index),
                "goal": name,
            },
            requested={"native_options": options, "think": False, "keep_alive": "5m"},
            provenance={
                **self.settings["model"]["provenance"],
                "prompt_digest": fingerprint(prompt),
                "schema_digest": fingerprint(PLANS[name].model_json_schema()),
                "opportunity": opportunity.id,
            },
            token_reservation=reserved,
            real_model=True,
        )
        parsed, error = None, None
        before = time.perf_counter()
        try:
            import httpx

            async with httpx.AsyncClient(
                base_url=self.settings["model"]["host"], timeout=5, trust_env=False
            ) as http:
                tags = (await http.get("/api/tags")).json()
                actual = next(m for m in tags["models"] if m["name"] == "gemma4:e4b")
                if actual["digest"] != self.settings["model"]["provenance"]["model_digest"]:
                    raise ValueError("pinned model changed")
            async with local_ollama_client(
                self.settings["model"]["host"], model="gemma4:e4b", seconds=25, transport=observer
            ) as client:
                response = await client.get_response(
                    [Message(role="user", contents=[prompt])],
                    options={  # type: ignore[call-overload]
                        "options": options,
                        "think": False,
                        "keep_alive": "5m",
                        "response_format": PLANS[name],
                    },
                )
                parsed = PLANS[name].model_validate_json(response.text)
        except Exception as exc:
            error = type(exc).__name__
        finally:
            await observer.aclose()
            observation = json.loads((folder / "observation.json").read_text())
            self.charged += observation["budget_charge"]
            write_new(
                folder / "host-validation.json",
                {
                    "goal": name,
                    "opportunity": opportunity.id,
                    "parsed_plan": parsed.model_dump(mode="json") if parsed else None,
                    "error_type": error,
                    "aggregate_budget_charge": self.charged,
                },
            )
            event = Event(
                issuer="producer",
                subject=opportunity.subject,
                action="proposal" if parsed else "failure",
                task_id=opportunity.id,
                attempt_id="model-" + fingerprint([self.settings["model"]["identity"], index]),
                correlation_id=opportunity.id,
                costs=(
                    Cost(
                        category="formation" if parsed else "failure",
                        status="measured",
                        unit="wall_seconds",
                        quantity=Decimal(str(round(time.perf_counter() - before, 9))),
                    ),
                    Cost(
                        category="formation",
                        status="measured"
                        if observation["tokens_measured"] is not None
                        else "unavailable",
                        unit="model_tokens",
                        quantity=Decimal(observation["tokens_measured"])
                        if observation["tokens_measured"] is not None
                        else None,
                    ),
                ),
            )
            await run_blocking(self.store.put, self.identity.sign(event))
        if parsed is None:
            return ProposalDrafts(alternatives=())
        return ProposalDrafts(
            alternatives=(
                ProposalDraft(
                    builder=contract.builders[0],
                    alternative="gemma-parameters",
                    arguments={"plan": parsed.model_dump(mode="json")},
                ),
            )
        )

    async def check(self, arguments: dict[str, Any]) -> dict[str, Any]:
        if self.evaluator is None:
            raise ValueError("checking belongs to the separate verifier")
        name, attempt = arguments["name"], arguments["attempt"]
        evidence_id = "checked-" + fingerprint(attempt)
        saved = self.store.record_page(
            RecordQuery(kinds=("evidence",), issuer="verifier", record_id=evidence_id), limit=1
        )
        if saved.items:
            return {"evidence": saved.items[0].model_dump(mode="json")}
        await synchronize(self.config, self.identity, self.store, "receiver", page_size=128)
        description = await send(
            self.config, self.identity, "receiver", {"operation": "app.describe", "name": name}
        )
        binding = Binding.model_validate(description["binding"])
        if binding.digest != arguments["binding_digest"]:
            return {"state": "rejected", "reason": "target_changed"}
        transcripts = []
        for index, case in enumerate(self.evaluator.cases("validation", name)):
            actual = await send(
                self.config,
                self.identity,
                "receiver",
                {
                    "operation": "invoke",
                    "purpose": "verification",
                    "invocation_id": "probe-" + fingerprint([attempt, index]),
                    "binding_id": name,
                    "binding_digest": binding.digest,
                    "arguments": {"rows": case["rows"]},
                },
            )
            transcripts.append({"case": case, "observed": actual})
        verdict = (
            "UNKNOWN"
            if any(t["observed"].get("state") != "completed" for t in transcripts)
            else (
                "PASS"
                if all(t["observed"]["result"] == t["case"]["expected"] for t in transcripts)
                else "FAIL"
            )
        )
        artifact = self.artifacts.put(
            json.dumps(
                {"binding_digest": binding.digest, "transcripts": transcripts}, sort_keys=True
            ).encode()
        )
        evidence = Evidence(
            schema_version="2",
            id=evidence_id,
            issuer="verifier",
            subject=binding.subject,
            binding_digest=binding.digest,
            claim="tabular-contract",
            scope=binding.scope,
            receivers=("receiver",),
            verdict=Verdict(verdict),
            method="reference-check",
            verifier_version=self.settings["evaluation"]["checker_digest"][:32],
            artifact_digest=artifact,
            expires_at=now() + timedelta(hours=1),
        )
        self.store.put(self.identity.sign(evidence))
        return {"evidence": evidence.model_dump(mode="json"), "checks": len(transcripts)}

    async def run(self, maximum: int, _: int) -> dict[str, Any]:
        assert self.host.opportunities is not None and self.host.steps is not None
        if self.lock.locked():
            return {"reason": "already_running"}
        async with self.lock:
            seen = set()
            static_cursor = 0
            reason = "step_limit"
            async with asyncio.timeout(300):
                for _index in range(min(maximum, 12)):
                    await synchronize(
                        self.config, self.identity, self.store, "verifier", page_size=128
                    )
                    static = self.settings["mode"] == "static"
                    if static and static_cursor == len(NAMES):
                        reason = "goals_satisfied"
                        break
                    # Static uses only the current item in its fixed local plan.
                    # The public observation API still creates signed references
                    # needed by Steps and ordinary admission; it does not expose
                    # the other goals' adaptive backlog to the static allocator.
                    discovered = await self.host.opportunities.discover(
                        max_candidates=1 if static else 3,
                        start=static_cursor if static else 0,
                    )
                    if static and discovered.satisfied == 1:
                        static_cursor += 1
                        continue
                    if not static and discovered.satisfied == 3:
                        reason = "goals_satisfied"
                        break
                    if not discovered.opportunities:
                        reason = "no_progress"
                        break
                    allocation = await allocate(
                        self.host.opportunities,
                        self.context,
                        discovered.opportunities,
                        AllocationPolicy(
                            mode=self.settings["mode"],
                            minimum_samples=1,
                            verification_threshold=1,
                            connection_threshold=1,
                            cooldown_seconds=0,
                        ),
                        self.host.steps.last_allocation(),
                    )
                    by_id = {o.id: o for o in discovered.opportunities}
                    pending = [by_id[key] for key in allocation.ordered if key not in seen]
                    if not pending:
                        reason = "no_progress"
                        break
                    opportunity = pending[0]
                    seen.add(opportunity.id)
                    goal = self.host.opportunities.goal(opportunity.goal_id)
                    replies = await collect(
                        self.config, self.store, self.identity, goal, opportunity.id
                    )
                    if opportunity.work_kind == "verification":
                        result = await self.host.steps.step(
                            opportunity.id, replies.replies, allocation=allocation
                        )
                        self.history.append(
                            {"kind": "verification", "step": result.model_dump(mode="json")}
                        )
                        continue
                    if opportunity.work_kind not in {"formation", "repair", "connection"}:
                        reason = "requires_" + opportunity.work_kind
                        break
                    async with FormationSession(
                        self.registry, self.identity, max_steps=8, max_seconds=30
                    ) as formation:
                        result = await self.host.steps.step(
                            opportunity.id, replies.replies, allocation=allocation
                        )
                        if result.invocation is None or result.invocation["state"] != "completed":
                            self.history.append(
                                {
                                    "kind": opportunity.work_kind,
                                    "step": result.model_dump(mode="json"),
                                }
                            )
                            continue
                        assert result.selection is not None
                        selected = self.store.resolve_reference(result.selection.proposal)
                        assert isinstance(selected, Proposal)
                        # Attach the original completed receipt to this formation.
                        await self.executor.invoke(
                            result.selection.invocation_id,
                            selected.builder.id,
                            selected.builder.digest,
                            selected.arguments,
                            self.context,
                        )
                        name = goal.id
                        plan = PLANS[name].model_validate(result.invocation["result"]["plan"])

                        async def execute(
                            args: dict[str, Any], kind: str = name, pinned: Any = plan
                        ) -> dict[str, Any]:
                            if kind == "numeric":
                                return normalize(args["rows"], NumericPlan.model_validate(pinned))
                            if kind == "status":
                                return select_status(
                                    args["rows"], StatusPlan.model_validate(pinned)
                                )
                            return await self.compose(
                                args["rows"], AggregatePlan.model_validate(pinned)
                            )

                        components = (
                            tuple(self.installed[n].digest for n in ("numeric", "status"))
                            if name == "aggregate"
                            else ()
                        )
                        if name == "aggregate":
                            # Reuse C1/C2 on different public inputs before C3
                            # publication. These actual receipts join its lineage.
                            parent_token = active_invocation.set(
                                fingerprint(["receiver", "formation", formation.id])
                            )
                            try:
                                await self.compose(
                                    self.settings["followup_practice"],
                                    AggregatePlan.model_validate(plan),
                                )
                            finally:
                                active_invocation.reset(parent_token)
                        binding = self.install(
                            name,
                            execute,
                            plan.model_dump(mode="json"),
                            ROWS,
                            OUTPUTS[name],
                            components=components,
                        )
                        event = await formation.publish(name, self.candidate(binding))
                        reference = self.store.reference(
                            "capability", "receiver", binding.subject.key
                        )
                        self.host.opportunities.select_target(goal.id, goal.digest, name, reference)
                        self.history.append(
                            {
                                "kind": opportunity.work_kind,
                                "step": result.model_dump(mode="json"),
                                "binding": binding.model_dump(mode="json"),
                                "formation": event.model_dump(mode="json"),
                            }
                        )
            return {"reason": reason, "history": self.history}

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        if data["operation"] == "app.describe":
            name = data["name"]
            return {
                "binding": self.installed[name].model_dump(mode="json"),
                "manifest": self.manifests.get(name),
            }
        if data["operation"] == "app.evaluate":
            if self.evaluator is None:
                raise ValueError("evaluation unavailable")
            result = []
            for index, case in enumerate(self.evaluator.cases("heldout", data["name"])):
                observed = await send(
                    self.config,
                    self.identity,
                    "receiver",
                    {
                        "operation": "app.use",
                        "name": data["name"],
                        "invocation_id": "heldout-" + fingerprint([data["name"], index]),
                        "rows": case["rows"],
                    },
                )
                result.append(
                    {
                        "case": case,
                        "observed": observed,
                        "passed": observed.get("state") == "completed"
                        and observed.get("result") == case["expected"],
                    }
                )
            return {"trials": result}
        if data["operation"] == "app.use":
            name = data["name"]
            binding = self.installed[name]
            return await self.executor.invoke(
                data["invocation_id"], name, binding.digest, {"rows": data["rows"]}, self.context
            )
        if data["operation"] == "app.calibration":
            # A public black-box test of the evaluator's exact comparison, with
            # no hidden dataset or answer sent to a proposer/model.
            if self.evaluator is None:
                raise ValueError("not a checker")
            return {
                "positive": self.evaluator.compare({"values": ["1.00"]}, {"values": ["1.00"]}),
                "negative": self.evaluator.compare({"values": ["2.00"]}, {"values": ["1.00"]}),
            }
        raise ValueError("unsupported tabular operation")


def configure(host: ApplicationHost) -> None:
    app = TabularApplication(host)
    readers = tuple({host.config.owner, *(p.identity for p in host.config.peers)})
    host.register_operation("app.describe", app.handle, callers=readers)
    if host.config.owner == "receiver":
        host.register_operation("app.use", app.handle, callers=("receiver", "verifier"))
        host.register_goal_runner(app.run)
    elif host.config.owner == "verifier":
        host.register_operation("app.evaluate", app.handle, callers=("verifier",))
        host.register_operation("app.calibration", app.handle, callers=("producer",))
