"""Source-only observation harness over the installed standard three-owner service."""

import asyncio
import base64
import json
import os
import subprocess
import sys
import time
from pathlib import Path

from run_production_experiment import ROOT, log_observations, process_sample, subtree
from sqlalchemy import text

from collective_intelligence_overlay.adapters.a2a import send
from collective_intelligence_overlay.bindings import Binding
from collective_intelligence_overlay.models import UseRequest
from collective_intelligence_overlay.starter.adaptive_documents import (
    ENVIRONMENT,
    configure_application,
    write_json,
)
from collective_intelligence_overlay.starter.documents import APPLICATION_FACTORY

sys.path[:0] = [str(ROOT / "tests/e2e"), str(ROOT / "examples")]
from evaluate_documents import export_owner  # noqa: E402
from production_mesh import ProductionMesh, stop_process  # noqa: E402


class ProductionSession:
    """No alternative executor, allowance, HTTP protocol or application logic."""

    def __init__(self, home, output, database, opa, caddy, allowance, training):
        self.home, self.output = home, output
        self.database, self.opa, self.caddy = database, opa, caddy
        self.allowance, self.training = allowance, training
        self.mesh = None
        self.configs, self.identities, self.processes = {}, {}, {}
        self.logs, self.calls, self.samples = [], [], []
        self.started = time.monotonic()
        self.phase = "setup"
        self.pg_pid = None
        self.journal = (output / "calls.jsonl").open("x", encoding="utf-8")

    def seconds(self):
        return time.monotonic() - self.started

    async def call(self, owner, *, category="control", **data):
        if len(self.calls) >= 8192:
            raise ValueError("finite observation call bound exceeded")
        item = {
            "call_index": len(self.calls),
            "owner": owner,
            "phase": self.phase,
            "category": category,
            "operation": data["operation"],
            "request": data,
            "offered_seconds": self.seconds(),
            "status": "censored",
        }
        self.calls.append(item)
        before = time.monotonic()
        try:
            value = await send(self.configs[owner], self.identities[owner], owner, data)
            item.update(status="returned", result=value)
            return value
        except Exception as error:
            item.update(status="failed", error_type=type(error).__name__)
            return {"error_type": type(error).__name__}
        finally:
            item["wall_seconds"] = time.monotonic() - before
            item["latency_censored"] = item["status"] == "censored"
            self.journal.write(json.dumps(item, ensure_ascii=False) + "\n")
            self.journal.flush()

    async def sync(self, owner, source):
        return await self.call(owner, operation="sync", peer=source, page_size=128, max_pages=16)

    async def start(self, owner):
        config = self.configs[owner]
        log = (config.private_key.parent / "profile-process.log").open("ab")
        self.logs.append(log)
        self.processes[owner] = await asyncio.to_thread(
            subprocess.Popen,
            [
                sys.executable,
                "-m",
                "collective_intelligence_overlay.cli",
                "peer",
                "--config",
                str(config.private_key.parent / "config.json"),
            ],
            cwd=self.home,
            stdout=log,
            stderr=subprocess.STDOUT,
        )
        async with asyncio.timeout(30):
            while True:
                if self.processes[owner].poll() is not None:
                    raise RuntimeError("installed peer exited during startup")
                value = await self.call(owner, operation="status")
                if value.get("state") == "ready":
                    return value
                await asyncio.sleep(0.1)

    async def stop(self, owner, *, crash=False):
        process = self.processes[owner]
        if crash and process.poll() is None:
            process.kill()
        await asyncio.to_thread(stop_process, process)

    async def initialize(self):
        self.mesh = await asyncio.to_thread(
            ProductionMesh, self.home, self.database, self.opa, self.caddy, self.allowance
        )
        if sys.platform == "linux":
            with self.mesh.admin.connect() as conn:
                path = Path(conn.execute(text("SHOW data_directory")).scalar_one())
            self.pg_pid = int((path / "postmaster.pid").read_text().splitlines()[0])
        for owner, original in self.mesh.configs.items():
            config = original.model_copy(
                update={
                    "execution_environment": ENVIRONMENT,
                    "max_seconds": 120,
                    "application": APPLICATION_FACTORY,
                    "application_settings": original.private_key.parent / "application.json",
                }
            )
            self.configs[owner] = config
            data = config.model_dump(mode="json", exclude={"database_url"})
            data["database_url_file"] = "secrets/database-url"
            write_json(config.private_key.parent / "config.json", data)
        self.mesh.configs = self.configs
        await self.mesh.configure_mcp(self.configs["producer"])
        await asyncio.to_thread(configure_application, self.configs, self.training)
        for owner, config in self.configs.items():
            identity, overlay = config.runtime()
            self.identities[owner] = identity
            overlay.store.close()
        await asyncio.to_thread(self.mesh.start_proxies)
        for owner in self.configs:
            await self.start(owner)
        for provider, name, arguments in (
            ("producer", "words", {"text": "initial primitive check"}),
            ("receiver", "render", {"words": 7}),
            ("receiver", "remote-words", {"text": "remote primitive check"}),
        ):
            result = await self.verify(provider, name, arguments, "initial-" + name)
            if result.get("evidence", {}).get("verdict") != "PASS":
                raise ValueError("initial primitive check did not pass")
            if name == "words":
                for owner, source in (
                    ("producer", "verifier"),
                    ("receiver", "producer"),
                    ("receiver", "verifier"),
                ):
                    if not (await self.sync(owner, source)).get("complete"):
                        raise ValueError("initial source synchronization incomplete")
        await self.sync("receiver", "verifier")
        for target in ("verifier", "receiver"):
            result = await self.call("producer", operation="app.certify-checker", target=target)
            if result.get("evidence", {}).get("verdict") != "PASS":
                raise ValueError("initial checker calibration did not pass")
            if target == "verifier":
                await self.sync("verifier", "producer")
                await self.sync("receiver", "verifier")
            await self.sync("receiver", "producer")
        self.initial_run = await self.call("receiver", operation="run", max_steps=8)
        if self.initial_run.get("reason") != "goals_satisfied":
            raise ValueError("initial finite formation did not satisfy its contracts")
        self.target = Binding.model_validate(
            (await self.call("receiver", operation="app.describe", name="triage"))["binding"]
        )
        report = Binding.model_validate(
            (await self.call("receiver", operation="app.describe", name="report"))["binding"]
        )
        self.target_requests = [
            UseRequest(
                receiver="receiver",
                capability_issuer=binding.issuer,
                subject=binding.subject,
                scope=binding.scope,
                binding_digest=binding.digest,
                semantic_fit="confirmed",
            ).model_dump(mode="json")
            for binding in (report, self.target)
        ]
        remote = Binding.model_validate(
            (await self.call("receiver", operation="app.describe", name="remote-words"))["binding"]
        )
        direct_request = {
            "operation": "invoke",
            "invocation_id": "soak-original-direct-a2a",
            "binding_id": remote.id,
            "binding_digest": remote.digest,
            "arguments": {"text": "explicit original direct document query"},
        }
        direct = await self.call("receiver", **direct_request)
        if direct.get("state") != "completed":
            raise ValueError("initial direct registered A2A observation did not complete")
        self.original_direct = {"request": direct_request, "result": direct}

    async def verify(self, provider, name, arguments, attempt):
        return await self.call(
            "verifier",
            operation="app.verify",
            provider=provider,
            name=name,
            arguments=arguments,
            attempt=attempt,
        )

    async def sample(self, *, operational=True, schedule=None):
        row = {"seconds": self.seconds(), "phase": self.phase}
        if schedule is not None:
            row["schedule"] = schedule
            row["sampling_started_seconds"] = self.seconds()
        if sys.platform == "linux":
            snapshot, vanished = await asyncio.to_thread(process_sample)
            row.update(
                vanished_or_unreadable_process_entries=vanished,
                owners={
                    owner: subtree(snapshot, (process.pid,))
                    for owner, process in self.processes.items()
                    if process.poll() is None
                },
                proxy=subtree(snapshot, [p.pid for p in self.mesh.proxies]),
                mcp=subtree(snapshot, [p.pid for p in self.mesh.workers]),
                postgresql_shared_cluster=subtree(snapshot, (self.pg_pid,)),
                driver=snapshot.get(os.getpid()),
            )
        else:
            row["process_resources"] = "unavailable; this short gate has no Linux /proc sampler"
        if operational:
            values = await asyncio.gather(
                *(
                    self.call(owner, operation="operational_metrics", category="monitoring")
                    for owner in self.configs
                )
            )
            row["operational"] = dict(zip(self.configs, values, strict=True))
        else:
            row["operational"] = "separate bounded monitoring requests; unavailable while pending"
        if schedule is not None:
            row["sampling_completed_seconds"] = self.seconds()
        self.samples.append(row)
        with (self.output / "samples.jsonl").open("a", encoding="utf-8") as stream:
            stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        return row

    async def finish(self):
        self.phase = "export"
        for owner in self.processes:
            await self.stop(owner)
        for log in self.logs:
            log.close()
        result = {
            "owners": {},
            "export_errors": {},
            "monitoring_durations": {},
            "rotated_owner_log_bytes": {},
            "secret_log_disclosures": [],
        }
        for owner, config in self.configs.items():
            try:
                artifacts = config.artifacts()
                usage = artifacts.usage()
                original = {
                    path.name: base64.b64encode(artifacts.get(path.name)).decode()
                    for path in artifacts.directory.iterdir()
                }
                write_json(
                    self.output / f"{owner}-artifacts.json",
                    {
                        "owner": owner,
                        "usage": usage,
                        "original_bytes_base64": original,
                    },
                )
                log_files = list((config.private_key.parent / "logs").glob("owner.jsonl*"))
                result["rotated_owner_log_bytes"][owner] = sum(
                    path.stat().st_size for path in log_files
                )
                forbidden = [
                    config.database_url.get_secret_value().encode(),
                    self.mesh.mcp_token.encode(),
                    b"BEGIN PRIVATE KEY",
                ]
                # Public deterministic fixture inputs also must not leak into
                # standard service logs. Keep raw and JSON-escaped spellings.
                texts = {self.training}
                texts.update(
                    call["request"].get("arguments", {}).get("text", "") for call in self.calls
                )
                for value in texts:
                    if isinstance(value, str) and len(value) >= 16:
                        forbidden.extend([value.encode(), json.dumps(value)[1:-1].encode()])
                for path in log_files:
                    content = path.read_bytes()
                    if any(value in content for value in forbidden):
                        result["secret_log_disclosures"].append({"owner": owner, "file": path.name})
                result["owners"][owner] = await asyncio.to_thread(
                    export_owner, config, self.output / f"{owner}-observations.json"
                )
            except Exception as error:
                result["export_errors"][owner] = type(error).__name__
        if self.mesh is not None:
            result["monitoring_durations"] = log_observations(self.mesh)
            # Keep private files and databases when exporting fails; do not discard evidence.
            if not result["export_errors"]:
                await asyncio.to_thread(self.mesh.close)
        self.journal.close()
        return result
