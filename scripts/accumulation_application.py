"""Operator-installed source-only application over the existing three-owner host.

The model sees one public problem and a finite explicit cognitive view. All
generated procedures are data for the pinned SQLite/numeric factory. The separate
verifier alone loads expected cases. Nothing here is a new runtime or executor.
"""

import base64
import hashlib
import json
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Literal

import httpx
from accumulation_primitives import ENVIRONMENT, Problem, Solution, factory
from accumulation_stock import CognitiveView, Skill, Snapshot, ViewSkill, prompt, retrieve
from agent_framework import Message
from check_gemma_transport import persist_originals, validate_wire
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.adapters.inference_observer import (
    RawInferenceTransport,
    write_new,
)
from collective_intelligence_overlay.application import ApplicationHost
from collective_intelligence_overlay.bindings import (
    ArtifactSpec,
    Binding,
    ExecutionContext,
    Target,
    callable_digest,
    fingerprint,
)
from collective_intelligence_overlay.invocations import Executor, Reservation
from collective_intelligence_overlay.lineage import FormationSession
from collective_intelligence_overlay.models import (
    BindingRef,
    Capability,
    Cost,
    Event,
    Evidence,
    FormationInput,
    Scope,
    Subject,
    UseRequest,
    now,
)
from collective_intelligence_overlay.opportunities import Goal
from collective_intelligence_overlay.storage import projection_digest

MODEL = "gemma4:e4b"
DIGEST = "dc35e8d9c6061baa6f0fa870975ab6932e2542b579b13ea0f199fa4bb7300c9c"
FACTORY = "accumulation_application:configure"


class ModelDraft(BaseModel):
    """All fields are required on the wire; defaults cannot stand in for discovery."""

    model_config = ConfigDict(extra="forbid")
    explanation: str = Field(max_length=800)
    family: Literal["sql", "calibration", "composition"]
    sql: str = Field(max_length=12000)
    coefficients: tuple[float, float, float]
    reduction: Literal["sum", "mean", "count"]
    calibration_order: Literal["calibrate-then-reduce", "reduce-then-calibrate", "not-applicable"]
    uses: tuple[str, ...] = Field(max_length=3)


class CalibrationDraft(ModelDraft):
    family: Literal["calibration"]
    sql: Literal[""]
    reduction: Literal["sum"]
    calibration_order: Literal["not-applicable"]


class AffineDraft(CalibrationDraft):
    coefficients: tuple[float, float, Literal[0]]


class SQLDraft(ModelDraft):
    family: Literal["sql"]
    coefficients: tuple[Literal[0], Literal[1], Literal[0]]
    calibration_order: Literal["not-applicable"]


class CompositionDraft(ModelDraft):
    family: Literal["composition"]
    calibration_order: Literal["calibrate-then-reduce", "reduce-then-calibrate"]


def wire_schema(family, difficulty):
    if family == "calibration" and difficulty == "low":
        return AffineDraft
    return {"sql": SQLDraft, "calibration": CalibrationDraft, "composition": CompositionDraft}[
        family
    ]


class AccumulationApplication:
    def __init__(self, host):
        self.host, self.config = host, host.config
        self.identity, self.store = host.identity, host.overlay.store
        self.registry, self.executor = host.registry, host.executor
        self.artifacts = self.config.artifacts()
        path = self.config.application_settings
        if path is None or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("bounded explicit operator settings required")
        self.settings = json.loads(path.read_bytes())
        if self.config.owner != "verifier" and "checks" in self.settings:
            raise ValueError("expected cases belong only to the separate verifier")
        if self.config.owner == "verifier" and "model" in self.settings:
            raise ValueError("verifier is not a model proposer")
        self.installed = {}
        self.pending = None
        self.context = ExecutionContext(
            caller=self.config.owner, purpose="verification", environment=ENVIRONMENT
        )
        self.builder = self.local("build-plan", self.build, "parameter-construction")
        if "model" in self.settings:
            self.proposer = self.local("model-propose", self.infer, "recorded-model-proposal")
            # The existing Executor has an operator-selected finite reservation.
            # A2A's public run operation supplies the longer SDK deadline.
            self.executor = Executor(
                self.registry,
                self.identity,
                Reservation(
                    seconds=min(300, self.settings["model"]["seconds"] + 10),
                    max_concurrent=1,
                    max_unresolved=self.config.max_unresolved,
                ),
            )
            host.executor = self.executor

    def candidate(self, binding, claim, *, formed=False, imported=False):
        return Capability(
            schema_version="3" if formed else "2",
            issuer=self.config.owner,
            subject=binding.subject,
            binding_digest=binding.digest,
            scope=binding.scope,
            entrypoint=binding.id,
            claim=claim,
            license="Apache-2.0",
            provenance="installed bounded data factory; synthetic study, no independent PASS",
            classification="imported" if imported else "declared-new",
            formation_inputs=(
                FormationInput(
                    subject=self.builder.subject,
                    issuer=self.config.owner,
                    binding_digest=self.builder.digest,
                ),
            )
            if formed
            else (),
            expires_at=now() + timedelta(hours=6),
        )

    def local(self, name, operation, claim):
        source = callable_digest(operation)
        artifact = self.artifacts.put(json.dumps({"name": name, "source": source}).encode())
        binding = Binding(
            id=name,
            revision=artifact[:24],
            issuer=self.config.owner,
            registrar=self.config.owner,
            subject=Subject(id="study." + name, version=artifact[:24], digest=artifact),
            scope=Scope(
                task=name,
                input_contract=name + ".in.v1",
                output_contract=name + ".out.v1",
                environment=ENVIRONMENT,
            ),
            target=Target(
                kind="local",
                name=name,
                interface_digest=source,
                implementation_identity="installed",
            ),
            input_schema={"type": "object"},
            output_schema={"type": "object"},
            callers=(self.config.owner, "verifier")
            if self.config.owner != "verifier"
            else ("verifier",),
            verification_callers=(self.config.owner, "verifier")
            if self.config.owner != "verifier"
            else ("verifier",),
            effects="read-only",
        )
        self.registry.register_local(binding, operation, lambda _: True)
        self.host.publish_candidate(binding, self.candidate(binding, claim))
        self.installed[name] = binding
        return binding

    async def build(self, arguments):
        try:
            solution = Solution.model_validate(arguments["solution"])
        except ValidationError:
            return {"valid": False, "error_type": "ValidationError"}
        spec = ArtifactSpec(
            builder_id="study-plan",
            builder_version="1",
            builder_source=callable_digest(factory),
            parameters=solution.model_dump(mode="json"),
            environment=ENVIRONMENT,
        )
        return {
            "valid": True,
            "artifact_digest": spec.persist(self.artifacts),
            "solution": solution.model_dump(mode="json"),
        }

    def materialize(
        self, name, problem, solution, artifact_digest, *, publish=True, imported=False
    ):
        source = callable_digest(factory(solution.model_dump(mode="json")))
        problem_schema = Problem.model_json_schema()
        definitions = problem_schema.pop("$defs", {})
        binding = Binding(
            binding_schema="2",
            artifact_digest=artifact_digest,
            id=name,
            revision=artifact_digest[:24],
            issuer=self.config.owner,
            registrar=self.config.owner,
            subject=Subject(
                id="study." + name, version=artifact_digest[:24], digest=artifact_digest
            ),
            scope=Scope(
                task=problem.contract,
                input_contract="problem."
                + fingerprint(
                    [
                        problem.contract,
                        problem.revision,
                        problem.schema_digest,
                        problem.specification,
                    ]
                )[:24],
                output_contract="study-output.v1",
                environment=ENVIRONMENT,
            ),
            target=Target(
                kind="local",
                name=name,
                interface_digest=source,
                implementation_identity="installed",
            ),
            input_schema={
                "$defs": definitions,
                "type": "object",
                "required": ["problem"],
                "properties": {"problem": problem_schema},
                "additionalProperties": False,
            },
            output_schema={"type": "object"},
            callers=(self.config.owner, "verifier"),
            verification_callers=(self.config.owner, "verifier"),
            effects="read-only",
        )
        self.registry.register_artifact(
            binding,
            self.artifacts,
            factory,
            lambda args: (
                self.contract_key(Problem.model_validate(args["problem"]))
                == self.contract_key(problem)
            ),
            builder_id="study-plan",
            builder_version="1",
        )
        if publish:
            self.host.publish_candidate(
                binding, self.candidate(binding, "synthetic-task-contract", imported=imported)
            )
        self.installed[name] = binding
        return binding

    @staticmethod
    def contract_key(problem):
        return (
            problem.family,
            problem.contract,
            problem.revision,
            problem.schema_digest,
            problem.specification,
        )

    async def authenticate(self, skill, *, checked, audit=None):
        skill.validate_artifact(self.artifacts.get(skill.artifact_digest))
        ref = self.store.reference("capability", skill.producer, skill.source_binding.subject.key)
        cap = self.store.resolve_reference(ref)
        if (
            not isinstance(cap, Capability)
            or cap.binding_digest != skill.binding_digest
            or cap.subject != skill.source_binding.subject
            or cap.license != "Apache-2.0"
        ):
            raise ValueError("stock is not the original authenticated candidate")
        decision = None
        if checked:
            ref = self.store.reference("evidence", "verifier", skill.evidence_id)
            evidence = self.store.resolve_reference(ref)
            if (
                not isinstance(evidence, Evidence)
                or evidence.verdict != "PASS"
                or evidence.binding_digest != skill.binding_digest
                or evidence.subject != cap.subject
                or evidence.scope != cap.scope
            ):
                raise ValueError("stock has no matching original independent PASS")
            decision = await self.host.overlay.qualify(
                UseRequest(
                    receiver=self.config.owner,
                    capability_issuer=cap.issuer,
                    subject=cap.subject,
                    binding_digest=cap.binding_digest,
                    scope=cap.scope,
                    semantic_fit="confirmed",
                )
            )
        if audit is not None:
            body = decision.model_dump(mode="json") if decision is not None else None
            audit.append(
                {
                    "skill_id": skill.id,
                    "capability_subject_key": cap.subject.key,
                    "decision": body,
                    "decision_projection_digest": projection_digest(body) if body else None,
                }
            )
        return decision is None or decision.outcome == "ACCEPT"

    async def run(self, maximum, candidates):
        if maximum != 1 or candidates != 1 or self.pending is None:
            raise ValueError("one explicitly staged model attempt is required")
        data, self.pending = self.pending, None
        return await self.solve(data)

    async def solve(self, data):
        stock = Snapshot.model_validate(data["snapshot"])
        if stock.world != self.settings["world"] or stock.arm != self.settings["arm"]:
            raise ValueError("world/arm stock isolation violated")
        if stock.digest != data["snapshot_digest"]:
            raise ValueError("checkpoint snapshot digest changed")
        problem = Problem.model_validate(data["problem"])
        visible = retrieve(
            stock,
            problem,
            self.config.owner,
            view=data["view"],
            revision=self.settings.get("retrieval_revision", "1"),
        )
        checked = stock.arm in {"C", "A", "I"}
        admitted, admission_records = [], []
        for skill in visible:
            if await self.authenticate(skill, checked=checked, audit=admission_records):
                admitted.append(skill)
        restricted = CognitiveView(
            world=stock.world,
            arm=stock.arm,
            checkpoint=stock.checkpoint,
            skills=tuple(ViewSkill.from_skill(s) for s in admitted),
        )
        arguments = {key: data[key] for key in ("id", "model_seed", "view", "snapshot_digest")}
        arguments.update(
            problem=problem.model_dump(mode="json"),
            visible_snapshot=restricted.model_dump(mode="json"),
            feedback=data.get("feedback"),
            snapshot_artifact=self.artifacts.put(stock.model_dump_json().encode()),
            retrieval_candidates=[ViewSkill.from_skill(s).model_dump(mode="json") for s in visible],
            admission_records=admission_records,
        )
        if data.get("study_context") is not None:
            arguments["study_context"] = data["study_context"]
        return await self.executor.invoke(
            "propose-" + data["id"], self.proposer.id, self.proposer.digest, arguments, self.context
        )

    def draft_schema(self, problem):
        return wire_schema(problem.family, problem.difficulty)

    def model_prompt(self, problem, skills):
        return prompt(problem, skills, revision=self.settings["model"].get("prompt_revision", "1"))

    def draft_schema_for_view(self, problem, skills):
        return self.draft_schema(problem)

    def check_declared_schema(self, problem, skills, schema):
        model = self.settings["model"]
        if model.get("observation_binding_schema") == "2":
            if model["wire_schemas"][problem.family + "/" + problem.difficulty] != schema:
                raise ValueError("declared family wire changed before inference")

    def decode_model_response(self, text, schema, problem, skills):
        return validate_wire(text, schema, Solution)

    def response_metadata(self, text, schema, problem, skills, solution):
        return {}

    def minimum_model_output(self):
        return 1024

    async def infer(self, arguments):
        from collective_intelligence_overlay.adapters.ollama import local_ollama_client

        problem = Problem.model_validate(arguments["problem"])
        view = CognitiveView.model_validate(arguments["visible_snapshot"])
        text = self.model_prompt(problem, view.skills)
        if arguments.get("feedback"):
            # Only the previous public verdict/error type, never hidden cases/answers.
            text += "\nPrevious attempt public feedback: " + str(arguments["feedback"])[:600]
        model = self.settings["model"]
        draft = self.draft_schema_for_view(problem, view.skills)
        schema = draft.model_json_schema()
        self.check_declared_schema(problem, view.skills, schema)
        options = {**model["options"], "seed": arguments["model_seed"]}
        if (
            options.get("draft_num_predict") != 0
            or options.get("num_predict", 0) < self.minimum_model_output()
        ):
            raise ValueError("explicit no-draft and adequate output limit required")
        path = Path(model["output"]) / arguments["id"]
        observer = RawInferenceTransport(
            path,
            identity={
                **model["identity"],
                "peer": self.config.owner,
                "job": arguments["id"],
                "task": problem.id,
                "view": arguments["view"],
                "snapshot_digest": arguments["snapshot_digest"],
                **(
                    {"study_context": arguments["study_context"]}
                    if arguments.get("study_context")
                    else {}
                ),
            },
            requested={"native_options": options, "think": False, "keep_alive": "5m"},
            provenance={
                **model["provenance"],
                "model_name": MODEL,
                "model_digest": DIGEST,
                "prompt_digest": fingerprint(text),
                "schema_digest": fingerprint(schema),
            },
            token_reservation=options["num_ctx"] + options["num_predict"],
            real_model=True,
        )
        solution, error, response_text = None, None, None
        identity = {
            "identity_schema": "1",
            "endpoint": "/api/tags",
            "projection_scope": "selected-model-only",
            "observed_at": datetime.now(UTC).isoformat(),
            "transport_dispatch_started": False,
            "status": None,
            "selected_model": None,
            "native_response_sha256": None,
            "native_response_bytes": None,
            "error_type": None,
            "unrelated_inventory_retained": False,
        }
        try:
            async with httpx.AsyncClient(
                base_url=model["host"], timeout=5, trust_env=False
            ) as http:
                identity["transport_dispatch_started"] = True
                reply = await http.get("/api/tags")
                identity.update(
                    status=reply.status_code,
                    native_response_sha256=hashlib.sha256(reply.content).hexdigest(),
                    native_response_bytes=len(reply.content),
                )
                if len(reply.content) > 1048576:
                    raise ValueError("model identity response byte cap")
                reply.raise_for_status()
                tags = reply.json()
                selected = next(m for m in tags["models"] if m["name"] == MODEL)
                identity["selected_model"] = selected
                if selected["digest"] != DIGEST:
                    raise ValueError("pinned model changed; no alternate/pull is permitted")
            async with local_ollama_client(
                model["host"], model=MODEL, seconds=model["seconds"], transport=observer
            ) as client:
                response = await client.get_response(
                    [Message(role="user", contents=[text])],
                    options={
                        "options": options,
                        "think": False,
                        "keep_alive": "5m",
                        "response_format": draft,
                    },
                )
                response_text = response.text
                solution = self.decode_model_response(response_text, schema, problem, view.skills)
        except Exception as exc:
            error = type(exc).__name__
        finally:
            if (
                identity["selected_model"] is None
                or identity["selected_model"].get("digest") != DIGEST
            ):
                identity["error_type"] = error or "UnconfirmedModelIdentity"
            write_new(path / "model-identity.json", identity)
            await observer.aclose()
            observation = json.loads((path / "observation.json").read_bytes())
            error = error or observation["error_type"]
            transcript = {
                "solution": solution.model_dump(mode="json") if solution else None,
                "error_type": error,
                "visible_snapshot": view.model_dump(mode="json"),
                "full_snapshot_digest": arguments["snapshot_digest"],
                "full_snapshot_artifact": arguments["snapshot_artifact"],
                **(
                    {"study_context": arguments["study_context"]}
                    if arguments.get("study_context")
                    else {}
                ),
                **self.response_metadata(response_text, schema, problem, view.skills, solution),
            }
            if model.get("observation_binding_schema") == "2":
                transcript.update(
                    observation_binding_schema="2",
                    retrieval_candidates=arguments["retrieval_candidates"],
                    admission_records=arguments["admission_records"],
                    original_transport_artifacts=persist_originals(
                        path, observation, self.artifacts
                    ),
                )
            write_new(path / "parsed.json", transcript)
            artifact = self.artifacts.put(json.dumps(transcript, sort_keys=True).encode())
            event = Event(
                id="model-" + arguments["id"],
                issuer=self.config.owner,
                subject=Subject(
                    id="study-model-output",
                    version=model.get("observation_binding_schema", "1"),
                    digest=artifact,
                ),
                action="proposal" if solution else "failure",
                task_id=problem.id,
                attempt_id=arguments["id"],
                correlation_id=arguments["id"],
                costs=(
                    Cost(
                        category="formation",
                        status=observation["token_status"],
                        unit="model_tokens",
                        quantity=Decimal(observation["tokens_measured"])
                        if observation["tokens_measured"] is not None
                        else None,
                    ),
                ),
            )
            self.store.put(self.identity.sign(event))
        if not observation["stream_complete"] or observation["status"] != 200:
            raise TimeoutError("model transport incomplete; usage reservation remains charged")
        if solution and set(solution.uses) - {s.id for s in view.skills}:
            return {
                "solution": None,
                "error_type": "InvisibleSkillReference",
                "model_event": event.id,
            }
        return {
            "solution": solution.model_dump(mode="json") if solution else None,
            "error_type": error,
            "model_event": event.id,
        }

    async def handle(self, caller, data):
        operation = data["operation"]
        if operation == "app.describe":
            return {"binding": self.installed[data["name"]].model_dump(mode="json")}
        if operation == "app.stage":
            if self.pending is not None:
                raise ValueError("a model attempt is already staged")
            self.pending = json.loads(json.dumps(data))
            return {"staged": data["id"]}
        if operation == "app.export":
            binding = self.installed[data["name"]]
            raw = self.artifacts.get(binding.artifact_digest)
            return {
                "binding": binding.model_dump(mode="json"),
                "artifact_base64": base64.b64encode(raw).decode(),
            }
        if operation == "app.import":
            skill = Skill.model_validate(data["skill"])
            raw = base64.b64decode(data["artifact_base64"], validate=True)
            skill.validate_artifact(raw)
            # Data for the already installed factory, never received code.
            digest = self.artifacts.put(raw)
            if not await self.authenticate(skill, checked=self.settings["arm"] in {"C", "I", "A"}):
                raise ValueError("source is currently inadmissible")
            return {"artifact_digest": digest, "source_verified": True}
        if operation == "app.construct":
            problem, solution = (
                Problem.model_validate(data["problem"]),
                Solution.model_validate(data["solution"]),
            )
            source_admission = []
            if data.get("copied", False):
                source = Skill.model_validate(data["source_skill"])
                if source.solution != solution or not await self.authenticate(
                    source,
                    checked=self.settings["arm"] in {"C", "I", "A"},
                    audit=source_admission,
                ):
                    return {
                        "state": "unformed",
                        "reason": "source_inadmissible",
                        "source_admission": source_admission,
                    }
            formed = self.settings["arm"] in {"C", "I", "A"} and not data.get("copied", False)

            async def construct(context, publish):
                built = await self.executor.invoke(
                    "build-" + data["id"],
                    self.builder.id,
                    self.builder.digest,
                    {"solution": solution.model_dump(mode="json")},
                    context,
                )
                if built["state"] != "completed":
                    return built, None
                binding = self.materialize(
                    "candidate-" + data["id"],
                    problem,
                    solution,
                    built["result"]["artifact_digest"],
                    publish=publish,
                    imported=data.get("copied", False),
                )
                return built, binding

            formation_event = None
            if formed:
                async with FormationSession(
                    self.registry, self.identity, max_steps=2, max_seconds=30
                ) as formation:
                    context = self.context.model_copy(update={"purpose": "reuse"})
                    built, binding = await construct(context, False)
                    if binding is not None:
                        formation_event = await formation.publish(
                            binding.id,
                            self.candidate(binding, "synthetic-task-contract", formed=True),
                        )
            else:
                built, binding = await construct(self.context, True)
            if binding is None:
                return {
                    "state": "unformed",
                    "construction": built,
                    "source_admission": source_admission,
                }
            return {
                "state": "constructed",
                "binding": binding.model_dump(mode="json"),
                "construction": built,
                "formation_event": formation_event.model_dump(mode="json")
                if formation_event
                else None,
                "source_admission": source_admission,
            }
        if operation == "app.execute":
            binding = self.installed[data["name"]]
            context = self.context.model_copy(update={"purpose": data["purpose"]})
            return await self.executor.invoke(
                "execute-" + data["id"],
                binding.id,
                binding.digest,
                {"problem": data["problem"]},
                context,
            )
        if operation == "app.check":
            started = time.perf_counter()
            if self.config.owner != "verifier":
                raise ValueError("independent checks belong only to verifier")
            from accumulation_tasks import compare

            binding = Binding.model_validate(data["binding"])
            peer, offer = data["peer"], data["offer"]
            cases = self.settings["checks"][offer]
            if not 1 <= len(cases) <= 4 or binding.issuer != peer:
                raise ValueError("bounded original checker contract required")
            transcripts = []
            for index, case in enumerate(cases):
                try:
                    observed = await send(
                        self.config,
                        self.identity,
                        peer,
                        {
                            "operation": "invoke",
                            "purpose": "verification",
                            "invocation_id": "check-"
                            + fingerprint([offer, binding.digest, index])[:32],
                            "binding_id": binding.id,
                            "binding_digest": binding.digest,
                            "arguments": {"problem": case["problem"]},
                        },
                    )
                except Exception as error:
                    observed = {"state": "unknown", "error_type": type(error).__name__}
                transcripts.append(
                    {
                        "case": case,
                        "observed": observed,
                        "passed": observed.get("state") == "completed"
                        and compare(observed.get("result"), case["expected"]),
                    }
                )
            verdict = (
                "PASS"
                if all(t["passed"] for t in transcripts)
                else (
                    "FAIL"
                    if any(
                        t["observed"].get("state") == "completed" and not t["passed"]
                        for t in transcripts
                    )
                    else "UNKNOWN"
                )
            )
            artifact = self.artifacts.put(
                json.dumps(
                    {
                        "offer": offer,
                        "binding": binding.model_dump(mode="json"),
                        "peer": peer,
                        "checker_digest": self.settings["checker_digest"],
                        "transcripts": transcripts,
                    },
                    sort_keys=True,
                ).encode()
            )
            evidence = None
            if data["publish_evidence"]:
                evidence = Evidence(
                    schema_version="2",
                    id="check-" + fingerprint([offer, binding.digest])[:32],
                    issuer="verifier",
                    subject=binding.subject,
                    binding_digest=binding.digest,
                    claim="synthetic-task-contract",
                    scope=binding.scope,
                    receivers=tuple(self.settings.get("receivers", ("producer", "receiver"))),
                    verdict=verdict,
                    method="reference-check",
                    verifier_version=self.settings["checker_digest"][:32],
                    artifact_digest=artifact,
                    expires_at=now() + timedelta(hours=6),
                )
                self.store.put(self.identity.sign(evidence))
            event = Event(
                id="check-event-" + fingerprint([offer, binding.digest])[:32],
                issuer="verifier",
                subject=Subject(
                    id="study-check-" + fingerprint(offer)[:24], version="1", digest=artifact
                ),
                action="verification",
                task_id=offer,
                attempt_id=offer,
                correlation_id=offer,
                outcome=verdict,
                costs=(
                    Cost(
                        category="verification",
                        status="measured",
                        unit="wall_seconds",
                        quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                    ),
                    Cost(category="verification", status="unavailable", unit="USD", quantity=None),
                ),
            )
            self.store.put(self.identity.sign(event))
            return {
                "verdict": verdict,
                "artifact_digest": artifact,
                "checks": len(transcripts),
                "evidence": evidence.model_dump(mode="json") if evidence else None,
            }
        raise ValueError("unsupported study operation")


def configure(host: ApplicationHost, *, application_class=AccumulationApplication):
    app = application_class(host)
    if app.settings.get("installed_candidate"):
        from check_gemma_candidate import installed_candidate

        inspected = installed_candidate(
            Path(__file__).resolve().parents[1], app.settings["installed_candidate"]
        )
        artifact = app.artifacts.put(
            json.dumps(
                {
                    "wheel_sha256": inspected["installed_wheel_sha256"],
                    "version": inspected["version"],
                    "original_package_file_sha256": inspected["original_package_file_sha256"],
                    "package_within_actual_interpreter_prefix": True,
                    "all_loaded_package_modules_from_candidate": True,
                    "editable": False,
                    "inspection_scope": "trusted-host bytes/origins; no attestation",
                },
                sort_keys=True,
            ).encode()
        )
        app.store.put(
            app.identity.sign(
                Event(
                    id="candidate-installed-runtime",
                    issuer=app.config.owner,
                    subject=Subject(id="study-installed-candidate", version="1", digest=artifact),
                    action="verification",
                    task_id="startup",
                    attempt_id="startup",
                    correlation_id="startup",
                )
            )
        )
    for name in ("app.stage", "app.construct", "app.export", "app.import", "app.execute"):
        if host.config.owner != "verifier":
            host.register_operation(name, app.handle, callers=(host.config.owner,))
    host.register_operation(
        "app.describe",
        app.handle,
        callers=(host.config.owner, "verifier")
        if host.config.owner != "verifier"
        else ("verifier",),
    )
    if host.config.owner == "verifier":
        host.register_operation("app.check", app.handle, callers=("verifier",))
    else:
        ref = BindingRef(issuer=host.config.owner, id=app.builder.id, digest=app.builder.digest)
        host.register_goals(
            (
                Goal(
                    id="bounded-study-proposal",
                    revision="1",
                    request=UseRequest(
                        receiver=host.config.owner,
                        capability_issuer=host.config.owner,
                        subject=app.builder.subject,
                        binding_digest=app.builder.digest,
                        scope=app.builder.scope,
                        semantic_fit="confirmed",
                    ),
                    checker=ref,
                    builders=(ref,),
                ),
            )
        )
        host.register_goal_runner(app.run)
