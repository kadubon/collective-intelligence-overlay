"""Three-process loopback reference demonstration with persistent separate owners."""

import asyncio
import json
import os
import secrets
import socket
import sys
import time
from contextlib import ExitStack
from decimal import Decimal
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
from pydantic import SecretStr
from securesystemslib.signer import CryptoSigner  # type: ignore[attr-defined]
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from .config import Config, Peer, TrustedIdentity
from .models import uid
from .storage import migrate

FORMATION_CSV = "category,amount\nbooks,12.50\nfood,7.25\nbooks,-2.00\n"
HELD_OUT_CSV = "category,amount\nrent,101.13\nfood,19.07\nrefund,-3.20\n"


def free_port() -> int:
    return free_ports(1)[0]


def free_ports(count: int) -> tuple[int, ...]:
    """Choose distinct loopback ports while every socket in the batch is bound."""
    if count < 1:
        raise ValueError("a positive port count is required")
    ports = []
    with ExitStack() as stack:
        for _ in range(count):
            sock = stack.enter_context(socket.socket())
            sock.bind(("127.0.0.1", 0))
            ports.append(int(sock.getsockname()[1]))
    return tuple(ports)


def initialize(
    directory: Path,
    admin_url: str,
    opa: str,
    *,
    work_allowance: Decimal = Decimal(50),
    work_allowances: dict[str, Decimal] | None = None,
) -> dict[str, Config]:
    """Create new roles/databases only; never reuse or overwrite existing configuration."""
    if not work_allowance.is_finite() or work_allowance < 0:
        raise ValueError("invalid initial work allowance")
    allowances = dict(work_allowances or {})
    if set(allowances) - {"producer", "verifier", "receiver"} or any(
        not amount.is_finite() or amount < 0 for amount in allowances.values()
    ):
        raise ValueError("invalid per-owner initial allowance")
    directory.mkdir(parents=True, exist_ok=False, mode=0o700)
    directory = directory.resolve()
    names = ("producer", "verifier", "receiver")
    signers = {name: CryptoSigner.generate_ed25519() for name in names}
    entries = {
        name: TrustedIdentity(
            keyid=signer.public_key.keyid,
            key=signer.public_key.to_dict(),
            trust_group=name,
            methods=("reference-check",),
        )
        for name, signer in signers.items()
    }
    peers = tuple(
        Peer(identity=name, url=f"http://127.0.0.1:{port}/")
        for name, port in zip(names, free_ports(len(names)), strict=True)
    )
    admin = create_engine(admin_url, isolation_level="AUTOCOMMIT", hide_parameters=True)
    configs = {}
    try:
        for name in names:
            role = "cio_" + uuid4().hex
            password = secrets.token_hex(24)
            with admin.connect() as conn:
                conn.execute(text(f"CREATE ROLE {role} LOGIN PASSWORD '{password}'"))
                conn.execute(text(f"CREATE DATABASE {role} OWNER {role}"))
                conn.execute(text(f"REVOKE CONNECT ON DATABASE {role} FROM PUBLIC"))
                conn.execute(text(f"GRANT CONNECT ON DATABASE {role} TO {role}"))
            url = make_url(admin_url).set(username=role, password=password, database=role)
            home = directory / name
            home.mkdir(mode=0o700)
            keyfile = home / "identity.pem"
            keyfile.write_bytes(signers[name].private_bytes)
            os.chmod(keyfile, 0o600)
            config = Config(
                execution_environment={"reference": "1"},
                owner=name,
                database_url=SecretStr(url.render_as_string(hide_password=False)),
                private_key=keyfile,
                artifact_directory=home / "artifacts",
                opa_binary=opa,
                url=next(p.url for p in peers if p.identity == name),
                local_development=True,
                share_records=True,
                peers=peers,
                identities=entries,
            )
            data = config.model_dump(mode="json")
            data["database_url"] = config.database_url.get_secret_value()
            config_path = home / "config.json"
            config_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            os.chmod(config_path, 0o600)
            _, overlay = config.runtime()
            try:
                migrate(overlay.store.engine)
                overlay.store.set_budget("work", allowances.get(name, work_allowance))
            finally:
                overlay.store.close()
            configs[name] = config
        (directory / "formation.csv").write_text(FORMATION_CSV, encoding="utf-8")
        (directory / "evaluation.csv").write_text(HELD_OUT_CSV, encoding="utf-8")
        return configs
    finally:
        admin.dispose()


async def run_demo(directory: Path, configs: dict[str, Config]) -> dict[str, Any]:
    if len(configs) > min(c.max_children for c in configs.values()):
        raise ValueError("child process limit exhausted")
    if min(c.max_rechecks for c in configs.values()) < 1:
        raise ValueError("demo requires one requalification")
    async with asyncio.timeout(min(c.max_seconds for c in configs.values())):
        return await _run_demo(directory, configs)


async def _run_demo(directory: Path, configs: dict[str, Config]) -> dict[str, Any]:
    from a2a.client import AgentCardResolutionError

    from .adapters.a2a import send

    processes: list[asyncio.subprocess.Process] = []
    logs = []
    identities = {}
    for name, config in configs.items():
        identity, overlay = config.runtime()
        overlay.store.close()
        identities[name] = identity

    steps = {name: 0 for name in configs}

    async def call(owner_name: str, **data: Any) -> dict[str, Any]:
        steps[owner_name] += 1
        if steps[owner_name] > configs[owner_name].max_steps:
            raise ValueError("step limit exhausted")
        return await send(configs[owner_name], identities[owner_name], owner_name, data)

    try:
        for name in configs:
            log = (directory / name / "peer.log").open("wb")
            logs.append(log)
            processes.append(
                await asyncio.create_subprocess_exec(
                    *[
                        sys.executable,
                        "-m",
                        "collective_intelligence_overlay.cli",
                        "peer",
                        "--reference",
                        "--config",
                        str((directory / name / "config.json").resolve()),
                    ],
                    stdout=log,
                    stderr=log,
                )
            )
        for name in configs:
            try:
                async with asyncio.timeout(30):
                    while True:
                        if any(p.returncode is not None for p in processes):
                            raise RuntimeError("peer exited; inspect local peer.log")
                        try:
                            await send(
                                configs[name], identities[name], name, {"operation": "metrics"}
                            )
                            break
                        except (httpx.HTTPError, ConnectionError, AgentCardResolutionError):
                            await asyncio.sleep(0.1)
            except TimeoutError as error:
                raise RuntimeError(
                    "peer startup exceeded 30 seconds; inspect local peer.log"
                ) from error
        setup_started = time.perf_counter_ns()
        source = (directory / "formation.csv").read_text(encoding="utf-8")
        registered = (await call("producer", operation="reference-register"))["registrations"]

        async def verify_registered(owner: str, item: dict[str, Any], source: str) -> None:
            binding = item["binding"]
            cap = item["capability"]
            arguments = (
                {"summary": json.loads(source)}
                if cap["entrypoint"] == "render-report"
                else {"source": source}
            )
            probe = await send(
                configs["verifier"],
                identities["verifier"],
                owner,
                {
                    "operation": "invoke",
                    "invocation_id": uid(),
                    "binding_id": binding["id"],
                    "binding_digest": cap["binding_digest"],
                    "arguments": arguments,
                    "purpose": "verification",
                },
            )
            if probe.get("state") != "completed":
                raise RuntimeError(f"reference probe failed: {probe}")
            checked = await call(
                "verifier",
                operation="work",
                mode="verify-registered",
                attempt=uid(),
                capability=cap,
                binding=binding,
                source=source,
                result=probe["result"],
                receiver="receiver",
            )
            if checked["evidence"]["verdict"] != "PASS":
                raise RuntimeError("registered reference verification failed")
            await call(owner, operation="sync", peer="verifier")

        for item in registered:
            data = (
                '{"rows":3,"total":"17.75"}'
                if item["capability"]["entrypoint"] == "render-report"
                else source
            )
            await verify_registered("producer", item, data)
        for peer in ("producer", "verifier"):
            await call("receiver", operation="sync", peer=peer)
        imported = []
        for item in (registered[0], registered[2]):
            local = await call("receiver", operation="reference-import", binding=item["binding"])
            await verify_registered("receiver", local, source)
            imported.append(local)
        cap = imported[-1]["capability"]
        req = {
            "receiver": "receiver",
            "subject": cap["subject"],
            "scope": cap["scope"],
            "capability_issuer": cap["issuer"],
            "binding_digest": cap["binding_digest"],
            "semantic_fit": "confirmed",
        }
        admitted = await call("receiver", operation="qualify", request=req)
        if admitted["decision"]["outcome"] != "ACCEPT":
            raise RuntimeError(f"unexpected admission: {admitted}")
        held_out = (directory / "evaluation.csv").read_text(encoding="utf-8")
        reused = await call(
            "receiver", operation="work", mode="reuse", attempt=uid(), request=req, source=held_out
        )
        changed = {**req, "scope": {**req["scope"], "environment": {"reference": "2"}}}
        requalification = await call("receiver", operation="qualify", request=changed)
        from .evaluation import compare_network

        setup_seconds = (time.perf_counter_ns() - setup_started) / 1e9
        comparison = await compare_network(call, imported[0]["capability"], imported[0]["binding"])
        await call(
            "producer",
            operation="revoke",
            subject=registered[0]["capability"]["subject"],
            reason="dependency withdrawn",
        )
        await call("receiver", operation="sync", peer="producer")
        rejected = await call("receiver", operation="qualify", request=req)
        result = {
            "processes": 3,
            "comparison": comparison,
            "shared_formation_transfer_seconds": setup_seconds,
            "admission": admitted["decision"]["outcome"],
            "held_out_result": reused["result"],
            "execution_receipt": reused["invocation"]["receipt_id"],
            "execution_path": "registered-A2A",
            "changed_environment": requalification["decision"]["outcome"],
            "after_dependency_revocation": rejected["decision"]["outcome"],
            "metrics": await call("receiver", operation="metrics"),
            "claims": "deterministic interoperability demonstration; no intelligence-growth claim",
        }
        if (
            result["changed_environment"] != "REQUALIFY"
            or result["after_dependency_revocation"] != "REJECT"
        ):
            raise RuntimeError("lifecycle checks failed")
        (directory / "result.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
        return result
    finally:
        for process in processes:
            process.terminate()
        for process in processes:
            try:
                await asyncio.wait_for(process.wait(), 10)
            except TimeoutError:
                process.kill()
                await asyncio.wait_for(process.wait(), 5)
        for log in logs:
            log.close()
