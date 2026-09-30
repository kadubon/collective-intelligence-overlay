"""Installed document reference application: three peers and subsequent formation.

Run --directory NEW_PATH to provision/run the local example, or --config PATH to
serve one existing owner. No received code is imported, compiled or evaluated.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal
from urllib.parse import urlsplit

import httpx2
import uvicorn
from agent_framework import WorkflowBuilder, WorkflowContext, tool
from agent_framework import executor as maf_executor

from collective_intelligence_overlay.adapters.a2a import application, synchronize
from collective_intelligence_overlay.adapters.a2a import send as protocol_send
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
from collective_intelligence_overlay.config import Config, load_config
from collective_intelligence_overlay.demo import initialize
from collective_intelligence_overlay.lineage import FormationSession
from collective_intelligence_overlay.models import (
    Capability,
    Cost,
    Event,
    Evidence,
    Scope,
    Subject,
    now,
    uid,
)
from collective_intelligence_overlay.peer import PeerService
from collective_intelligence_overlay.queries import RecordQuery
from collective_intelligence_overlay.storage import Conflict

ENVIRONMENT = {"documents": "1"}


APPLICATION_FACTORY = "collective_intelligence_overlay.starter.adaptive_documents:configure"
APPLICATION_OPERATIONS = frozenset(
    {
        "describe",
        "register-remote",
        "form-report",
        "form-triage",
        "verify",
        "describe-checker",
        "certify-checker",
        "request-document-check",
        "adaptive-run",
        "static-run",
    }
)


async def send(config: Config, identity: Any, peer: str, data: dict[str, Any]) -> dict[str, Any]:
    if (
        config.application == APPLICATION_FACTORY
        and data.get("operation") in APPLICATION_OPERATIONS
    ):
        data = {**data, "operation": "app." + data["operation"]}
    return await protocol_send(config, identity, peer, data)


class CandidateChanged(ValueError):
    """An actual described binding differs from the explicitly pinned target."""


APPLICATION_SCRIPT = Path(__file__).resolve()
TEXT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["text"],
    "properties": {"text": {"type": "string", "minLength": 1, "maxLength": 4096}},
}
COUNT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["words"],
    "properties": {"words": {"type": "integer", "minimum": 0, "maximum": 4096}},
}
REPORT: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["report"],
    "properties": {"report": {"type": "string", "maxLength": 128}},
}
TRIAGE: dict[str, Any] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["long", "threshold"],
    "properties": {"long": {"type": "boolean"}, "threshold": {"type": "integer"}},
}


async def word_count(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"words": len(arguments["text"].split())}


async def render_count(arguments: dict[str, Any]) -> dict[str, Any]:
    return {"report": f"Words: {arguments['words']}"}


@tool
def propose_document_formation(stage: Literal["report", "triage"], text: str) -> dict[str, Any]:
    """Propose one installed document construction stage; this grants no authority or budget."""
    if not text.strip() or len(text) > 4096:
        raise ValueError("proposal input is outside the document application's scope")
    return {"operation": "form-" + stage, "text": text}


class DocumentService(PeerService):
    def __init__(self, config: Config, host: ApplicationHost | None = None) -> None:
        if host is None:
            super().__init__(config)
        else:
            self.config = host.config
            self.identity, self.overlay = host.identity, host.overlay
            self.registry, self.executor = host.registry, host.executor
            self.proposal_exchange = host.proposal_exchange
        self.artifacts = config.artifacts()
        self.installed: dict[str, Binding] = {}
        settings = config.application_settings or config.private_key.parent / "application.json"
        data: dict[str, Any] = {}
        if settings.exists():
            if settings.stat().st_size > 262144:
                raise ValueError("application settings exceed byte bound")
            data = json.loads(settings.read_text(encoding="utf-8"))
        if config.owner == "producer":
            if "counter" in data:
                binding = Binding.model_validate(data["counter"])
                if (
                    binding.id != "words"
                    or binding.issuer != config.owner
                    or binding.registrar != config.owner
                    or binding.target.kind != "mcp"
                    or binding.effects != "read-only"
                    or binding.scope
                    != Scope(
                        task="words",
                        input_contract="words.in.v1",
                        output_contract="words.out.v1",
                        environment=ENVIRONMENT,
                    )
                ):
                    raise ValueError(
                        "counter must pin the installed read-only MCP document contract"
                    )
                # Application settings are a protected private file, already
                # included in coherent owner backup. Public Binding/CAS metadata
                # never contains this credential or inherits an A2A token.
                token = data["counter_token"]
                if (
                    not isinstance(token, str)
                    or not 1 <= len(token) <= 8192
                    or "\n" in token
                    or "\r" in token
                ):
                    raise ValueError("invalid explicit MCP credential")

                def client() -> httpx2.AsyncClient:
                    return httpx2.AsyncClient(
                        verify=config.tls_context(),
                        headers={"Authorization": "Bearer " + token},
                        timeout=20,
                        follow_redirects=False,
                        trust_env=False,
                    )

                self.registry.register_mcp(
                    binding,
                    lambda args: (
                        isinstance(args.get("text"), str)
                        and bool(args["text"].strip())
                        and len(args["text"]) <= 4096
                    ),
                    http_client_factory=client,
                )
                self.installed["words"] = binding
            else:
                binding = self.install("words", word_count)
            self.publish(binding, imported=binding.target.kind == "mcp")
        elif config.owner == "receiver":
            binding = self.install("render", render_count)
            self.publish(binding)
            pins = data.get("installed")
            existing: dict[str, Binding | Capability]
            if pins is not None:
                if not isinstance(pins, dict) or set(pins) - {
                    "render",
                    "remote-words",
                    "report",
                    "triage",
                }:
                    raise ValueError("unsupported installed document binding pins")
                existing = {name: Binding.model_validate(value) for name, value in pins.items()}
                if "render" in existing and existing["render"] != binding:
                    raise ValueError("installed render changed; requalification required")
            else:
                # Compatibility with old operator settings only. New settings
                # pin exact bindings and never choose by historical timestamp.
                page = self.overlay.store.record_page(
                    RecordQuery(kinds=("capability",), issuer=config.owner), limit=16
                )
                if page.next_cursor:
                    raise ValueError("legacy candidate history requires explicit binding pins")
                candidates = [c for c in page.items if isinstance(c, Capability)]
                if len(candidates) != len(page.items):
                    raise ValueError("candidate projection has an unexpected record type")
                existing = {
                    c.entrypoint: c for c in sorted(candidates, key=lambda item: item.created_at)
                }
            for name in ("remote-words", "report", "triage"):
                if name not in existing:
                    continue
                candidate = existing[name]
                manifest = json.loads(self.artifacts.get(candidate.subject.digest))
                if name == "remote-words":
                    restored = self.install_remote(
                        Binding.model_validate(manifest["parameters"]["provider"])
                    )
                elif name == "report":
                    restored = self.install_report(manifest["parameters"].get("input_key", "text"))
                else:
                    restored = self.install_triage(int(manifest["parameters"]["threshold"]))
                if (
                    restored.digest
                    != (
                        candidate.digest
                        if isinstance(candidate, Binding)
                        else candidate.binding_digest
                    )
                    or restored.subject != candidate.subject
                    or isinstance(candidate, Binding)
                    and restored != candidate
                ):
                    raise ValueError(
                        "installed application changed; candidate requalification required"
                    )

    def make_binding(
        self, name: str, operation: Any, parameters: dict[str, Any], components: tuple[str, ...]
    ) -> Binding:
        manifest = {
            "application": "documents.v1",
            "name": name,
            "parameters": parameters,
            "components": components,
            "source": callable_digest(operation) if operation else None,
        }
        artifact = self.artifacts.put(
            json.dumps(manifest, sort_keys=True, separators=(",", ":")).encode()
        )
        input_schema, output_schema = {
            "words": (TEXT, COUNT),
            "remote-words": (TEXT, COUNT),
            "render": (COUNT, REPORT),
            "report": (TEXT, REPORT),
            "triage": (TEXT, TRIAGE),
        }[name]
        document_input = name == "report" and parameters.get("input_key") == "document"
        if document_input:
            input_schema = {
                **TEXT,
                "required": ["document"],
                "properties": {"document": TEXT["properties"]["text"]},
            }
        if name == "remote-words":
            provider = Binding.model_validate(parameters["provider"])
            endpoint = next(p.url for p in self.config.peers if p.identity == provider.issuer)
            target = Target(
                kind="a2a",
                name=provider.id,
                peer=provider.issuer,
                endpoint=endpoint,
                interface_digest=provider.digest,
                implementation_identity="remote-unknown",
            )
        else:
            target = Target(
                kind="local",
                name=name,
                interface_digest=callable_digest(operation),
                implementation_identity="installed",
            )
        return Binding(
            id=name,
            revision="2" if document_input else "1",
            issuer=self.config.owner,
            registrar=self.config.owner,
            subject=Subject(
                id="documents." + name, version="2" if document_input else "1", digest=artifact
            ),
            target=target,
            scope=Scope(
                task=name,
                input_contract=name + (".in.v2" if document_input else ".in.v1"),
                output_contract=name + ".out.v1",
                environment=ENVIRONMENT,
            ),
            input_schema=input_schema,
            output_schema=output_schema,
            callers=tuple(sorted({self.config.owner, "receiver", "verifier"})),
            verification_callers=("verifier",),
            effects="read-only",
            components=components,
        )

    def install(
        self,
        name: str,
        operation: Any,
        *,
        parameters: dict[str, Any] | None = None,
        components: tuple[str, ...] = (),
    ) -> Binding:
        binding = self.make_binding(name, operation, parameters or {}, components)
        self.registry.register_local(
            binding,
            operation,
            lambda args: (
                isinstance(value := args.get("text", args.get("document", "nonempty")), str)
                and bool(value.strip())
            ),
        )
        self.installed[name] = binding
        return binding

    def install_remote(self, provider: Binding) -> Binding:
        if (
            provider.id != "words"
            or provider.issuer != "producer"
            or provider.target.kind not in {"local", "mcp"}
        ):
            raise ValueError("application only imports the configured document counter")
        binding = self.make_binding(
            "remote-words", None, {"provider": provider.model_dump(mode="json")}, ()
        )
        self.registry.register_a2a(
            binding, lambda args: bool(args["text"].strip()), self.config, self.identity
        )
        self.installed[binding.id] = binding
        return binding

    def candidate(
        self, binding: Binding, dependencies: tuple[Binding, ...] = (), *, imported: bool = False
    ) -> Capability:
        return Capability(
            schema_version="2",
            issuer=self.config.owner,
            subject=binding.subject,
            binding_digest=binding.digest,
            scope=binding.scope,
            entrypoint=binding.id,
            claim="document-contract",
            license="Apache-2.0",
            provenance="operator-installed document application; no received executable code",
            classification="imported" if imported else "declared-new",
            dependencies=tuple(b.subject for b in dependencies),
            dependency_issuers=tuple(b.issuer for b in dependencies),
            expires_at=now() + timedelta(hours=1),
        )

    def publish(
        self, binding: Binding, dependencies: tuple[Binding, ...] = (), *, imported: bool = False
    ) -> None:
        page = self.overlay.store.record_page(
            RecordQuery(kinds=("capability",), issuer=self.config.owner, subject=binding.subject)
        )
        if page.items:
            existing = page.items[0]
            if not isinstance(existing, Capability) or existing.binding_digest != binding.digest:
                raise ValueError("existing capability and binding disagree")
            return
        self.overlay.store.put(
            self.identity.sign(self.candidate(binding, dependencies, imported=imported))
        )

    async def call(self, name: str, arguments: dict[str, Any]) -> Any:
        binding = self.installed[name]
        invocation = fingerprint([active_invocation.get() or uid(), binding.digest, arguments])
        result = await self.executor.invoke(
            invocation,
            name,
            binding.digest,
            arguments,
            ExecutionContext(caller=self.config.owner, environment=ENVIRONMENT),
        )
        if result["state"] != "completed":
            raise ValueError("registered child execution was not admitted or completed")
        return result["result"]

    def install_report(self, input_key: str = "text") -> Binding:
        if input_key not in {"text", "document"}:
            raise ValueError("unsupported installed report input adapter")

        async def report(arguments: dict[str, Any]) -> dict[str, Any]:
            @maf_executor(id="count")
            async def count(data: dict[str, Any], ctx: WorkflowContext[dict[str, Any]]) -> None:
                await ctx.send_message(await self.call("remote-words", data))

            @maf_executor(id="render")
            async def render(
                data: dict[str, Any], ctx: WorkflowContext[dict[str, Any], dict[str, Any]]
            ) -> None:
                await ctx.yield_output(await self.call("render", data))

            workflow = (
                WorkflowBuilder(start_executor=count, max_iterations=3)
                .add_edge(count, render)
                .build()
            )
            outputs = (await workflow.run({"text": arguments[input_key]})).get_outputs()
            if len(outputs) != 1:
                raise ValueError("document workflow did not yield exactly one report")
            return dict(outputs[0])

        return self.install(
            "report",
            report,
            parameters={"input_key": input_key},
            components=tuple(self.installed[n].digest for n in ("remote-words", "render")),
        )

    def install_triage(self, threshold: int) -> Binding:
        if not 1 <= threshold <= 4096:
            raise ValueError("calibration threshold outside the configured bound")

        report_input = self.installed["report"].input_schema["required"][0]

        async def triage(arguments: dict[str, Any]) -> dict[str, Any]:
            report = await self.call("report", {report_input: arguments["text"]})
            count = int(report["report"].split(": ")[1])
            return {"long": count > threshold, "threshold": threshold}

        return self.install(
            "triage",
            triage,
            parameters={"threshold": threshold},
            components=(self.installed["report"].digest,),
        )

    async def handle(self, caller: str, data: dict[str, Any]) -> dict[str, Any]:
        operation = data.get("operation")
        if operation == "describe":
            binding = self.installed[str(data["name"])]
            return {
                "binding": binding.model_dump(mode="json"),
                "manifest": json.loads(self.artifacts.get(binding.subject.digest)),
                "pid": os.getpid(),
            }
        if operation in {"register-remote", "form-report", "form-triage", "verify"}:
            if caller != self.config.owner:
                raise ValueError("application construction and checking are owner operations")
            if operation == "verify":
                return await self.check(data)
            if self.config.owner != "receiver":
                raise ValueError("construction belongs to the receiver application")
            if operation == "register-remote":
                provider = Binding.model_validate(data["binding"])
                binding = self.install_remote(provider)
                self.publish(binding, (provider,), imported=True)
                return {"binding": binding.model_dump(mode="json")}
            async with FormationSession(
                self.registry, self.identity, max_steps=8, max_seconds=25
            ) as formation:
                if operation == "form-report":
                    counted = await self.call("remote-words", {"text": data["text"]})
                    await self.call("render", counted)
                    binding = self.install_report()
                    dependencies = tuple(self.installed[n] for n in ("remote-words", "render"))
                else:
                    calibration = await self.call("report", {"text": data["text"]})
                    binding = self.install_triage(int(calibration["report"].split(": ")[1]))
                    dependencies = tuple(
                        self.installed[n] for n in ("remote-words", "render", "report")
                    )
                event = await formation.publish(binding.id, self.candidate(binding, dependencies))
            return {
                "binding": binding.model_dump(mode="json"),
                "formation": event.model_dump(mode="json"),
            }
        return await super().handle(caller, data)

    async def check(self, data: dict[str, Any]) -> dict[str, Any]:
        if self.config.owner != "verifier":
            raise ValueError("independent checking belongs to the verifier")
        attempt = str(data["attempt"])
        request = {
            "provider": str(data["provider"]),
            "name": str(data["name"]),
            "arguments": data["arguments"],
            "binding_digest": data.get("binding_digest"),
        }
        evidence_id = "checked-" + fingerprint([self.config.owner, attempt])
        saved = await run_blocking(
            self.overlay.store.record_page,
            RecordQuery(kinds=("evidence",), issuer=self.config.owner, record_id=evidence_id),
            limit=1,
        )
        if saved.items:
            evidence = saved.items[0]
            if not isinstance(evidence, Evidence):
                raise ValueError("saved check is not evidence")
            artifact = json.loads(self.artifacts.get(evidence.artifact_digest))
            if artifact.get("request") != request:
                raise Conflict("check attempt reused with different request")
            # This returns the original verdict, expiry and actual probe result.
            # It neither refreshes admission nor renews an expired PASS.
            return {"evidence": evidence.model_dump(mode="json"), "observed": artifact["observed"]}
        fence = await run_blocking(
            self.overlay.store.acquire,
            attempt,
            self.config.owner,
            "work",
            Decimal(1),
            30,
            reclaim_expired=False,
        )
        started = time.perf_counter()
        try:
            provider, name = str(data["provider"]), str(data["name"])
            await synchronize(self.config, self.identity, self.overlay.store, provider, page_size=2)
            description = await send(
                self.config, self.identity, provider, {"operation": "describe", "name": name}
            )
            binding = Binding.model_validate(description["binding"])
            if (
                request["binding_digest"] is not None
                and request["binding_digest"] != binding.digest
            ):
                raise CandidateChanged("candidate changed before checking")
            candidates = await run_blocking(
                self.overlay.store.record_page,
                RecordQuery(kinds=("capability",), issuer=provider, subject=binding.subject),
            )
            if len(candidates.items) != 1 or not isinstance(candidates.items[0], Capability):
                raise ValueError("candidate is not authenticated by its publishing peer")
            cap = candidates.items[0]
            if (
                cap.binding_digest != binding.digest
                or fingerprint(description["manifest"]) != cap.subject.digest
            ):
                raise ValueError("candidate manifest or binding changed")
            arguments = data["arguments"]
            observed = await send(
                self.config,
                self.identity,
                provider,
                {
                    "operation": "invoke",
                    "purpose": "verification",
                    "invocation_id": attempt,
                    "binding_id": binding.id,
                    "binding_digest": binding.digest,
                    "arguments": arguments,
                },
            )
            verdict = "UNKNOWN"
            if observed.get("state") == "completed":
                count = len(
                    re.findall(r"\S+", arguments.get("text", arguments.get("document", "")))
                )
                if name in {"words", "remote-words"}:
                    expected: dict[str, Any] = {"words": count}
                elif name == "render":
                    expected = {"report": "Words: " + str(arguments["words"])}
                elif name == "report":
                    expected = {"report": "Words: " + str(count)}
                elif name == "triage":
                    threshold = description["manifest"]["parameters"]["threshold"]
                    expected = {"long": count > threshold, "threshold": threshold}
                else:
                    raise ValueError("checker does not cover this application")
                verdict = "PASS" if observed["result"] == expected else "FAIL"
            artifact = self.artifacts.put(
                json.dumps(
                    {
                        "binding": binding.digest,
                        "arguments": arguments,
                        "observed": observed,
                        "request": request,
                    },
                    sort_keys=True,
                ).encode()
            )
            evidence = Evidence.model_validate(
                {
                    "schema_version": "2",
                    "id": evidence_id,
                    "issuer": self.config.owner,
                    "subject": cap.subject,
                    "binding_digest": binding.digest,
                    "scope": cap.scope,
                    "claim": cap.claim,
                    "receivers": ["producer", "receiver"],
                    "verdict": verdict,
                    "method": "reference-check",
                    "verifier_version": "document-check.v1",
                    "artifact_digest": artifact,
                    "expires_at": now() + timedelta(hours=1),
                }
            )
            event = Event(
                issuer=self.config.owner,
                subject=cap.subject,
                action="verification",
                task_id=attempt,
                attempt_id=attempt,
                correlation_id=attempt,
                outcome=evidence.verdict,
                costs=(
                    Cost(
                        category="verification",
                        status="measured",
                        unit="wall_seconds",
                        quantity=Decimal(str(round(time.perf_counter() - started, 9))),
                    ),
                ),
            )
            await run_blocking(
                self.overlay.store.commit_work,
                attempt,
                self.config.owner,
                fence,
                [self.identity.sign(evidence), self.identity.sign(event)],
            )
            return {"evidence": evidence.model_dump(mode="json"), "observed": observed}
        except BaseException:
            await asyncio.shield(
                run_blocking(
                    self.overlay.store.finish, attempt, self.config.owner, fence, cancelled=True
                )
            )
            raise


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--config", type=Path)
    group.add_argument("--directory", type=Path)
    args = parser.parse_args()
    if args.config:
        config = load_config(args.config)
        service = DocumentService(config)
        try:
            uvicorn.run(
                application(config, service.handle),
                host="127.0.0.1",
                port=urlsplit(config.url).port or 8000,
                log_level="warning",
                access_log=False,
                timeout_graceful_shutdown=10,
            )
        finally:
            service.overlay.store.close()
    else:
        configs = initialize(
            args.directory, os.environ["CIO_TEST_DATABASE_URL"], os.environ["CIO_OPA"]
        )
        for name, config in configs.items():
            config = config.model_copy(
                update={"execution_environment": ENVIRONMENT, "max_seconds": 300}
            )
            configs[name] = config
            data = config.model_dump(mode="json")
            data["database_url"] = config.database_url.get_secret_value()
            (args.directory / name / "config.json").write_text(json.dumps(data), encoding="utf-8")
        result = asyncio.run(run_application(args.directory, configs))
        (args.directory / "document-results.json").write_text(
            json.dumps(result, indent=2), encoding="utf-8"
        )
        print(json.dumps(result))


async def run_application(directory: Path, configs: dict[str, Config]) -> dict[str, Any]:
    import httpx
    from a2a.client import AgentCardResolutionError

    identities = {}
    for name, config in configs.items():
        identity, overlay = config.runtime()
        overlay.store.close()
        identities[name] = identity
    processes: dict[str, asyncio.subprocess.Process] = {}
    logs: list[Any] = []

    async def call(owner: str, **data: Any) -> dict[str, Any]:
        return await send(configs[owner], identities[owner], owner, data)

    async def cli_call(command: str, *arguments: str) -> dict[str, Any]:
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            "-m",
            "collective_intelligence_overlay.cli",
            command,
            "--config",
            str((directory / "receiver/config.json").resolve()),
            "--peer",
            "receiver",
            "--invocation-id",
            "held-out-triage",
            *arguments,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            stdout, stderr = await asyncio.wait_for(process.communicate(), 45)
        except BaseException:
            if process.returncode is None:
                process.terminate()
                await process.wait()
            raise
        if process.returncode != 0:
            raise ValueError(f"CLI {command} failed: {stderr.decode(errors='replace')}")
        return dict(json.loads(stdout))

    async def start(owner: str) -> None:
        log = (directory / owner / "document-peer.log").open("ab")
        logs.append(log)
        process = await asyncio.create_subprocess_exec(
            sys.executable,
            str(APPLICATION_SCRIPT),
            "--config",
            str((directory / owner / "config.json").resolve()),
            stdout=log,
            stderr=log,
        )
        processes[owner] = process
        async with asyncio.timeout(20):
            while True:
                if process.returncode is not None:
                    raise RuntimeError(f"{owner} exited; inspect its local document-peer.log")
                try:
                    await call(owner, operation="metrics")
                    return
                except (httpx.HTTPError, ConnectionError, AgentCardResolutionError):
                    await asyncio.sleep(0.1)

    async def stop(owner: str) -> None:
        process = processes[owner]
        if process.returncode is None:
            process.terminate()
        try:
            await asyncio.wait_for(process.wait(), 10)
        except TimeoutError:
            process.kill()
            await process.wait()

    async def sync(owner: str, source: str) -> dict[str, Any]:
        result = await call(owner, operation="sync", peer=source, page_size=1, max_pages=32)
        if not result["complete"]:
            raise ValueError("application synchronization exceeded its page budget")
        return result

    async def check(provider: str, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        result = await call(
            "verifier",
            operation="verify",
            attempt=uid(),
            provider=provider,
            name=name,
            arguments=arguments,
        )
        if result["evidence"]["verdict"] != "PASS":
            raise ValueError(f"independent {name} check did not pass: {result}")
        return result

    def invocation(binding: Binding, identifier: str, text: str, **extra: Any) -> dict[str, Any]:
        return {
            "operation": "invoke",
            "invocation_id": identifier,
            "binding_id": binding.id,
            "binding_digest": binding.digest,
            "arguments": {"text": text},
            **extra,
        }

    try:
        async with asyncio.timeout(240):
            for owner in configs:
                await start(owner)
            initial_pids = {owner: process.pid for owner, process in processes.items()}
            c1 = Binding.model_validate(
                (await call("producer", operation="describe", name="words"))["binding"]
            )
            before = await send(
                configs["receiver"],
                identities["receiver"],
                "producer",
                invocation(c1, "before-verification", "new candidate"),
            )
            denied_probe = await send(
                configs["receiver"],
                identities["receiver"],
                "producer",
                invocation(c1, "unauthorized-probe", "new candidate", purpose="verification"),
            )
            if before["state"] != "unknown" or denied_probe["state"] != "rejected":
                raise ValueError(
                    f"precheck states: {before.get('state')}, {denied_probe.get('state')}"
                )
            checked_c1 = await check(
                "producer", "words", {"text": "independent\tunicode 文書 test"}
            )
            await sync("producer", "verifier")
            await sync("receiver", "producer")
            await sync("receiver", "verifier")
            await call("receiver", operation="register-remote", binding=c1.model_dump(mode="json"))
            await check("receiver", "render", {"words": 7})
            await check("receiver", "remote-words", {"text": "remote service contract check"})
            await sync("receiver", "verifier")
            proposal3 = await propose_document_formation.invoke(
                arguments={"stage": "report", "text": "formation material with four paragraphs"}
            )
            if not proposal3[0].text:
                raise ValueError("proposal tool returned no construction arguments")
            formed3 = await call("receiver", **json.loads(proposal3[0].text))
            c3 = Binding.model_validate(formed3["binding"])
            await check(
                "receiver",
                "report",
                {"text": "a separate verification document\nwith another line"},
            )
            await sync("receiver", "verifier")
            calibration = "calibration vocabulary"
            proposal4 = await propose_document_formation.invoke(
                arguments={"stage": "triage", "text": calibration}
            )
            if not proposal4[0].text:
                raise ValueError("proposal tool returned no construction arguments")
            formed4 = await call("receiver", **json.loads(proposal4[0].text))
            c4 = Binding.model_validate(formed4["binding"])
            checked_c4 = await check(
                "receiver", "triage", {"text": "new verification input is deliberately longer"}
            )
            await sync("receiver", "verifier")
            requests = [
                {
                    "receiver": "receiver",
                    "subject": b.subject.model_dump(mode="json"),
                    "capability_issuer": b.issuer,
                    "binding_digest": b.digest,
                    "scope": b.scope.model_dump(mode="json"),
                    "semantic_fit": "confirmed",
                }
                for b in (c3, c4)
            ]
            accepted = await call("receiver", operation="capability_metrics", requests=requests)
            held_out = "This previously unseen document has its own content."
            use_request = invocation(c4, "held-out-triage", held_out)
            argument_file = directory / "held-out-arguments.json"
            await run_blocking(
                argument_file.write_text, json.dumps({"text": held_out}), encoding="utf-8"
            )
            result = await cli_call(
                "invoke",
                "--binding-id",
                c4.id,
                "--binding-digest",
                c4.digest,
                "--arguments-file",
                str(argument_file.resolve()),
            )
            expected = {"long": len(re.findall(r"\S+", held_out)) > 2, "threshold": 2}
            if result["state"] != "completed" or result["result"] != expected:
                raise ValueError("held-out composed execution failed")
            await stop("receiver")
            await start("receiver")
            restored = await call("receiver", operation="describe", name="triage")
            if Binding.model_validate(restored["binding"]).digest != c4.digest:
                raise ValueError("application binding did not survive restart")
            replay = await call("receiver", **use_request)
            if replay != result:
                raise ValueError("durable invocation result changed after restart")
            looked_up = await cli_call("invocation")
            if looked_up["invocation"] != result:
                raise ValueError("CLI lookup differs from durable result after restart")
            await call(
                "producer",
                operation="revoke",
                subject=c1.subject.model_dump(mode="json"),
                reason="document counter withdrawn by owner",
            )
            delta = await sync("receiver", "producer")
            rejected = await call("receiver", operation="capability_metrics", requests=requests)
            blocked = [
                await call("receiver", **invocation(b, "after-withdrawal-" + b.id, held_out))
                for b in (c3, c4)
            ]
            if any(item["state"] != "unknown" for item in blocked):
                raise ValueError("a withdrawn dependency still permitted new execution")
            pages = []
            cursor = None
            for _ in range(32):
                page = await call("receiver", operation="metrics", cursor=cursor, limit=4)
                pages.append(page)
                cursor = page["next_cursor"]
                if cursor is None:
                    break
            if cursor is not None:
                raise ValueError("example metrics exceeded page budget")
            return {
                "processes": len(initial_pids),
                "pids": initial_pids,
                "restarted_receiver_pid": processes["receiver"].pid,
                "before_verification": before["state"],
                "ungranted_probe": denied_probe["state"],
                "c1_check": checked_c1["evidence"]["verdict"],
                "c4_check": checked_c4["evidence"]["verdict"],
                "formation_c3": formed3["formation"],
                "formation_c4": formed4["formation"],
                "held_out_result": result["result"],
                "replayed_receipt": replay["receipt_id"],
                "accepted_before": accepted["currently_accepted_capabilities"],
                "accepted_after": rejected["currently_accepted_capabilities"],
                "checked_after": rejected["historically_checked_capabilities"],
                "after_withdrawal": [item["decision"]["outcome"] for item in rejected["targets"]],
                "delta": delta,
                "metrics_pages": pages,
            }
    finally:
        for owner in processes:
            await stop(owner)
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
