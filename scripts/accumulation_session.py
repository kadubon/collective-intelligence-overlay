"""Finite study actions over ProductionSession and installed application APIs.

This module neither runs a model directly nor implements admission/execution.
The shared cap belongs to the complete world/arm, including both proposer peers.
"""

import asyncio
import hashlib
import json
import os
import time
from datetime import timedelta
from pathlib import Path

from accumulation_application import DIGEST, FACTORY, MODEL
from accumulation_primitives import ENVIRONMENT, Solution
from accumulation_stock import Skill, Snapshot, ViewSkill, retrieve
from production_session import ProductionSession
from sqlalchemy import select

from collective_intelligence_overlay.adapters.inference_observer import write_new
from collective_intelligence_overlay.bindings import ArtifactSpec, Binding, fingerprint
from collective_intelligence_overlay.models import Event, Evidence, Subject, now
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.starter.adaptive_documents import write_json
from collective_intelligence_overlay.storage import decisions, projection_digest

ROOT = Path(__file__).resolve().parents[1]


class SharedCap:
    """Serial operator resource cap, never a new execution or allowance ledger."""

    def __init__(self, limits, *, context, predict):
        self.limits = limits
        self.reservation = context + predict
        self.calls = self.charged_tokens = self.measured_tokens = 0
        self.missing_usage = self.actions = 0
        self.execution_invocations = self.checker_cases = self.retrievals = 0
        self.not_sent = 0
        self.identity_observations_reserved = 0
        self.model_retrievals_reserved = 0
        self.started = time.monotonic()

    def action(self):
        if self.actions >= self.limits["application_actions"] or self.expired():
            raise ValueError("aggregate application action cap")
        self.actions += 1

    def expired(self):
        return time.monotonic() - self.started >= self.limits["wall_seconds"]

    def observation(self, executions=0, cases=0):
        for key, quantity in (("execution_invocations", executions), ("checker_cases", cases)):
            limit = self.limits.get(key, 4096)
            if getattr(self, key) + quantity > limit:
                raise ValueError("aggregate " + key + " cap")
        self.execution_invocations += executions
        self.checker_cases += cases

    def retrieval(self):
        if self.retrievals + self.model_retrievals_reserved >= self.limits.get(
            "retrieval_calls", 256
        ):
            raise ValueError("aggregate retrieval cap")
        self.retrievals += 1

    def reserve_model(self, identifier=None):
        if (
            self.calls >= self.limits["model_calls"]
            or self.identity_observations_reserved
            >= self.limits.get("model_identity_observations", self.limits["model_calls"])
            or self.charged_tokens + self.reservation > self.limits["model_tokens"]
            or self.retrievals + self.model_retrievals_reserved
            >= self.limits.get("retrieval_calls", 256)
            or time.monotonic() - self.started >= self.limits["wall_seconds"]
        ):
            return False
        self.calls += 1
        self.identity_observations_reserved += 1
        self.model_retrievals_reserved += 1
        self.charged_tokens += self.reservation
        return True

    def settle_model(self, observation):
        if observation and observation.get("transport_dispatch_started") is False:
            if observation.get("budget_charge") != 0:
                raise ValueError("pre-send observation cannot carry dispatched consumption")
            self.charged_tokens -= self.reservation
            self.not_sent += 1
            return
        measured = observation.get("tokens_measured") if observation else None
        if isinstance(measured, int) and not isinstance(measured, bool) and measured >= 0:
            if measured > self.reservation:
                raise ValueError("actual usage exceeds declared request reservation")
            self.charged_tokens += measured - self.reservation
            self.measured_tokens += measured
        else:
            self.missing_usage += 1

    def report(self):
        return {
            "limits": self.limits,
            "model_calls": self.calls,
            "model_identity_observations_reserved": self.identity_observations_reserved,
            "model_retrieval_calls_reserved": self.model_retrievals_reserved,
            "charged_tokens": self.charged_tokens,
            "measured_tokens": self.measured_tokens,
            "missing_usage_requests": self.missing_usage,
            "application_actions": self.actions,
            "execution_invocations_reserved": self.execution_invocations,
            "checker_cases_reserved": self.checker_cases,
            "retrieval_calls": self.retrievals,
            "proven_not_sent_requests": self.not_sent,
            "inclusive_wall_seconds": time.monotonic() - self.started,
        }


class CappedSession(ProductionSession):
    """Account for every driver RPC, including native startup readiness probes."""

    async def call(self, owner, **data):
        self.study.cap.action()
        operation = data["operation"]
        cases = len(self.study.checks[data["offer"]]) if operation == "app.check" else 0
        executions = cases + int(operation in {"invoke", "run", "app.construct", "app.execute"})
        self.study.cap.observation(executions, cases)
        return await super().call(owner, **data)


class StudySession:
    def __init__(self, home, output, world, arm, protocol, model, checks):
        self.world, self.arm, self.protocol, self.model = world, arm, protocol, model
        self.output = Path(output).resolve()
        self.output.mkdir()
        self.cap = SharedCap(
            protocol["caps"],
            context=model["options"]["num_ctx"],
            predict=model["options"]["num_predict"],
        )
        self.session = CappedSession(
            Path(home).resolve(),
            self.output,
            os.environ["CIO_TEST_DATABASE_URL"],
            os.environ["CIO_OPA"],
            os.environ["CIO_CADDY"],
            protocol["caps"]["application_actions"] + 100,
            "unused",
        )
        self.session.study = self
        self.checks = checks
        self.stock = Snapshot(world=world.id, arm=arm, checkpoint=0, skills=())
        self.transfers = []
        self.source_sync_seconds = {}

    async def call(self, owner, **data):
        return await self.session.call(owner, **data)

    async def sync(self, owner, source):
        result = await self.call(owner, operation="sync", peer=source, page_size=128, max_pages=16)
        if not result.get("complete"):
            raise ValueError("authenticated complete source synchronization required")
        self.source_sync_seconds[owner, source] = time.monotonic()
        return result

    async def maintain_sources(self, owner, sources):
        for source in sorted(set(sources) - {owner}):
            if time.monotonic() - self.source_sync_seconds.get((owner, source), 0) >= 120:
                await self.sync(owner, source)

    async def initialize(self):
        # Keep source-only import separate from the installed package location.
        scripts = str(ROOT / "scripts")
        os.environ["PYTHONPATH"] = os.pathsep.join(
            filter(None, (scripts, os.environ.get("PYTHONPATH")))
        )
        from production_mesh import ProductionMesh

        s = self.session
        owners = ("producer", "verifier", "receiver")
        if self.protocol.get("new_receiver", False):
            owners += ("newreceiver",)
        s.mesh = await asyncio.to_thread(
            ProductionMesh,
            s.home,
            s.database,
            s.opa,
            s.caddy,
            s.allowance,
            proxy_seconds=305,
            owners=owners,
        )
        s.configs = {
            owner: original.model_copy(
                update={
                    "application": self.protocol.get("application_factory", FACTORY),
                    "application_settings": original.private_key.parent / "application.json",
                    "execution_environment": ENVIRONMENT,
                    "max_seconds": 300,
                    "max_concurrency": 1,
                    "max_steps": 1,
                    "max_children": 8,
                    "artifact_capacity_bytes": self.protocol["caps"].get(
                        "owner_CAS_bytes", 16777216
                    ),
                    "artifact_max_files": 4096,
                }
            )
            for owner, original in s.mesh.configs.items()
        }
        s.mesh.configs = s.configs
        for owner, config in s.configs.items():
            data = config.model_dump(mode="json", exclude={"database_url"})
            data["database_url_file"] = "secrets/database-url"
            write_json(config.private_key.parent / "config.json", data)
            settings = {
                "world": self.world.id,
                "arm": self.arm,
                "retrieval_revision": self.protocol.get("retrieval_revision", "1"),
            }
            if self.protocol.get("classification") == "confirmation" or self.protocol.get(
                "require_installed_candidate"
            ):
                settings["installed_candidate"] = self.protocol["installed_wheel"]
            if owner == "verifier":
                settings.update(
                    checks=self.checks,
                    receivers=owners,
                    checker_digest=(
                        fingerprint(
                            {
                                name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                                for name in self.protocol["checker_sources"]
                            }
                        )
                        if self.protocol.get("checker_sources")
                        else hashlib.sha256(
                            (ROOT / "scripts/accumulation_tasks.py").read_bytes()
                        ).hexdigest()
                    ),
                )
            else:
                settings["model"] = {
                    **self.model,
                    "observation_binding_schema": self.protocol.get(
                        "observation_binding_schema", "1"
                    ),
                    "wire_schemas": self.protocol.get("wire_schemas", {}),
                    "output": str(self.output / "model"),
                    "identity": {
                        "world": self.world.id,
                        "arm": self.arm,
                        "protocol": self.protocol["id"],
                    },
                    "provenance": {
                        "sources": self.protocol["sources"],
                        "model_name": MODEL,
                        "model_digest": DIGEST,
                    },
                }
            write_json(config.application_settings, settings)
            identity, overlay = config.runtime()
            s.identities[owner] = identity
            overlay.store.close()
        await asyncio.to_thread(s.mesh.start_proxies)
        for owner in s.configs:
            if owner == "newreceiver":
                continue  # Cold process, fresh DB/CAS/key; activated only after training.
            await s.start(owner)
        # The separate verifier checks only the installed parameter constructor.
        # No completed study skill, query, latent coefficient or oracle is seeded.
        for owner in ("producer", "receiver"):
            await self.certify_constructor(owner)
        write_new(self.output / "initial-stock.json", self.stock.model_dump(mode="json"))

    async def certify_constructor(self, owner):
        s = self.session
        if owner in s.configs:
            description = await self.call(owner, operation="app.describe", name="build-plan")
            binding = Binding.model_validate(description["binding"])
            valid = Solution(family="calibration").model_dump(mode="json")
            observations = []
            for index, value in enumerate((valid, {"family": "not-a-family"})):
                observations.append(
                    await self.call(
                        "verifier",
                        destination=owner,
                        operation="invoke",
                        purpose="verification",
                        invocation_id="base-validator-" + str(index),
                        binding_id=binding.id,
                        binding_digest=binding.digest,
                        arguments={"solution": value},
                    )
                )
            good, bad = observations
            if (
                good.get("state") != "completed"
                or not good["result"].get("valid")
                or bad.get("state") != "completed"
                or bad["result"].get("valid") is not False
            ):
                raise ValueError("independent parameter validation calibration failed")
            # Check actual CAS reconstruction data, not only its digest string.
            raw = s.configs[owner].artifacts().get(good["result"]["artifact_digest"])
            if ArtifactSpec.model_validate_json(raw).parameters != valid:
                raise ValueError("actual constructor output differs from public test input")
            identity, overlay = s.configs["verifier"].runtime()
            try:
                artifact = (
                    s.configs["verifier"]
                    .artifacts()
                    .put(json.dumps(observations, sort_keys=True).encode())
                )
                ev = Evidence(
                    schema_version="2",
                    id="base-" + binding.digest,
                    issuer="verifier",
                    subject=binding.subject,
                    binding_digest=binding.digest,
                    claim="parameter-construction",
                    scope=binding.scope,
                    receivers=(owner,),
                    verdict="PASS",
                    method="reference-check",
                    verifier_version="study-constructor-1",
                    artifact_digest=artifact,
                    expires_at=now() + timedelta(hours=6),
                )
                overlay.store.put(identity.sign(ev))
            finally:
                overlay.store.close()
            await self.sync(owner, "verifier")

    async def check_constructed(
        self, peer, offer, problem, solution, identifier, *, copied, source_skill=None
    ):
        await self.maintain_sources(peer, ("verifier",))
        built = await self.call(
            peer,
            operation="app.construct",
            id=identifier,
            problem=problem.model_dump(mode="json"),
            solution=solution.model_dump(mode="json"),
            copied=copied,
            source_skill=source_skill.model_dump(mode="json") if source_skill else None,
        )
        if built.get("state") != "constructed":
            return {"succeeded": False, "construction": built}
        binding = Binding.model_validate(built["binding"])
        checked = await self.call(
            "verifier",
            operation="app.check",
            offer=offer,
            peer=peer,
            binding=binding.model_dump(mode="json"),
            publish_evidence=self.arm in {"C", "I", "A"},
        )
        result = {
            "succeeded": checked.get("verdict") == "PASS",
            "construction": built,
            "check": checked,
        }
        if (
            self.protocol.get("restricted_endpoints")
            and getattr(self.cap, "active", None)
            and result["succeeded"]
        ):
            result["first_independent_pass_wall_seconds"] = (
                time.monotonic() - self.cap.offer_started
            )
        if result["succeeded"]:
            if self.arm in {"C", "I", "A"}:
                await self.sync(peer, "verifier")
            executed = await self.call(
                peer,
                operation="app.execute",
                id=identifier,
                name=binding.id,
                purpose="reuse" if self.arm in {"C", "I", "A"} else "verification",
                problem=problem.model_dump(mode="json"),
            )
            result["execution"] = executed
            result["succeeded"] = executed.get("state") == "completed"
        return result

    async def offer(
        self,
        peer,
        offer,
        problem,
        snapshot,
        *,
        view="full",
        attempts=1,
        episode=0,
        learn=False,
        task_world=None,
        phase="evaluation",
    ):
        if attempts not in {1, 2}:
            raise ValueError("finite preregistered attempts required")
        directory = self.output / "offers" / offer
        directory.mkdir(parents=True)
        record = {
            "id": offer,
            "peer": peer,
            "world": self.world.id,
            "arm": self.arm,
            "problem": problem.model_dump(mode="json"),
            "view": view,
            "snapshot_digest": snapshot.digest,
            "checkpoint": snapshot.checkpoint,
            "episode": episode,
            "learn": learn,
            "task_world": task_world or self.world.id,
            "phase": phase,
            "attempts": [],
            "succeeded": False,
            "budget_before": self.cap.report(),
        }
        write_new(directory / "intent.json", {k: v for k, v in record.items() if k != "attempts"})
        before = time.monotonic()
        if self.protocol.get("restricted_endpoints"):
            self.cap.begin_offer(self.world.id, self.arm, offer, phase)
        original_stock = self.stock.digest
        selected = None
        try:
            self.cap.retrieval()
            visible = retrieve(
                snapshot,
                problem,
                peer,
                view=view,
                revision=self.protocol.get("retrieval_revision", "1"),
            )
            record["retrieval_candidates"] = [
                ViewSkill.from_skill(s).model_dump(mode="json") for s in visible
            ]
            await self.maintain_sources(peer, ("verifier", *(s.producer for s in visible)))
            # Strong ordinary memory also tries a reconstructed callable directly.
            # Current independent checks remain identical for all strategies.
            if (
                visible
                and self.arm != "E"
                and visible[0].family == problem.family
                and visible[0].contract == problem.contract
            ):
                identifier = offer + "-reuse"
                result = await self.check_constructed(
                    peer,
                    offer,
                    problem,
                    visible[0].solution,
                    identifier,
                    copied=True,
                    source_skill=visible[0],
                )
                record["attempts"].append(
                    {
                        "kind": "copied-executable",
                        "id": identifier,
                        "solution": visible[0].solution.model_dump(mode="json"),
                        "source_skill": visible[0].model_dump(mode="json"),
                        **result,
                    }
                )
                if self.protocol.get("restricted_endpoints"):
                    record["attempts"][-1].update(
                        endpoint_wall_seconds=result.get(
                            "first_independent_pass_wall_seconds", time.monotonic() - before
                        ),
                        endpoint_measured_tokens=0,
                        endpoint_charged_tokens=0,
                    )
                if result["succeeded"]:
                    selected = record["attempts"][-1]
            for index in range(attempts):
                if selected is not None:
                    break
                identifier = offer + "-draft-" + str(index)
                if not self.cap.reserve_model(identifier):
                    record["attempts"].append(
                        {
                            "kind": "model",
                            "id": identifier,
                            "status": "not_dispatched_budget",
                            "succeeded": False,
                        }
                    )
                    break
                seed = int(
                    hashlib.sha256(
                        (
                            self.protocol["id"]
                            + "/"
                            + str(self.world.seed)
                            + "/"
                            + problem.id
                            + "/"
                            + str(index)
                        ).encode()
                    ).hexdigest()[:8],
                    16,
                ) % (2**31 - 1)
                staged = await self.call(
                    peer,
                    operation="app.stage",
                    id=identifier,
                    model_seed=seed,
                    problem=problem.model_dump(mode="json"),
                    view=view,
                    snapshot=snapshot.model_dump(mode="json"),
                    snapshot_digest=snapshot.digest,
                    feedback=(
                        "Previous independent check did not pass"
                        if index and self.protocol.get("feedback_policy") != "none"
                        else None
                    ),
                )
                if staged.get("staged") == identifier:
                    response = await self.call(
                        peer, operation="run", max_steps=1, max_candidates=1, seconds=300
                    )
                else:
                    response = {"state": "unknown", "error_type": "stage_failed"}
                path = self.output / "model" / identifier / "observation.json"
                observation = json.loads(path.read_bytes()) if path.exists() else None
                self.cap.settle_model(observation)
                attempt = {
                    "kind": "model",
                    "id": identifier,
                    "model_seed": seed,
                    "response": response,
                    "succeeded": False,
                }
                record["attempts"].append(attempt)
                value = (response.get("result") or {}).get("solution")
                if response.get("state") == "completed" and value is not None:
                    solution = Solution.model_validate(value)
                    result = await self.check_constructed(
                        peer, offer, problem, solution, identifier, copied=False
                    )
                    attempt.update(solution=solution.model_dump(mode="json"), **result)
                if attempt["succeeded"]:
                    selected = attempt
                if self.protocol.get("restricted_endpoints"):
                    attempt["endpoint_wall_seconds"] = attempt.get(
                        "first_independent_pass_wall_seconds", time.monotonic() - before
                    )
                    attempt["endpoint_measured_tokens"] = (
                        self.cap.measured_tokens - record["budget_before"]["measured_tokens"]
                    )
                    attempt["endpoint_charged_tokens"] = (
                        self.cap.charged_tokens - record["budget_before"]["charged_tokens"]
                    )
            record["succeeded"] = selected is not None
            if learn and selected is not None and self.arm != "E":
                skill = self.skill(selected, peer, problem, episode)
                self.stock = Snapshot(
                    world=self.world.id,
                    arm=self.arm,
                    checkpoint=episode,
                    skills=(*self.stock.skills, skill),
                )
                record["learning_succeeded"] = True
                try:
                    await self.transfer(skill)
                except Exception as error:
                    record["transfer_error_type"] = type(error).__name__
            elif learn:
                self.stock = self.stock.model_copy(update={"checkpoint": episode})
            if not learn and self.stock.digest != original_stock:
                raise ValueError("read-only evaluation changed training stock")
        except Exception as error:
            record["error_type"] = type(error).__name__
        finally:
            record["succeeded"] = any(a.get("succeeded", False) for a in record["attempts"])
            if learn:
                record.setdefault("learning_succeeded", False)
                self.stock = self.stock.model_copy(update={"checkpoint": episode})
            record["inclusive_wall_seconds"] = time.monotonic() - before
            record["budget_after"] = self.cap.report()
            record["stock_digest_after"] = self.stock.digest
            self.persist_offer(directory, record)
            if self.protocol.get("restricted_endpoints"):
                self.cap.end_offer()
        return record

    def persist_offer(self, directory, record):
        write_new(directory / "result.json", record)
        if self.protocol.get("observation_binding_schema") != "2":
            return
        config = self.session.configs[record["peer"]]
        artifact = config.artifacts().put((directory / "result.json").read_bytes())
        identity, overlay = config.runtime()
        try:
            overlay.store.put(
                identity.sign(
                    Event(
                        id="offer-observation-" + record["id"],
                        issuer=record["peer"],
                        subject=Subject(id="study-offer-observation", version="2", digest=artifact),
                        action="verification",
                        task_id=record["problem"]["id"],
                        attempt_id=record["id"],
                        correlation_id=record["id"],
                    )
                )
            )
        finally:
            overlay.store.close()

    def skill(self, selected, peer, problem, episode, *, source_world=None):
        binding = Binding.model_validate(selected["construction"]["binding"])
        evidence = selected["check"].get("evidence")
        return Skill(
            id=binding.id,
            producer=peer,
            family=problem.family,
            contract=problem.contract,
            revision=problem.revision,
            schema_digest=problem.schema_digest,
            solution=Solution.model_validate(selected["solution"]),
            basic_passed=True,
            independent_verdict="PASS",
            evidence_id=evidence["id"] if evidence else None,
            binding_digest=binding.digest,
            artifact_digest=binding.artifact_digest,
            source_world=source_world or self.world.id,
            source_binding=binding,
            source_problem=problem,
            episode=episode,
        )

    async def activate_receiver(self):
        if "newreceiver" not in self.session.configs:
            raise ValueError("new identity was not declared before training")
        config = self.session.configs["newreceiver"]
        identity, overlay = config.runtime()
        try:
            if overlay.store.record_page(RecordQuery(), limit=1).items:
                raise ValueError("new receiver must begin with an empty signed history")
            if config.artifacts().usage()["files"]:
                raise ValueError("new receiver must begin with an empty CAS")
        finally:
            overlay.store.close()
        await self.session.start("newreceiver")
        await self.certify_constructor("newreceiver")
        return {
            "identity_keyid": identity.signer.public_key.keyid,
            "fresh_database": True,
            "fresh_CAS": True,
            "conversation_transferred": False,
        }

    async def import_to(self, skill, other):
        exported = await self.call(
            skill.producer, operation="app.export", name=skill.source_binding.id
        )
        await self.sync(other, skill.producer)
        if self.arm in {"C", "I", "A"}:
            await self.sync(other, "verifier")
        imported = await self.call(
            other,
            operation="app.import",
            skill=skill.model_dump(mode="json"),
            artifact_base64=exported["artifact_base64"],
        )
        item = {
            "skill": skill.id,
            "source": skill.producer,
            "receiver": other,
            "artifact_digest": skill.artifact_digest,
            "result": imported,
        }
        self.transfers.append(item)
        if imported.get("artifact_digest") != skill.artifact_digest:
            raise ValueError("actual local artifact transfer failed")
        return item

    async def transfer(self, skill):
        other = "receiver" if skill.producer == "producer" else "producer"
        if self.arm == "I":
            return
        await self.import_to(skill, other)

    async def finish(self):
        write_new(self.output / "final-stock.json", self.stock.model_dump(mode="json"))
        write_new(self.output / "transfers.json", self.transfers)
        for owner in self.session.processes:
            await self.session.stop(owner)
        for owner, config in self.session.configs.items():
            _, overlay = config.runtime()
            try:
                cursor, original = None, []
                for _ in range(128):
                    page = overlay.store.record_page(
                        RecordQuery(kinds=("decision",)), cursor=cursor, limit=256
                    )
                    with overlay.store.engine.connect() as connection:
                        for r in page.items:
                            body = connection.execute(
                                select(decisions.c.body).where(decisions.c.id == r.id)
                            ).scalar_one()
                            original.append(
                                {"body": body, "projection_digest": projection_digest(body)}
                            )
                    cursor = page.next_cursor
                    if cursor is None:
                        break
                else:
                    raise ValueError("complete safety decision export exceeds declared bound")
                write_new(
                    self.output / (owner + "-decisions.json"),
                    {
                        "owner": owner,
                        "original_local_projections": original,
                        "complete": True,
                        "signed": False,
                    },
                )
            finally:
                overlay.store.close()
        exported = await self.session.finish()
        write_new(self.output / "export.json", exported)
        write_new(self.output / "resources.json", self.cap.report())
        return exported
