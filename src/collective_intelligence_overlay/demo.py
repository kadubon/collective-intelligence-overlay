"""Three-process loopback reference demonstration with persistent separate owners."""

import asyncio
import json
import os
import secrets
import socket
import sys
import time
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
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def initialize(directory: Path, admin_url: str, opa: str) -> dict[str, Config]:
    """Create new roles/databases only; never reuse or overwrite existing configuration."""
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
    peers = tuple(Peer(identity=name, url=f"http://127.0.0.1:{free_port()}/") for name in names)
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
                overlay.store.set_budget("work", Decimal(50))
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
            for _ in range(100):
                if any(p.returncode is not None for p in processes):
                    raise RuntimeError("peer exited; inspect local peer.log")
                try:
                    await send(configs[name], identities[name], name, {"operation": "metrics"})
                    break
                except (httpx.HTTPError, ConnectionError, AgentCardResolutionError):
                    await asyncio.sleep(0.1)
            else:
                raise RuntimeError("peer startup timeout")
        setup_started = time.perf_counter_ns()
        source = (directory / "formation.csv").read_text(encoding="utf-8")
        candidates = []
        for name, data in (("csv-sum", source), ("render-report", '{"rows":3,"total":"17.75"}')):
            formed = await call(
                "producer", operation="work", mode="form", attempt=uid(), name=name, source=data
            )
            checked = await call(
                "verifier",
                operation="work",
                mode="verify",
                attempt=uid(),
                capability=formed["capability"],
                source=data,
                result=formed["result"],
                receiver="receiver",
            )
            if checked["evidence"]["verdict"] != "PASS":
                raise RuntimeError("reference verification failed")
            candidates.append(formed["capability"])
        composite = await call(
            "producer",
            operation="work",
            mode="form",
            attempt=uid(),
            name="csv-report",
            source=source,
            dependencies=[c["subject"] for c in candidates],
        )
        await call(
            "verifier",
            operation="work",
            mode="verify",
            attempt=uid(),
            capability=composite["capability"],
            source=source,
            result=composite["result"],
            receiver="receiver",
        )
        for name in ("producer", "verifier"):
            await call("receiver", operation="sync", peer=name)
        cap = composite["capability"]
        req = {
            "receiver": "receiver",
            "subject": cap["subject"],
            "scope": cap["scope"],
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
        comparison = await compare_network(call, candidates[0])
        await call(
            "producer",
            operation="revoke",
            subject=candidates[0]["subject"],
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
